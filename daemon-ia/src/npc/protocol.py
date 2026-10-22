"""
Protocolo de arquivos entre o mod Lua e o daemon.

Lua -> daemon (NPC_events.txt), uma linha por evento:   evento|payload
    state|name=Marcos;mode=seguir;hp=80;player_hp=90;threats=2;ammo=ok;loot_near=1
    hurt|amount=10        kill|total=3        loot|item=Lata de Feijão
    no_ammo|              joined|name=Marcos  left|        died|
    fetch_fail|reason=none|danger|timeout   (a busca não deu certo)
    cmd|defender          (ordem do menu)     say|texto livre do jogador

daemon -> Lua (NPC_commands.txt), uma linha por comando:  seq|tipo|arg|extra
    1760400001|mode|defender|você tá ferido, deixa comigo
    1760400002|say|Fica atrás de mim.|
    1760400003|fetch|petrol,-empty|combustível      (buscar itens)
"""
import os
import threading
import time
from pathlib import Path


def parse_line(line: str):
    """'evento|payload' -> (evento, payload)."""
    parts = line.split("|", 1)
    return parts[0].strip(), (parts[1] if len(parts) > 1 else "")


def parse_kv(payload: str) -> dict:
    """'a=1;b=2' -> {'a': '1', 'b': '2'} (ignora pedaços sem '=')."""
    out = {}
    for part in payload.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def clean_field(text: str) -> str:
    """Remove separadores do protocolo e quebras de linha."""
    return " ".join(str(text).replace("|", " ").split())


class FileTail:
    """Lê (tail) um arquivo que o Lua só faz append. Começa do FIM por padrão."""

    def __init__(self, path: Path, on_line, poll_s: float = 0.25, from_start: bool = False):
        self.path = Path(path)
        self.on_line = on_line
        self.poll_s = poll_s
        self._partial = b""
        self._stop = threading.Event()
        self._thread = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if from_start or not self.path.exists():
            self._offset = 0
        else:
            self._offset = self.path.stat().st_size

    def poll_once(self) -> int:
        """Processa linhas novas. Devolve quantas leu."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            self._offset, self._partial = 0, b""
            return 0
        if size < self._offset:          # arquivo truncado/recriado
            self._offset, self._partial = 0, b""
        if size == self._offset:
            return 0

        with open(self.path, "rb") as f:
            f.seek(self._offset)
            chunk = f.read()
        self._offset += len(chunk)

        lines = (self._partial + chunk).split(b"\n")
        self._partial = lines.pop()
        count = 0
        for raw in lines:
            line = raw.decode("utf-8", "replace").strip()
            if line:
                count += 1
                try:
                    self.on_line(line)
                except Exception as e:
                    print(f"[NPC] erro ao tratar linha '{line[:60]}': {e}", flush=True)
        return count

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as e:
                print(f"[NPC] erro no monitor: {e}", flush=True)
            time.sleep(self.poll_s)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="npc-tail")
        self._thread.start()

    def stop(self):
        self._stop.set()


class CommandWriter:
    """Escreve NPC_commands.txt (mantém só as últimas N linhas, troca atômica)."""

    def __init__(self, path: Path, keep: int = 20):
        self.path = Path(path)
        self.keep = keep
        self._lock = threading.Lock()
        self._seq = int(time.time())      # monotônico entre reinícios
        self._lines = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._flush()                      # limpa comandos velhos da sessão anterior

    def _flush(self):
        text = "".join(l + "\n" for l in self._lines)
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            for _ in range(5):
                try:
                    os.replace(tmp, self.path)
                    return
                except OSError:           # Lua pode estar lendo neste instante (Windows)
                    time.sleep(0.05)
        except OSError:
            pass
        try:
            self.path.write_text(text, encoding="utf-8")
        except OSError as e:
            print(f"[NPC] falha ao gravar comandos: {e}", flush=True)

    def send(self, kind: str, arg: str, extra: str = "") -> int:
        with self._lock:
            self._seq += 1
            self._lines.append(f"{self._seq}|{kind}|{clean_field(arg)}|{clean_field(extra)}")
            self._lines = self._lines[-self.keep:]
            self._flush()
            return self._seq

    def send_mode(self, mode: str, reason: str = "") -> int:
        return self.send("mode", mode, reason)

    def send_say(self, text: str) -> int:
        return self.send("say", text)

    def send_fetch(self, keywords: str, label: str = "") -> int:
        """Pede ao adapter para buscar itens (palavras-chave separadas por vírgula)."""
        return self.send("fetch", keywords, label)
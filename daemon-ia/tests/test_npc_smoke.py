"""
Teste de fumaça do módulo NPC, sem jogo, sem XTTS e sem Ollama (tudo falso).
Rodar na raiz do projeto:  python tests/test_npc_smoke.py
"""
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.npc import npc_config as cfg                      # noqa: E402
from src.npc.npc_brain import NpcCompanion                 # noqa: E402
from src.npc.npc_chat import detect_mode                   # noqa: E402
from src.npc.npc_decision import ModeDecider               # noqa: E402
from src.npc.npc_state import NpcState                     # noqa: E402
from src.npc.protocol import parse_line, parse_kv, CommandWriter, FileTail  # noqa: E402


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def ensure(self, text, params):
        return f"fake://{text}"


def make_companion(tmp: Path, llm=None):
    played = []
    gate = threading.Lock()
    comp = NpcCompanion(
        base_pipeline=None,
        play_fn=lambda p: played.append(p),
        gate=gate,
        llm_fn=llm or (lambda *a, **k: ""),
        voice=FakeVoice(),
        events_file=tmp / "NPC_events.txt",
        commands_file=tmp / "NPC_commands.txt",
        memory_file=tmp / "mem.json",
    )
    return comp, played


def wait_for(cond, timeout=3.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_protocol():
    assert parse_line("state|hp=80;mode=seguir") == ("state", "hp=80;mode=seguir")
    assert parse_line("left|") == ("left", "")
    assert parse_kv("a=1;b=x y;lixo") == {"a": "1", "b": "x y"}
    print("ok protocolo")


def test_detect_mode():
    assert detect_mode("fica aí um pouco") == "ficar"
    assert detect_mode("Vem comigo!") == "seguir"
    assert detect_mode("protege a gente") == "defender"
    assert detect_mode("pega aquela lata") == "saquear"
    assert detect_mode("como você tá?") is None
    print("ok detect_mode")


def test_decider():
    now = [1000.0]
    dec = ModeDecider(llm_fn=None, clock=lambda: now[0])
    st = NpcState()
    st.update({"hp": "80", "player_hp": "20", "threats": "2", "mode": "seguir"}, now=now[0])
    d = dec.decide(st)
    assert d and d.mode == "defender", d

    # histerese: logo depois não troca de novo
    dec.note_applied()
    st.mode = "defender"
    st.update({"hp": "20", "player_hp": "20", "threats": "2", "mode": "defender"}, now=now[0])
    assert dec.decide(st) is None
    now[0] += 25
    d = dec.decide(st)
    assert d and d.mode == "seguir", d            # ferido => recua

    # ordem manual bloqueia a IA
    dec.note_manual()
    now[0] += 25
    assert dec.decide(st) is None
    print("ok decisão")


def test_llm_tiebreak_validates():
    now = [5000.0]
    calls = []

    def llm(evt, prompt, **kw):
        calls.append(kw.get("json_mode"))
        return '{"modo": "voar", "motivo": "porque sim"}'      # modo inválido

    dec = ModeDecider(llm_fn=llm, clock=lambda: now[0])
    st = NpcState()
    st.update({"hp": "50", "player_hp": "90", "threats": "0", "loot_near": "2", "mode": "ficar"}, now=now[0])
    assert dec.decide(st) is None and calls == [True]
    now[0] += 100
    dec.llm_fn = lambda *a, **k: '{"modo": "saquear", "motivo": "Vale a pena pegar."}'
    d = dec.decide(st)
    assert d and d.mode == "saquear" and d.source == "llm", d
    print("ok desempate LLM validado")


def test_command_writer_and_tail():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        w = CommandWriter(t / "c.txt", keep=3)
        for i in range(5):
            w.send_mode("seguir", f"motivo {i} | com pipe")
        lines = (t / "c.txt").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3 and all(l.count("|") == 3 for l in lines), lines
        seqs = [int(l.split("|")[0]) for l in lines]
        assert seqs == sorted(seqs)

        got = []
        ev = t / "e.txt"
        ev.write_text("velho|x\n", encoding="utf-8")
        tail = FileTail(ev, got.append)
        assert tail.poll_once() == 0                   # histórico antigo ignorado
        with open(ev, "a", encoding="utf-8") as f:
            f.write("novo|1\nmeia")
        assert tail.poll_once() == 1 and got == ["novo|1"]
        with open(ev, "a", encoding="utf-8") as f:
            f.write("|linha\n")
        tail.poll_once()
        assert got[-1] == "meia|linha"
    print("ok escrita de comandos + tail")


def test_end_to_end():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        comp, played = make_companion(t)
        comp.speaker.start()
        feed = comp._on_line

        # ordem por texto -> modo + fala + comando
        feed("say|fica aí um pouco")
        assert wait_for(lambda: any("mode|ficar" in l for l in (t / "NPC_commands.txt").read_text(encoding="utf-8").splitlines()))
        assert wait_for(lambda: len(played) >= 1)
        assert comp.state.mode == "ficar"

        # state com jogador ferido: ordem manual ainda bloqueia a IA
        feed("state|name=Marcos;mode=ficar;hp=90;player_hp=20;threats=3;ammo=ok")
        cmds = (t / "NPC_commands.txt").read_text(encoding="utf-8")
        assert "defender" not in cmds, cmds

        # libera o override e repete
        comp.decider.manual_until = 0
        comp.decider.last_change = 0
        feed("state|name=Marcos;mode=ficar;hp=90;player_hp=20;threats=3;ammo=ok")
        cmds = (t / "NPC_commands.txt").read_text(encoding="utf-8")
        assert "|mode|defender|" in cmds, cmds
        assert wait_for(lambda: any("deixa comigo" in p.lower() for p in played))

        # loot com LLM que "inventa" consumo é descartado => cai na frase estática
        comp.phrases.llm_fn = lambda *a, **k: "Comi o bacon, o melhor que tive em semanas."
        import src.npc.npc_phrases as ph
        ph.STATIC_FIRST_RATIO = 0.0                    # força caminho LLM
        comp.state.threats = 0
        feed("loot|item=Bacon")
        assert wait_for(lambda: any("Bacon" in p for p in played), 3), played
        assert not any("Comi" in p for p in played), played
        comp.stop()
    print("ok ponta a ponta")


if __name__ == "__main__":
    test_protocol()
    test_detect_mode()
    test_decider()
    test_llm_tiebreak_validates()
    test_command_writer_and_tail()
    test_end_to_end()
    print("\nTODOS OS TESTES PASSARAM")
"""
Personalidade e memória do NPC (persistida em src/data/npc_memory.json).
"""
import json
import time
from pathlib import Path

from src.npc.npc_config import NPC_NAME, NPC_MEMORY_FILE

MAX_FACTS = 12

EVENT_CONTEXT = {
    "hurt":    "Você acabou de levar dano de um zumbi.",
    "kill":    "Você acabou de derrubar um zumbi.",
    "loot":    "Você pegou {item} e guardou na mochila. Você NÃO usou, comeu nem consumiu.",
    "no_ammo": "A sua arma ficou sem munição.",
    "low_hp":  "Você está muito ferido e fraco.",
    "danger":  "Zumbis estão se aproximando de vocês.",
    "joined":  "Você acabou de se juntar ao jogador como companheiro.",
    "idle":    "Está tudo calmo. Comente algo curto sobre a situação ou o clima, sem inventar fatos.",
}
EVENT_EXAMPLES = {
    "hurt":    ["Ai, isso doeu!", "Droga, me acertaram!"],
    "kill":    ["Mais um que não levanta.", "Esse já era."],
    "loot":    ["Boa, {item} vai servir.", "{item}... guardo pra depois."],
    "no_ammo": ["Acabou a munição!", "Tô sem bala!"],
    "low_hp":  ["Tô muito mal...", "Preciso parar um pouco."],
    "danger":  ["Cuidado, vem gente!", "Tem zumbi chegando!"],
    "joined":  ["Tô contigo.", "Bora, eu vou junto."],
    "idle":    ["Tá quieto demais.", "Faz tempo que não vejo ninguém."],
}


class NpcMemory:
    def __init__(self, path: Path = NPC_MEMORY_FILE):
        self.path = Path(path)
        self.bond = 0
        self.facts = []
        self.stats = {}
        self._dirty = False
        self._last_save = 0.0
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.bond = int(data.get("bond", 0))
            self.facts = list(data.get("facts", []))[-MAX_FACTS:]
            self.stats = dict(data.get("stats", {}))
        except Exception:
            pass

    def remember(self, fact: str):
        self.facts = (self.facts + [fact])[-MAX_FACTS:]
        self._dirty = True

    def count(self, key: str, n: int = 1):
        self.stats[key] = self.stats.get(key, 0) + n
        self._dirty = True

    def add_bond(self, n: int = 1):
        self.bond += n
        self._dirty = True

    def relation(self) -> str:
        if self.bond < 10:
            return "ainda está se acostumando com o jogador"
        if self.bond < 40:
            return "é parceiro do jogador"
        return "é leal ao jogador, quase um amigo"

    def save_if_needed(self, now: float = None, min_interval: float = 10.0):
        now = now if now is not None else time.time()
        if not self._dirty or now - self._last_save < min_interval:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"bond": self.bond, "stats": self.stats, "facts": self.facts}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            self._dirty = False
            self._last_save = now
        except OSError:
            pass


def system_prompt(name: str, memory: NpcMemory) -> str:
    base = (
        f"Você é {name}, um sobrevivente que acompanha o jogador em Project Zomboid. "
        "Tom: leal, direto, humor seco, cansado mas confiável. Português do Brasil, coloquial. "
        "Fale SEMPRE curto: uma frase de 3 a 12 palavras, sem aspas, sem emojis e sem narrar ações. "
        "Nunca finja ter feito algo que não aconteceu. "
        f"Você {memory.relation()}."
    )
    if memory.facts:
        base += " Lembranças recentes: " + "; ".join(memory.facts[-4:]) + "."
    return base
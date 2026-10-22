"""
Estado atual do NPC, atualizado pelos eventos 'state' vindos do Lua.
"""
import time
from dataclasses import dataclass
from typing import Optional

from src.npc.npc_config import NPC_NAME, STATE_STALE_S


def _int(v, default=0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


@dataclass
class NpcState:
    name: str = NPC_NAME
    mode: str = "seguir"
    hp: int = 100
    player_hp: int = 100
    threats: int = 0
    ammo: str = "ok"            # ok | empty | none
    loot_near: int = 0
    present: bool = False
    updated_at: float = 0.0
    calm_since: Optional[float] = None   # desde quando threats == 0 (None se em combate)
    kills: int = 0

    @property
    def in_combat(self) -> bool:
        return self.threats > 0

    def update(self, kv: dict, now: Optional[float] = None):
        now = now if now is not None else time.time()
        prev_threats = self.threats

        self.name = kv.get("name", self.name) or self.name
        self.mode = kv.get("mode", self.mode) or self.mode
        self.hp = _int(kv.get("hp"), self.hp)
        self.player_hp = _int(kv.get("player_hp"), self.player_hp)
        self.threats = _int(kv.get("threats"), 0)
        self.ammo = kv.get("ammo", self.ammo) or self.ammo
        self.loot_near = _int(kv.get("loot_near"), 0)
        self.present = True
        self.updated_at = now

        if self.threats > 0:
            self.calm_since = None
        elif prev_threats > 0 or self.calm_since is None:
            self.calm_since = now

    def is_stale(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return self.present and (now - self.updated_at) > STATE_STALE_S

    def calm_for(self, now: Optional[float] = None) -> float:
        now = now if now is not None else time.time()
        return 0.0 if self.calm_since is None else now - self.calm_since

    def summary(self) -> str:
        return (f"vida {self.hp}%, modo {self.mode}, ameaças por perto {self.threats}, "
                f"munição {self.ammo}, itens por perto {self.loot_near}; "
                f"o jogador está com {self.player_hp}% de vida")
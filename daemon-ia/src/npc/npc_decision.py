"""
Decisão de MODO do NPC (seguir / ficar / defender / saquear).
Regras determinísticas primeiro; LLM só como desempate, fora de combate,
com saída validada contra a lista de modos. Quem EXECUTA é o mod base.
"""
import json
import time
from dataclasses import dataclass

from src.npc.npc_config import (
    MODES, MANUAL_OVERRIDE_S, MODE_MIN_INTERVAL_S, LLM_DECISION_COOLDOWN_S,
    LOW_HP, PLAYER_LOW_HP,
)


@dataclass
class Decision:
    mode: str
    reason: str      # frase em 1ª pessoa, também usada como fala
    source: str      # "rule" | "llm"


class ModeDecider:
    def __init__(self, llm_fn=None, clock=time.time):
        self.llm_fn = llm_fn
        self.clock = clock
        self.last_change = 0.0
        self.manual_until = 0.0
        self.last_llm = 0.0

    def note_manual(self):
        now = self.clock()
        self.manual_until = now + MANUAL_OVERRIDE_S
        self.last_change = now

    def note_applied(self):
        self.last_change = self.clock()

    def decide(self, st):
        now = self.clock()
        if not st.present or now < self.manual_until:
            return None
        if now - self.last_change < MODE_MIN_INTERVAL_S:
            return None

        d = self._rules(st, now) or self._llm_tiebreak(st, now)
        if d is None or d.mode == st.mode:
            return None
        return d

    def _rules(self, st, now):
        if st.threats > 0:
            if st.hp <= LOW_HP:
                return Decision("seguir", "Tô ferido, vou recuar pra perto de você.", "rule")
            if st.ammo == "empty" and st.mode == "defender":
                return Decision("seguir", "Sem munição, fico perto de você.", "rule")
            if st.player_hp <= PLAYER_LOW_HP:
                return Decision("defender", "Você tá ferido, deixa comigo.", "rule")
            if st.threats >= 2 and st.mode != "defender":
                return Decision("defender", "Tem zumbi demais, eu cubro você.", "rule")
            return None

        calm = st.calm_for(now)
        if st.mode == "defender" and calm >= 10:
            return Decision("seguir", "Área limpa, volto a te acompanhar.", "rule")
        if st.mode == "saquear" and st.loot_near == 0:
            return Decision("seguir", "Não tem mais nada aqui, vamos.", "rule")
        if (st.mode == "seguir" and st.loot_near > 0 and calm >= 10
                and st.hp > 60 and st.player_hp >= 50):
            return Decision("saquear", "Vi coisa útil aqui perto, vou pegar.", "rule")
        return None

    def _llm_tiebreak(self, st, now):
        """Caso ambíguo: calmo, itens por perto, mas o NPC está meio ferido."""
        if self.llm_fn is None or st.threats > 0:
            return None
        if not (st.loot_near > 0 and LOW_HP < st.hp <= 60):
            return None
        if now - self.last_llm < LLM_DECISION_COOLDOWN_S:
            return None
        self.last_llm = now

        prompt = (
            f"Situação: {st.summary()}. Não há ameaças agora.\n"
            f"Modos possíveis: {', '.join(MODES)}.\n"
            "Há itens por perto e o NPC está meio ferido. Qual modo é mais sensato agora? "
            'Responda só JSON: {"modo": "...", "motivo": "frase curta em 1ª pessoa"}'
        )
        raw = self.llm_fn("npc_decision", prompt, temperature=0.2, json_mode=True)
        try:
            a, b = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[a:b + 1])
        except Exception:
            return None
        mode = str(data.get("modo", "")).strip().lower()
        reason = str(data.get("motivo", "")).strip()
        if mode not in MODES:
            return None
        if not (2 <= len(reason.split()) <= 18):
            reason = "Acho que é o melhor agora."
        return Decision(mode, reason, "llm")
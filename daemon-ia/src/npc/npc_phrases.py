"""
Gerador de falas do NPC: frases estáticas (cache de áudio) + LLM com validação.
A LLM NUNCA é chamada em combate.
"""
import random
import re
import time

from src.npc.npc_config import NPC_PHRASES, STATIC_FIRST_RATIO, LOOT_BANNED
from src.npc.npc_persona import EVENT_CONTEXT, EVENT_EXAMPLES, system_prompt


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[NPC FALAS] {msg}", flush=True)


class PhraseMaker:
    def __init__(self, llm_fn, memory, name: str):
        self.llm_fn = llm_fn
        self.memory = memory
        self.name = name

    # --- estáticas ---
    def static(self, key: str, item: str = ""):
        options = NPC_PHRASES.get(key)
        if not options:
            return None
        text = random.choice(options)
        if "{item}" in text:
            if not item:
                options = [o for o in options if "{item}" not in o]
                if not options:
                    return None
                text = random.choice(options)
            else:
                text = text.format(item=item)
        return text

    # --- validação ---
    @staticmethod
    def _clean(txt: str) -> str:
        txt = (txt or "").strip().split("\n")[0].strip().strip("\"'“”` ")
        txt = re.sub(r"^(fala|resposta|resposta do npc)\s*[:\-]\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"[^\w\s.,!?;:'\-…]", "", txt)
        return re.sub(r"\s+", " ", txt).strip()

    @staticmethod
    def _valid(txt: str, banned, item_words, max_words=14) -> bool:
        if not (2 <= len(txt.split()) <= max_words):
            return False
        low = txt.lower()
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in banned):
            return False
        if item_words and not any(w in low for w in item_words):
            return False
        return True

    # --- fala de evento ---
    def make(self, key: str, state, item: str = "", allow_llm: bool = True):
        use_llm = (allow_llm and not state.in_combat and key in EVENT_CONTEXT
                   and random.random() >= STATIC_FIRST_RATIO and self.llm_fn is not None)
        if use_llm:
            text = self._llm_event(key, state, item)
            if text:
                return text
        return self.static(key, item)

    def _llm_event(self, key: str, state, item: str):
        ctx = EVENT_CONTEXT[key].format(item=item or "algo")
        examples = [e.format(item=item or "isso") for e in EVENT_EXAMPLES.get(key, [])]
        prompt = f"Situação: {ctx}\nEstado: {state.summary()}.\nEscreva UMA fala curta reagindo a isso."
        if examples:
            prompt += "\nExemplos do estilo (NÃO copie):\n" + "\n".join(f"- {e}" for e in examples)
        prompt += "\nFala:"

        banned = LOOT_BANNED if key == "loot" else []
        item_words = [w.lower() for w in re.findall(r"[^\W\d_]{4,}", item)] if key == "loot" else []

        for _ in range(2):
            raw = self.llm_fn(f"npc_{key}", prompt,
                              system_override=system_prompt(self.name, self.memory),
                              temperature=0.8)
            if not raw:
                return None
            txt = self._clean(raw)
            if self._valid(txt, banned, item_words):
                return txt
            log(f"descartada ({key}): \"{txt}\"")
        return None

    # --- resposta de conversa livre ---
    def chat_reply(self, player_text: str, state):
        if state.in_combat:
            return self.static("busy")
        if self.llm_fn is not None:
            prompt = (f"Estado: {state.summary()}.\nO jogador disse: \"{player_text}\"\n"
                      "Responda como o companheiro, em uma frase curta. "
                      "Não prometa ações (como seguir, ficar ou atacar): apenas converse.\nFala:")
            raw = self.llm_fn("npc_chat", prompt,
                              system_override=system_prompt(self.name, self.memory),
                              temperature=0.8)
            txt = self._clean(raw)
            if txt and self._valid(txt, [], [], max_words=22):
                return txt
        return self.static("unknown")
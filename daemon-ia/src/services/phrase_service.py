"""
Falas curtas de eventos (loot, dor, pânico...) com contexto, exemplos e validação.
Evita alucinações como "comi o bacon" quando o jogador só pegou o item.
"""
import re
import time
from src.config import EVENT_CONTEXT, EVENT_EXAMPLES, BANNED_WORDS, EXTRA_RULES
from src.services.ollama_service import call_ollama_chat

LOOT_RULE = ("Você apenas PEGOU o item e guardou na mochila. NÃO comeu, NÃO bebeu, NÃO usou, NÃO provou: "
             "não fale de sabor nem de ter consumido. Fale só do achado (utilidade, opinião ou humor).")

# Consumo/sabor inventado + 'raro' (vem do nome do evento loot_rare, não do jogo)
LOOT_EXTRA_BANNED = [
    "comi", "comendo", "comeu", "devorei", "saboreei", "bebi", "sabor", "saboroso", "saborosa",
    "delicioso", "deliciosa", "delícia", "gostoso", "gostosa", "melhor que", "semanas",
    "raro", "rara", "raros", "raras", "raríssimo", "raríssima",
]


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[FRASES] {msg}", flush=True)


def generate_event_phrase(evt: str, detail: str, item: str):
    """Devolve uma fala validada ou None (quem chamou usa o fallback estático)."""
    ctx = EVENT_CONTEXT.get(evt) or f"Aconteceu o evento '{evt}'."
    if "{item}" in ctx:
        ctx = ctx.format(item=item or "isso")
    examples = [e.format(item=item or "isso") for e in EVENT_EXAMPLES.get(evt, [])]

    banned = list(BANNED_WORDS.get(evt, []))
    rules = EXTRA_RULES.get(evt, "")
    if evt == "loot_rare":
        banned += LOOT_EXTRA_BANNED
        rules = (rules + " " + LOOT_RULE).strip()

    prompt = f"Situação: {ctx}\nEscreva UMA fala curta (3 a 9 palavras) reagindo a isso."
    if rules:
        prompt += f"\nRegras: {rules}"
    if examples:
        prompt += "\nExemplos do estilo (NÃO copie, crie uma fala nova parecida):\n" + "\n".join(f"- {e}" for e in examples)
    prompt += "\nFala:"

    item_words = [w.lower() for w in re.findall(r"[^\W\d_]{4,}", item or "")]
    known = {e.lower() for e in examples}

    for _ in range(3):
        txt = call_ollama_chat(evt, prompt, temperature=0.8)
        if not txt:
            return None  # Ollama falhou: deixa o fallback estático resolver

        txt = txt.strip().split("\n")[0].strip()
        txt = re.sub(r"^(fala|resposta|sobrevivente)\s*[:\-]\s*", "", txt, flags=re.IGNORECASE)
        low = txt.lower()

        reason = None
        if not (2 <= len(txt.split()) <= 12):
            reason = "tamanho"
        elif any(re.search(rf"\b{re.escape(w)}\b", low) for w in banned):
            reason = "palavra proibida"
        elif low in known:
            reason = "copiada do exemplo"
        elif evt == "loot_rare" and item_words and not any(w in low for w in item_words):
            reason = "não cita o item"

        if reason:
            log(f"descartada ({reason}): \"{txt}\"")
            continue
        return txt
    return None
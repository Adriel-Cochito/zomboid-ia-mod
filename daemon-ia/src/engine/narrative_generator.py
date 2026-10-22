"""
Passo 3: a LLM só dá voz. Resumo do PASSADO + missões em tom de DÚVIDA sobre o futuro.
Cada campo é validado; se falhar, entra um fallback determinístico.
"""
import json
import random
from src.config import PERSONA
from src.services.ollama_service import call_ollama_chat
from src.engine.strategy_engine import EVT_PT, NEED_PT

CAT_PT = {
    "saude": "saúde", "fortificacao": "fortificação", "suprimentos": "suprimentos",
    "veiculos_energia": "veículos e energia", "combate_manutencao": "combate e manutenção",
    "outros": "outros",
}
STAGE_PT = {"inicio": "começo da sobrevivência", "meio": "fase intermediária", "avancado": "sobrevivente experiente"}
DOUBT_WORDS = ("?", "talvez", "será", "quem sabe", "dúvida")

DOUBT_TEMPLATES = [
    "Será que não valeria {acao}? Quem sabe eu ache {itens} por aí.",
    "Talvez fosse bom {acao}... e, com sorte, aparecer {itens}.",
    "Fico em dúvida se não é hora de {acao}. {itens_cap} poderiam ajudar.",
]


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _past_sentences(profile: dict) -> list[str]:
    s = []

    # Loot do dia, por categoria
    if profile["loot"]:
        for cat, items in profile["loot"].items():
            s.append(f"Em {CAT_PT.get(cat, cat)}, encontrei {', '.join(items)}.")
    else:
        s.append("Não encontrei nada que valesse nota.")

    # Incidentes
    if profile["incidents"]:
        lista = ", ".join(f"{EVT_PT.get(t, t)} ({n}x)" for t, n in profile["incidents"].items())
        s.append(f"Passei por: {lista}.")
    else:
        s.append("O dia foi relativamente calmo.")

    # Necessidades que ficaram sem resolução
    if profile["unresolved"]:
        s.append("Ficou pendente: " + ", ".join(NEED_PT[n] for n in profile["unresolved"]) + ".")

    # Tempo de vida do personagem
    days = profile.get("days")
    if days is not None:
        if days == 0:
            s.append("É o meu primeiro dia de sobrevivência.")
        else:
            s.append(f"Já são {days} dia(s) de sobrevivência ({STAGE_PT[profile['stage']]}).")

    return s
    

def _fallback_mission(d: dict) -> dict:
    cat_pt = CAT_PT.get(d["categoria"], d["categoria"])
    acao = _lower_first(d["acoes"][0]) if d["acoes"] else f"olhar melhor a área de {cat_pt}"
    itens = ", ".join(d["itens"]) if d["itens"] else "algo útil"
    desc = random.choice(DOUBT_TEMPLATES).format(acao=acao, itens=itens, itens_cap=itens[:1].upper() + itens[1:])
    return {"titulo": f"Será que vale olhar {cat_pt}?", "descricao": desc}


def _parse_json(text: str):
    if not text:
        return None
    a, b = text.find("{"), text.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        data = json.loads(text[a:b + 1])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _valid_text(v, max_len=300) -> bool:
    return isinstance(v, str) and 3 < len(v.strip()) <= max_len


def _has_doubt(v: str) -> bool:
    low = v.lower()
    return any(w in low for w in DOUBT_WORDS)


def generate_narrative(profile: dict, strategy: dict) -> dict:
    directions = strategy["direcoes"]
    past = _past_sentences(profile)

    dir_lines = []
    for i, d in enumerate(directions, 1):
        dir_lines.append(
            f"{i}. área={CAT_PT.get(d['categoria'], d['categoria'])} | motivo={d['motivo']} | "
            f"ações possíveis={', '.join(d['acoes']) or 'nenhuma'} | "
            f"itens possíveis={', '.join(d['itens']) or 'nenhum'}"
        )

    prompt = f"""FATOS DO DIA (já aconteceram):
{' '.join(past)}

DIREÇÕES POSSÍVEIS PARA O PRÓXIMO DIA:
{chr(10).join(dir_lines)}

Escreva em português do Brasil, como o sobrevivente falando sozinho. Responda SOMENTE um JSON com:
- "resumo_passado": 1 ou 2 frases, TUDO no passado, usando só os fatos acima.
- "fala_voz": no máximo 2 frases. A primeira resume o dia no passado. A segunda é uma DÚVIDA sobre o futuro (ex.: começando com "Será que" ou "Talvez").
- "missoes": lista com {len(directions)} objeto(s), na mesma ordem das direções, cada um com "titulo" (curto, em forma de dúvida) e "descricao" (1 ou 2 frases em tom de dúvida, citando apenas ações e itens da direção correspondente).
Não invente itens. Não dê ordens. Não use "você"."""

    system = PERSONA + " Responda somente JSON válido."
    raw = call_ollama_chat("narrative_generation", prompt, system_override=system,
                           temperature=0.6, json_mode=True)
    data = _parse_json(raw) or {}

    resumo = data.get("resumo_passado")
    if not _valid_text(resumo):
        resumo = " ".join(past)

    fala = data.get("fala_voz")
    if not (_valid_text(fala) and _has_doubt(fala)):
        first = directions[0] if directions else None
        cat_pt = CAT_PT.get(first["categoria"], first["categoria"]) if first else "os arredores"
        fala = f"{past[0]} Será que não valeria olhar melhor {cat_pt} amanhã?"

    llm_missions = data.get("missoes") if isinstance(data.get("missoes"), list) else []
    missoes = []
    for i, d in enumerate(directions):
        fb = _fallback_mission(d)
        m = llm_missions[i] if i < len(llm_missions) and isinstance(llm_missions[i], dict) else {}
        titulo = m.get("titulo") if _valid_text(m.get("titulo"), 90) else fb["titulo"]
        descricao = m.get("descricao") if (_valid_text(m.get("descricao")) and _has_doubt(m["descricao"])) else fb["descricao"]
        missoes.append({
            "titulo": titulo,
            "descricao": descricao,
            "categoria": d["categoria"],
            "itens_recomendados": d["itens"],
            "acoes_sugeridas": d["acoes"],
            "justificativa": d["motivo"],
        })

    return {"resumo_passado": resumo, "fala_voz": fala, "missoes": missoes, "foco": strategy["foco"]}


def generate_mission_speech(profile: dict, strategy: dict) -> str:
    """
    Camada final, só para o áudio de OBJETIVO POSSÍVEL: concreto, em tom de dúvida,
    baseado nas 2 melhores direções do estrategista.
    """
    dirs = strategy["direcoes"][:2]
    if not dirs:
        return ""

    lines = []
    for i, d in enumerate(dirs, 1):
        lines.append(
            f"{i}. área={CAT_PT.get(d['categoria'], d['categoria'])} | motivo={d['motivo']} | "
            f"ações possíveis={', '.join(d['acoes']) or 'nenhuma'} | "
            f"itens possíveis={', '.join(d['itens']) or 'nenhum'}"
        )

    prompt = f"""Fatos do dia: {' '.join(_past_sentences(profile))}

Possíveis objetivos para o próximo dia:
{chr(10).join(lines)}

Escreva em português do Brasil, como o sobrevivente pensando em voz alta, UMA fala de no máximo 2 frases propondo um possível objetivo concreto para o próximo dia: o que buscar ou fazer de diferente, citando pelo menos um item ou ação da lista. Use tom de dúvida ("Talvez o próximo passo seja...", "Será que valeria...?"). Não dê ordens. Não invente itens. Responda só com a fala."""

    text = call_ollama_chat("mission_speech", prompt, system_override=PERSONA, temperature=0.6)
    text = " ".join(text.split()) if text else ""

    keywords = set()
    for d in dirs:
        for s in d["itens"] + d["acoes"]:
            keywords.update(w.lower() for w in s.replace(",", " ").split() if len(w) >= 4)

    if text and _valid_text(text, 260) and _has_doubt(text) and any(k in text.lower() for k in keywords):
        return text

    # Fallback determinístico
    d = dirs[0]
    cat_pt = CAT_PT.get(d["categoria"], d["categoria"])
    acao = _lower_first(d["acoes"][0]) if d["acoes"] else f"olhar melhor a área de {cat_pt}"
    itens = ", ".join(d["itens"][:2]) if d["itens"] else "algo útil"
    fb = f"Talvez o próximo passo seja {acao}, atrás de {itens}."
    if len(dirs) > 1:
        fb += f" Ou será que valeria olhar {CAT_PT.get(dirs[1]['categoria'], dirs[1]['categoria'])} primeiro?"
    return fb
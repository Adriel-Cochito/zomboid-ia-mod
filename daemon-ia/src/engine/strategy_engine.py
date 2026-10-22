"""
Passo 2: decide O QUE BUSCAR DE DIFERENTE amanhã, cruzando passado (perfil do dia),
etapa de vida do personagem e conhecimento do jogo. Determinístico.
"""
import random
from src.engine.knowledge_filter import KnowledgeFilter, EVENT_CATEGORY_MAP

STAGE_ORDER = {
    "inicio":   ["suprimentos", "saude", "combate_manutencao", "fortificacao", "veiculos_energia"],
    "meio":     ["fortificacao", "saude", "combate_manutencao", "suprimentos", "veiculos_energia"],
    "avancado": ["veiculos_energia", "fortificacao", "suprimentos", "saude", "combate_manutencao"],
}

EVT_PT = {
    "hurt": "ferimentos", "bleeding": "sangramento", "sickness": "enjoo",
    "zombie_indoor": "zumbis dentro de casa", "zombie_back": "ataques pelas costas",
    "stealth_broken": "furtividade quebrada", "panic": "pânico",
    "weapon_jammed": "arma travada", "ammo_empty": "munição esgotada",
    "exhaustion": "exaustão", "hunger": "fome", "thirst": "sede", "nightmare": "pesadelos",
}
NEED_PT = {"bleeding": "sangramento", "hunger": "fome", "thirst": "sede"}
NEED_CAT = {"bleeding": "saude", "hunger": "suprimentos", "thirst": "suprimentos"}


def determine_survival_strategy(profile: dict, kf: KnowledgeFilter,
                                avoid_focus: str = None, max_directions: int = 3) -> dict:
    known = kf.all_categories()
    base = STAGE_ORDER[profile["stage"]]
    order = [c for c in base if (not known or c in known)] + [c for c in known if c not in base]

    loot = profile["loot"]
    found_lower = {i.lower() for items in loot.values() for i in items}

    scored = []
    for idx, cat in enumerate(order):
        score = (len(order) - idx) * 0.5          # peso da etapa de vida
        reasons = []

        for evt, n in profile["incidents"].items():
            if EVENT_CATEGORY_MAP.get(evt) == cat:
                score += 3 * min(n, 3)
                reasons.append(f"{EVT_PT.get(evt, evt)} ({n}x) hoje")

        for need in profile["unresolved"]:
            if NEED_CAT.get(need) == cat:
                score += 4
                reasons.append(f"{NEED_PT[need]} não chegou a ser resolvido(a)")

        if cat in loot:
            score -= 1
            ja_tenho = loot[cat]
        else:
            score += 2
            ja_tenho = []
            reasons.append("nada foi encontrado nessa área hoje")

        if avoid_focus and cat == avoid_focus:
            score -= 1.5

        if not reasons:
            reasons.append("vale manter essa área em dia")

        scored.append((score, idx, cat, reasons, ja_tenho))

    scored.sort(key=lambda x: (-x[0], x[1]))

    directions = []
    for score, _, cat, reasons, ja_tenho in scored[:max_directions]:
        info = kf.get_category(cat)
        acoes = list(info.get("acoes_validas", []))
        itens = [i for i in info.get("itens_reais", []) if i.lower() not in found_lower]
        directions.append({
            "categoria": cat,
            "descricao_categoria": info.get("descricao", ""),
            "motivo": "; ".join(reasons),
            "ja_encontrado": ja_tenho,
            "acoes": random.sample(acoes, min(2, len(acoes))),
            "itens": random.sample(itens, min(3, len(itens))),
            "score": round(score, 1),
        })

    return {"foco": directions[0]["categoria"] if directions else "suprimentos", "direcoes": directions}
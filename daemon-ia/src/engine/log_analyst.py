"""
Passo 1 do Pipeline: transforma a timeline do dia em um PERFIL de fatos (determinístico).
Sem LLM: rápido, sem timeout e sem alucinação.
"""
from collections import Counter, defaultdict
from src.engine.knowledge_filter import KnowledgeFilter, short_item, EVENT_CATEGORY_MAP

INCIDENT_EVENTS = [
    "hurt", "bleeding", "sickness", "zombie_indoor", "zombie_back", "stealth_broken",
    "panic", "weapon_jammed", "ammo_empty", "exhaustion", "hunger", "thirst", "nightmare",
]
NEED_PAIRS = {"bleeding": "bleeding_resolved", "hunger": "hunger_resolved", "thirst": "thirst_resolved"}


def get_stage(days) -> str:
    if days is None or days < 7:
        return "inicio"
    if days < 30:
        return "meio"
    return "avancado"


def build_day_profile(events: list[dict], player_status: dict, kf: KnowledgeFilter) -> dict:
    counts = Counter(e.get("type") for e in events)

    loot = defaultdict(list)
    for e in events:
        if e.get("type") == "loot_rare":
            detail = e.get("detail", "")
            name = short_item(detail)
            cat = kf.classify_item(detail) or "outros"
            if name and name not in loot[cat]:
                loot[cat].append(name)

    incidents = {t: counts[t] for t in INCIDENT_EVENTS if counts.get(t)}
    unresolved = [need for need, res in NEED_PAIRS.items() if counts.get(need, 0) > counts.get(res, 0)]

    days = player_status.get("days")
    hours = player_status.get("hours")
    if days is None and hours is not None:
        days = int(hours) // 24

    return {
        "total_events": len(events),
        "counts": dict(counts),
        "loot": dict(loot),
        "incidents": incidents,
        "unresolved": unresolved,
        "calm": not incidents,
        "days": days,
        "hours": hours,
        "stage": get_stage(days),
        "profession": player_status.get("profession", "Sobrevivente"),
        "perks": player_status.get("perks", {}),
    }
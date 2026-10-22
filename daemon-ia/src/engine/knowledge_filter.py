"""
Filtro seletivo de conhecimento (Query-driven filtering) + classificação de itens por categoria.
"""
import json
import re
from pathlib import Path
from src.config import GAME_KNOWLEDGE_FILE

EVENT_CATEGORY_MAP = {
    "hurt": "saude",
    "bleeding": "saude",
    "sickness": "saude",
    "zombie_indoor": "fortificacao",
    "zombie_back": "fortificacao",
    "stealth_broken": "fortificacao",
    "panic": "fortificacao",
    "loot_rare": "suprimentos",
    "hunger": "suprimentos",
    "thirst": "suprimentos",
    "exhaustion": "veiculos_energia",
    "weapon_jammed": "combate_manutencao",
    "ammo_empty": "combate_manutencao",
}

# Prefixo vindo do Lua ("Weapon:Barra") -> categoria provável
ITEM_PREFIX_MAP = {"weapon": "combate_manutencao", "food": "suprimentos"}

# Palavras-chave de apoio quando o item não está em itens_reais
ITEM_KEYWORDS = {
    "saude": ["curativo", "bandagem", "atadura", "analgés", "antibiót", "desinfet", "sutura", "pílula", "remédio", "kit médico"],
    "suprimentos": ["lata", "feijão", "água", "chocolate", "doce", "comida", "carne", "abridor", "garrafa", "pão", "fruta"],
    "combate_manutencao": ["taco", "barra", "faca", "machado", "pistola", "munição", "espingarda", "arma", "revólver", "pé de cabra"],
    "fortificacao": ["tábua", "prego", "martelo", "serra", "arame", "madeira", "pá"],
    "veiculos_energia": ["gerador", "gasolina", "galão", "bateria", "chave de roda"],
}


def short_item(detail: str) -> str:
    """'Weapon:Taco de Basebol (Ensanguentada)' -> 'Taco de Basebol'."""
    if not detail:
        return ""
    raw = detail.split(":", 1)[1] if ":" in detail else detail
    cleaned = re.sub(r"\s*\(.*?\)", "", raw).strip()
    return cleaned or raw.strip()


class KnowledgeFilter:
    def __init__(self, knowledge_path: Path = GAME_KNOWLEDGE_FILE):
        self.knowledge_path = knowledge_path
        self._cache = self._load_json()

    def _load_json(self) -> dict:
        if not self.knowledge_path.exists():
            return {}
        try:
            with open(self.knowledge_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[KNOWLEDGE ERRO] Falha ao carregar game_knowledge.json: {e}")
            return {}

    def _categories(self) -> dict:
        return self._cache.get("categorias", {})

    def all_categories(self) -> list[str]:
        return list(self._categories().keys())

    def get_category(self, cat: str) -> dict:
        return self._categories().get(cat, {})

    def get_filtered_knowledge(self, requested_categories: list[str]) -> dict:
        cats = self._categories()
        return {
            "versao": self._cache.get("versao", "1.0"),
            "jogo": self._cache.get("jogo", "Project Zomboid"),
            "categorias_filtradas": {c: cats[c] for c in requested_categories if c in cats},
        }

    def classify_item(self, detail: str):
        """Devolve a categoria do item (ou None). Ordem: itens_reais > palavras-chave > prefixo."""
        name = short_item(detail).lower()
        if not name:
            return None
        cats = self._categories()

        for cat, data in cats.items():
            for real in data.get("itens_reais", []):
                r = real.lower()
                if r and (r in name or name in r):
                    return cat

        for cat, words in ITEM_KEYWORDS.items():
            if (not cats or cat in cats) and any(w in name for w in words):
                return cat

        if ":" in detail:
            prefix = detail.split(":", 1)[0].strip().lower()
            cat = ITEM_PREFIX_MAP.get(prefix)
            if cat and (not cats or cat in cats):
                return cat
        return None

    def map_events_to_categories(self, event_types: list[str]) -> list[str]:
        matched = {EVENT_CATEGORY_MAP[e] for e in event_types if e in EVENT_CATEGORY_MAP}
        if not matched:
            matched.add("suprimentos")
        return list(matched)
"""
Configuração ISOLADA do módulo NPC. Não altera src/config.py.
"""
from src.config import (
    EVENTS_FILE, MODELOS_VOZ, SPEAKER_WAV, NPC_MEMORY_FILE,
    TTS_PARAMS_NORMAL, TTS_PARAMS_PANIC, TTS_PARAMS_SLOW,
)

NPC_ENABLED = True
NPC_NAME = "NPC"

# --- Arquivos de troca com o Lua (mesma pasta do TTS_events.txt) ---
LUA_DIR = EVENTS_FILE.parent
NPC_EVENTS_FILE = LUA_DIR / "NPC_events.txt"        # Lua    -> daemon
NPC_COMMANDS_FILE = LUA_DIR / "NPC_commands.txt"    # daemon -> Lua

# --- Voz própria (mesmo modelo XTTS, outro speaker_wav; sem VRAM extra) ---
NPC_VOICE_WAV = MODELOS_VOZ / "npc_voice.wav"      # se existir, é usada (clonagem de voz)
NPC_BUILTIN_SPEAKER = "Damien Black"                # senão: voz embutida do XTTS (NUNCA a do personagem)
NPC_FALLBACK_VOICE_WAV = SPEAKER_WAV                # sem uso (mantido por compatibilidade)

NPC_TTS_PARAMS = {
    "normal": {**TTS_PARAMS_NORMAL, "speed": 1.25},
    "danger": {**TTS_PARAMS_PANIC},
    "calm":   {**TTS_PARAMS_SLOW, "speed": 1.1},
}

# --- Modos canônicos (o adapter Lua traduz para o mod base) ---
MODES = ("seguir", "ficar", "defender", "saquear")

# --- Decisão de modo ---
MANUAL_OVERRIDE_S = 120        # depois de uma ordem sua, a IA não mexe no modo por este tempo
MODE_MIN_INTERVAL_S = 20       # histerese: no mínimo isto entre trocas automáticas
LLM_DECISION_COOLDOWN_S = 45   # desempate por LLM, no máximo 1 vez por este tempo
LOW_HP = 30                    # % de vida do NPC considerada crítica
PLAYER_LOW_HP = 40             # % de vida do jogador que aciona proteção
STATE_STALE_S = 30             # sem 'state' por este tempo => NPC considerado ausente

# --- Fala ---
IDLE_CHATTER = True
IDLE_MIN_S = 90
IDLE_MAX_S = 180
STATIC_FIRST_RATIO = 0.5       # chance de usar frase estática (cache) antes da LLM

PRIORITY = {"danger": 0, "order": 1, "chat": 1, "event": 2, "idle": 3}
TTL_S = {"danger": 6, "order": 15, "chat": 30, "event": 10, "idle": 20}
KEY_COOLDOWN_S = {
    "hurt": 8, "kill": 25, "loot": 10, "no_ammo": 20,
    "low_hp": 30, "idle": 60, "danger": 15, "decision": 15,
}
DEFAULT_KEY_COOLDOWN_S = 10
MAX_QUEUE = 3

POLL_INTERVAL_S = 0.25
COMMANDS_KEEP_LINES = 20

# --- Frases estáticas (pré-geradas em cache no arranque) ---
NPC_PHRASES = {
    "mode_seguir":   ["Certo, tô logo atrás de você.", "Pode ir, eu te acompanho.", "Beleza, te sigo."],
    "mode_ficar":    ["Fico aqui, pode ir.", "Beleza, seguro a posição."],
    "mode_defender": ["Fica atrás de mim.", "Deixa que eu cubro você.", "Pode deixar, eu cuido deles."],
    "mode_saquear":  ["Vou ver o que dá pra pegar.", "Deixa eu dar uma olhada nas coisas."],
    "fetch_go":   ["Deixa comigo, vou procurar {item}.", "Vou atrás de {item}."],
    "fetch_none": ["Não achei nada por aqui.", "Procurei e não tem nada."],
    "fetch_abort": ["Tem perigo, volto já.", "Deu ruim, desisti."],
    "joined":  ["Tô com você.", "Bora, eu vou junto."],
    "hurt":    ["Ai, me pegaram!", "Droga, isso doeu!", "Tô ferido!"],
    "low_hp":  ["Tô muito mal, preciso de ajuda.", "Não aguento muito mais."],
    "kill":    ["Mais um a menos.", "Esse não levanta mais.", "Foi um."],
    "no_ammo": ["Acabou a munição!", "Tô sem bala!"],
    "danger":  ["Cuidado, tem zumbi!", "Eles tão chegando!"],
    "idle":    ["Tá muito quieto por aqui.", "Será que ainda tem gente por aí?"],
    "busy":    ["Agora não, tem zumbi!"],
    "unknown": ["Hm, não entendi. Repete?"],
    "loot":    ["Achei {item}.", "Olha só, {item}.", "{item}, pode ser útil."],
}
PRECACHE_LOOT_ITEMS = ["Lata de Feijão", "Água", "Taco de Basebol", "combustível", "comida", "remédios"]

# Palavras proibidas em falas de loot (o NPC só pegou o item; não consumiu)
LOOT_BANNED = [
    "comi", "comendo", "comeu", "devorei", "saboreei", "bebi", "sabor", "saboroso", "saborosa",
    "delicioso", "deliciosa", "delícia", "gostoso", "gostosa", "melhor que", "semanas",
    "raro", "rara", "raros", "raras", "raríssimo", "raríssima",
]
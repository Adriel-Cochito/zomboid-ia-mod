"""
Configurações globais, caminhos, parâmetros de TTS, cooldowns e frases estáticas
do sistema de voz e cognição do Project Zomboid.
"""
import shutil
from pathlib import Path

from src.user_settings import app_dir, zomboid_lua_dir

# --- CONFIGURAÇÃO OLLAMA & LLM ---
OLLAMA_URL = "http://localhost:11434/api/generate"

# OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_MODEL = "gemma2:2b"

USE_LLM = True

# Endpoint de CHAT (aceita system prompt; muito melhor que /generate para modelos pequenos)
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
LLM_TIMEOUT_S = 10
LLM_TEMPERATURE = 1.0      # mais alto = mais criativo (baixe p/ 0.8 se ficar maluco)
LLM_HISTORY = 10           # quantas falas recentes DO MESMO EVENTO a LLM deve evitar

# --- CAMINHOS DE DIRETÓRIOS E FICHEIROS ---
# app_dir() é a raiz de daemon-ia no código e a pasta do .exe quando empacotado.
BASE = app_dir()
EVENTS_FILE = zomboid_lua_dir() / "TTS_events.txt"
AUDIOS_GERADOS = BASE / "audios_gerados"
MODELOS_VOZ = BASE / "modelos_voz"
VOZ_MODELO = "cognition_ffa15128344428778992473b5b89a0c9.wav"
SPEAKER_WAV = MODELOS_VOZ / VOZ_MODELO
CACHE_DIR = AUDIOS_GERADOS

DATA_DIR = BASE / "data"
MISSIONS_FILE = DATA_DIR / "missions.json"
NPC_MEMORY_FILE = DATA_DIR / "npc_memory.json"
_LEGACY_DATA = Path(__file__).resolve().parent / "data"


def _seed_runtime_file(name: str) -> None:
    """Copia missions/memória de src/data na primeira vez. O bundle não grava dentro de si."""
    dest = DATA_DIR / name
    src = _LEGACY_DATA / name
    if dest.exists() or not src.is_file():
        return
    try:
        if dest.resolve() == src.resolve():
            return
    except OSError:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


_seed_runtime_file("missions.json")
_seed_runtime_file("npc_memory.json")

GAME_KNOWLEDGE_FILE = Path(__file__).parent / "game_knowledge" / "game_knowledge.json"

LANGUAGE = "pt"

# --- PARÂMETROS DE ÁUDIO (XTTS-v2) ---

# Parâmetros de alta urgência e pânico (fala rápida, ofegante e expressiva)
TTS_PARAMS_PANIC = dict(
    temperature=1.0,        # Mais variação vocal e emoção
    length_penalty=0.60,    # Força frases mais rápidas e curtas
    repetition_penalty=2.5,
    speed=1.65,             # Fala significativamente mais rápida
    top_k=50,
    top_p=0.88,
)


# Parâmetros normais (fala rápida e urgente para combate/clima)
TTS_PARAMS_NORMAL = dict(
    temperature=0.95,
    length_penalty=0.80,
    repetition_penalty=2.5,
    speed=1.5,
    top_k=50,
    top_p=0.84,
)

# Parâmetros para descanso / reflexão (fala mais lenta, filosófica e calma)
TTS_PARAMS_SLOW = dict(
    temperature=0.75,
    length_penalty=0.50,
    repetition_penalty=2.5,
    speed=1.0,  
    top_k=50,
    top_p=0.2,
)

# Parâmetros exclusivos para Loot (velocidade mais lenta, temperatura normal)
TTS_PARAMS_LOOT = dict(
    temperature=0.95,
    length_penalty=0.80,
    repetition_penalty=2.5,
    speed=1.1,  
    top_k=50,
    top_p=0.84,
)

# --- CONFIGURAÇÕES DE TEMPO E FILA ---
POLL_INTERVAL_S = 0.05
MAX_EVENT_AGE_S = 15.0   
MAX_QUEUE = 1            

# --- COOLDOWNS INDEPENDENTES POR EVENTO (em segundos) ---
EVENT_COOLDOWN_S = {
    "zombie_back": 30.0,
    "zombie_indoor": 25.0,
    "hurt": 8.0,
    "rain": 120.0,
    "rest": 30.0,  # Reduzido ligeiramente para facilitar testes de descanso
    "bleeding": 35.0,
    "panic": 25.0,
    "exhaustion": 30.0,
    "soaked": 180.0,
    "nightmare": 10.0,
    "loot_rare": 10.0,
    "combat_clear": 10.0,
    "combat_many": 15.0,
    "hunger": 40.0,
    "thirst": 40.0,
    "boredom": 60.0,
    "sickness": 45.0,
    "stealth_broken": 15.0,
    "weapon_jammed": 10.0,
    "ammo_empty": 15.0,
    "bleeding_resolved": 45.0,
    "hunger_resolved": 60.0,
    "thirst_resolved": 60.0,
}

# --- FRASES ESTÁTICAS E FALLBACKS DE SEGURANÇA ---
PHRASES = {
    "zombie_back": [
        "Atrás de mim!",
        "Preciso ter cuidado!",
        "Droga!",
        "Preciso sair daqui!",
        "Corre!",
        "Tão na minha cola!",
        "Ah, não!",
        "Eles tão perto!",
        "Merda, tem mais!",
        "Fecha o cerco não!"
    ],
    "zombie_indoor": [
        "Barulho!",
        "Silêncio!",
        "Tem gente...",
        "Ouviram isso?",
        "Esconde!",
        "Alguém na porta!",
        "Passos por perto.",
        "Xiu, quieto."
    ],
    "hurt": [
        "Aaii!",
        "Droga!",
        "Ferido!",
        "Sangrando!",
        "Isso dói!",
        "Me pegaram!",
        "Droga de ferimento!",
        "Merda, machuquei!"
    ],
    "rain": [
        "Chuva forte.",
        "Molhando tudo.",
        "Tempestade.",
        "Droga de chuva.",
        "Vai abafar o som.",
        "Água caindo forte."
    ],
}

# --- FALAS CRIATIVAS (LLM) ---
PERSONA = ("Você é o sobrevivente de um apocalipse zumbi, falando sozinho em voz alta. "
           "Tom: seco, irônico, cansado, às vezes bem-humorado. Português do Brasil, coloquial.")

# O QUE aconteceu (a LLM nao ve o jogo: so sabe isto). {item} = nome curto do item.
EVENT_CONTEXT = {
    "loot_rare":      "Você acabou de pegar um item e guardar na mochila. Item: {item}.",
    "zombie_back":    "Você é um humano e um monstro zumbi te pegou de surpresa pelas costas! Você está assustado.",
    "zombie_indoor":  "Um zumbi apareceu de repente dentro da casa com você! Você é a vítima humana.",
    "hurt":           "Você levou uma mordida ou arranhão de zumbi e está sentindo muita dor física!",
    "rain":           "Começou a chover forte.",
    "panic":          "Você está cercado por vários zumbis e vai morrer se não fugir!",
    "exhaustion":     "Você está exausto, sem fôlego e com as pernas pesadas.",
    "soaked":         "Você está completamente encharcado pela chuva e com frio.",
    "nightmare":      "Você acordou assustado de um pesadelo no escuro.",
    "combat_clear":   "Você acabou de matar o último zumbi por perto e a área ficou limpa por enquanto.",
    "combat_many":    "Você matou um zumbi, mas ainda há vários outros cercando o local.",
    "hunger":         "Você está com muita fome, a barriga roncando.",
    "thirst":         "Você está com sede extrema, garganta seca.",
    "boredom":        "Você está entediado e farto de ficar isolado.",
    "sickness":       "Você está enjoado, com náuseas e mal-estar.",
    "stealth_broken": "Você tentou se esconder, mas um zumbi te descobriu.",
    "weapon_jammed":  "Sua arma de fogo travou no meio do perigo.",
    "ammo_empty":     "Sua arma ficou sem munição.",
    "bleeding": "Você percebeu que está sangrando por causa de um ferimento recente.",
    "bleeding_resolved": "Você acabou de fazer um curativo e o sangramento estancou com sucesso.",
    "hunger_resolved": "Você acabou de comer e a fome passou, sentindo um pouco de alívio.",
    "thirst_resolved": "Você bebeu água e a sede extrema foi saciada.",
}
# Palavras que NAO podem aparecer na fala desse evento (evita alucinacao de "zumbi" no loot)
BANNED_WORDS = {"loot_rare": ["zumbi", "zumbis", "morto", "mortos"]}
# Regra extra de prompt por evento
EXTRA_RULES = {"loot_rare": "Comente o item de forma natural e variada (opinião, utilidade, humor). "
                            "NÃO mencione zumbis. Pode usar só o nome curto do item."}
# Fallback se a LLM falhar (so eventos com detalhe)
FALLBACK_TEMPLATES = {"loot_rare": ["Um {item}.", "Sorte achar um {item}.", "Caraca! um {item}.", "{item}, vai ser útil." , "{item}, Pouco importante?"]}

# --- EXEMPLOS DE ESTILO (few-shot) ---------------------------------------------------
# Modelo pequeno (3B) acerta MUITO mais quando ve exemplos do tom/tamanho desejado.
# A LLM cria uma fala NOVA parecida (nao copia). Edite/adicione a vontade.
# {item} = nome curto do item (so loot).
EVENT_EXAMPLES = {
    "loot_rare":      ["Boa, {item} vai ser útil.", "Finalmente achei {item}.", "Hmm, {item}... guardo pra depois.", "Olha só, {item}. Nada mal."],
    "zombie_back":    ["Droga, tem um atrás de mim!", "Tão na minha cola, corre!", "Sai de perto, seu maldito!", "Eles me alcançaram!"],
    "zombie_indoor":  ["Tem alguma coisa aqui dentro!", "Ouvi um barulho na casa...", "Quieto, tem um zumbi aqui.", "Como esse bicho entrou?"],
    "hurt":           ["Ai, isso dói demais!", "Merda, me pegaram!", "Aaah, que dor!", "Droga, eu me machuquei!"],
    "bleeding":       ["Tô sangrando, preciso de um curativo!", "Merda, o ferimento abriu!", "Isso não para de sangrar!", "Preciso estancar isso logo!"],
    "panic":          ["São zumbis demais!", "Preciso sair daqui agora!", "Não, não, não, tem muitos!", "Vou morrer aqui!"],
    "rain":           ["Droga, começou a chover.", "Lá vem tempestade.", "A chuva vai abafar o barulho.", "Mais água caindo, que ótimo."],
    "exhaustion":     ["Não aguento mais correr.", "Tô sem fôlego.", "Minhas pernas estão pesadas.", "Preciso descansar um pouco."],
    "soaked":         ["Tô encharcado e morrendo de frio.", "Essa roupa tá toda molhada.", "Que frio, tô ensopado."],
    "nightmare":      ["Que pesadelo horrível!", "Acordei com o coração disparado.", "Foi só um sonho... foi só um sonho."],
    "combat_clear":   ["Pronto, acabou por enquanto.", "Esse foi o último, ufa.", "Por aqui tá limpo.", "Caiu o último, respira."],
    "combat_many":    ["Ainda tem um monte deles!", "Matei um, mas vêm mais!", "Eles não acabam nunca!", "Tá cheio de zumbi aqui!"],
    "hunger":         ["Tô morrendo de fome.", "Minha barriga não para de roncar.", "Preciso comer alguma coisa.", "Será que sobrou comida?"],
    "thirst":         ["Tô com a garganta seca.", "Preciso beber água.", "Que sede, meu Deus.", "Será que tem água por aqui?"],
    "boredom":        ["Que tédio, não aguento mais.", "Esse silêncio me enlouquece.", "Faz tempo que nada acontece.", "Preciso fazer alguma coisa."],
    "sickness":       ["Tô enjoado, vou passar mal.", "Meu estômago tá revirando.", "Não tô me sentindo bem."],
    "stealth_broken": ["Droga, me viram!", "Ele me descobriu!", "Meu esconderijo já era.", "Foi notado, corre!"],
    "weapon_jammed":  ["Minha arma travou, droga!", "Travou, agora não!", "Essa arma me abandonou!"],
    "ammo_empty":     ["Acabou a munição!", "Tô sem bala!", "Pente vazio, droga!"],
    "bleeding_resolved": ["Ufa, parou de sangrar.", "O curativo segurou.", "Agora sim, estancou."],
    "hunger_resolved":   ["Ah, agora sim, matei a fome.", "Isso caiu bem.", "Já tô me sentindo melhor."],
    "thirst_resolved":   ["Ahh, que alívio, água!", "Agora sim, a sede passou.", "Bebi e já melhorou."],
}
# Palavras informais que o corretor ortografico nao conhece (nao serao tratadas como "inventadas")
ALLOWED_WORDS = {"tô", "tá", "tão", "né", "pra", "pro", "ufa", "aaah", "aah", "ahh", "ai", "ei", "hmm",
                 "merda", "caramba", "droga", "zumbi", "zumbis", "curativo", "ei", "opa"}
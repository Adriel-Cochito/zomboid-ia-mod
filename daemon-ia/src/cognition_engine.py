"""
Motor cognitivo responsável por interagir com o Ollama (Qwen 2.5:3b),
gerando tanto frases avulsas de eventos quanto a reflexão dividida em blocos
(físico, tático e resumo/missões em JSON) para o momento de descanso,
guiada pela base de conhecimento estruturada do Project Zomboid.
"""
import json
import re
import time
import subprocess
import urllib.request
import random
from collections import deque
from src.config import (
    OLLAMA_URL, OLLAMA_CHAT_URL, OLLAMA_MODEL, USE_LLM,
    LLM_TIMEOUT_S, LLM_TEMPERATURE, LLM_HISTORY,
    PERSONA, EVENT_CONTEXT, BANNED_WORDS, EXTRA_RULES,
    GAME_KNOWLEDGE_FILE, EVENT_EXAMPLES, ALLOWED_WORDS
)

def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)

def load_game_knowledge() -> dict:
    """Carrega a base de conhecimento estruturada do Project Zomboid."""
    if not GAME_KNOWLEDGE_FILE.exists():
        return {}
    try:
        with open(GAME_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[CONHECIMENTO ERRO] Falha ao ler game_knowledge.json: {e}")
        return {}
        
def ensure_ollama_running():
    """Verifica se o servidor Ollama está ativo; se não estiver, inicia-o em segundo plano."""
    ollama_ping_url = "http://localhost:11434/api/version"
    
    try:
        with urllib.request.urlopen(ollama_ping_url, timeout=10.0) as res:
            if res.status == 200:
                log("[SYSTEM] Ollama já está a rodar em segundo plano.")
                return True
    except Exception:
        log("[SYSTEM] Ollama não foi detetado. A iniciar o servidor Ollama...")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        
        for _ in range(10):
            time.sleep(1)
            try:
                with urllib.request.urlopen(ollama_ping_url, timeout=10.0) as res:
                    if res.status == 200:
                        log("[SYSTEM] Servidor Ollama iniciado com sucesso!")
                        return True
            except Exception:
                pass
        log("[SYSTEM AVISO] O Ollama demorou a responder, mas o processo foi lançado.")
    except Exception as e:
        log(f"[SYSTEM ERRO] Não foi possível iniciar o Ollama automaticamente: {e}")
        return False

def warmup_ollama():
    if not USE_LLM:
        return
    
    ensure_ollama_running()

    log(f"[LLM] A aquecer o modelo Ollama ({OLLAMA_MODEL}) na VRAM...")
    t_start = time.time()
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": "Olá",
            "stream": False,
            "options": {"num_predict": 2}
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10.0) as res:
            log(f"[LLM] Modelo Ollama aquecido e pronto na VRAM! (Demorou {time.time() - t_start:.2f}s)")
    except Exception as e:
        log(f"[LLM AVISO] Ollama indisponível no arranque ({e}).")

_history = {}   # evento -> ultimas falas (para a LLM nao repetir)

def short_item(detail: str) -> str:
    """'Weapon:Taco de Basebol de Metal (Ensanguentada)' -> 'Taco de Basebol de Metal'."""
    if not detail:
        return ""
    parts = detail.split(":", 1)
    item_raw = parts[1] if len(parts) > 1 else parts[0]
    d = re.sub(r"\s*\(.*?\)", "", item_raw).split(":")[0].strip()   # tira (..) e subtitulos "Titulo: Subtitulo"
    return d or item_raw.strip()

try:  # corretor ortografico PT offline (pip install pyspellchecker). Opcional.
    from spellchecker import SpellChecker
    _spell = SpellChecker(language="pt")
except Exception:
    _spell = None
    print("[LLM AVISO] pyspellchecker ausente: sem filtro de palavras inventadas. (pip install pyspellchecker)")


def has_invented_words(text: str, extra_ok=()) -> list:
    """Palavras que nao existem em portugues (ex.: 'AOZOIOUUU', 'PERTIMBO')."""
    if _spell is None:
        return []
    ok = set(ALLOWED_WORDS) | {w.lower() for w in extra_ok}
    words = re.findall(r"[^\W\d_]+", text.lower())
    return [w for w in words if w not in ok and w not in _spell]


def generate_ollama_phrase(event: str, detail: str = "", last_phrase: str = "") -> str:
    """Fala curta e coerente para um evento (few-shot + validacao). None => usa fallback."""
    if not USE_LLM:
        return None

    item = short_item(detail)
    if event == "loot_rare" and not item:
        return None  # sem nome de item a LLM so inventa ("item especial"); deixa o fallback
    hist = _history.setdefault(event, deque(maxlen=LLM_HISTORY))
    examples = [e.format(item=item or "isso") for e in EVENT_EXAMPLES.get(event, [])]

    ctx = EVENT_CONTEXT.get(event) or f"Aconteceu o evento '{event}'."
    if "{item}" in ctx:
        ctx = ctx.format(item=item)

    system_prompt = (
        "Você é um sobrevivente de um apocalipse zumbi falando sozinho em voz alta. "
        "Escreva em português do Brasil correto, coloquial, como uma pessoa de verdade falaria. "
        "Use APENAS palavras que existem. Responda só com a fala, sem aspas e sem explicações."
    )
    user_prompt = f"Situação: {ctx}\nEscreva UMA fala curta (3 a 9 palavras) reagindo a isso."
    if examples:
        user_prompt += "\nExemplos do estilo (NÃO copie, crie uma fala nova parecida):\n" + "\n".join(f"- {e}" for e in examples)
    if hist:
        user_prompt += "\nNÃO repita estas falas recentes: " + " | ".join(hist)
    user_prompt += "\nFala:"

    payload = {
        "model": OLLAMA_MODEL, "stream": False, "keep_alive": "30m",
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_prompt}],
        # repeat_penalty alto (1.3) distorcia o portugues e gerava palavras inventadas
        "options": {"temperature": 0.8, "top_p": 0.9, "top_k": 40,
                    "repeat_penalty": 1.1, "num_predict": 30},
    }

    item_words = [w.lower() for w in re.findall(r"[^\W\d_]{4,}", item)]
    banned = BANNED_WORDS.get(event, [])
    known_examples = {e.lower() for e in examples}

    for _ in range(3):
        try:
            req = urllib.request.Request(
                OLLAMA_CHAT_URL, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_S) as res:
                txt = json.loads(res.read().decode("utf-8"))["message"]["content"]
        except Exception as e:
            log(f"[LLM ERRO] Falha ao comunicar com Ollama para o evento {event}: {e}")
            return None

        txt = txt.strip().split("\n")[0].strip().strip("\"\u201c\u201d'` ")
        txt = re.sub(r"^(fala|resposta|sobrevivente)\s*[:\-]\s*", "", txt, flags=re.IGNORECASE)
        txt = re.sub(r"[^\w\s.,!?;:'\-\u2026]", "", txt)          # sem emoji/simbolos
        txt = re.sub(r"\s+", " ", txt).strip()
        low = txt.lower()

        reason = None
        if not (2 <= len(txt.split()) <= 12):
            reason = "tamanho"
        elif any(re.search(rf"\b{w}\b", low) for w in banned):
            reason = "palavra proibida"
        elif low in known_examples or low in (h.lower() for h in hist):
            reason = "repetida/copiada"
        elif event == "loot_rare" and item_words and not any(w in low for w in item_words):
            reason = "nao cita o item"
        else:
            bad = has_invented_words(txt, extra_ok=item_words)
            if bad:
                reason = f"palavras inventadas {bad}"
        if reason:
            log(f"[LLM] descartada ({reason}): \"{txt}\"")
            continue

        # Urgencia vem dos parametros do XTTS (speed/temperature), nao de CAIXA ALTA
        hist.append(txt)
        return txt
    return None


def generate_reflection_blocks(events_list: list) -> dict:
    """
    Processa a timeline acumulada consultando a base de conhecimento oficial
    do Project Zomboid para gerar os blocos de reflexão calma e missões estruturadas.
    """
    if not USE_LLM or not events_list:
        return {
            "fisiologia": "O corpo está um pouco mais descansado.",
            "tatico": "A zona parece calma por enquanto.",
            "resumo": "Vou ficar atento aos arredores.",
            "missoes": [{"titulo": "Recuperar energias", "descricao": "Descansar e avaliar mantimentos.", "categoria": "suprimentos"}]
        }

    knowledge = load_game_knowledge()
    regras_texto = ""
    if knowledge and "categorias" in knowledge:
        regras_texto = "REGRAS E AÇÕES OFICIAIS PERMITIDAS NO JOGO:\n"
        for cat_name, cat_data in knowledge["categorias"].items():
            regras_texto += f"- [{cat_name.upper()}] {cat_data['descricao']}\n"
            regras_texto += f"  Ações válidas: {', '.join(cat_data['acoes_validas'])}. Itens reais: {', '.join(cat_data['itens_reais'][:6])}\n"

    events_summary = "\n".join([f"- [{time.strftime('%H:%M', time.localtime(e['timestamp']))}] Evento: {e['event']} (Detalhe: {e['detail']})" for e in events_list])

    prompt = f"""Você é o motor narrativo de Project Zomboid.
{regras_texto}

REGISTRO DOS ACONTECIMENTOS RECENTES:
{events_summary}

Gere uma resposta em formato JSON puro com 4 chaves exatas para um momento calmo de reflexão:
1. "fisiologia": Uma frase descritiva completa (8 a 14 palavras) comentando o estado físico ou cansaço. Termine a frase pontuada corretamente, sem cortes.
2. "tatico": Uma frase descritiva completa (8 a 14 palavras) comentando a segurança ou perigos ao redor. Termine a frase pontuada corretamente, sem cortes.
3. "resumo": Uma frase de encerramento completa (8 a 14 palavras) refletindo sobre a sobrevivência. Termine a frase pontuada corretamente, sem cortes.
4. "missoes": Uma lista contendo 1 ou 2 objetos JSON com as chaves "titulo", "descricao" e "categoria" para missões práticas.

Retorne APENAS o JSON válido, sem blocos de código markdown adicionais. Exemplo de estrutura:
{{"fisiologia": "...", "tatico": "...", "resumo": "...", "missoes": [{{"titulo": "...", "descricao": "...", "categoria": "Saúde"}}]}}
JSON:"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
            "num_predict": 400  # Aumentado para garantir frases completas sem cortes
        }
    }

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15.0) as res:
            body = res.read().decode("utf-8")
            data = json.loads(body)
            raw_resp = data.get("response", "").strip()
            
            if raw_resp.startswith("```json"):
                raw_resp = raw_resp[7:]
            if raw_resp.endswith("```"):
                raw_resp = raw_resp[:-3]
            raw_resp = raw_resp.strip()

            parsed = json.loads(raw_resp)
            defaults = {
                "fisiologia": "O corpo está um pouco mais descansado.",
                "tatico": "A área aparenta estar calma.",
                "resumo": "Amanhã será um novo dia de luta.", 
                "missoes": [{"titulo": "Procurar mantimentos", "descricao": "Achar comida e água na vizinhança.", "categoria": "suprimentos"}]
            }
            for k, v in defaults.items():
                if not parsed.get(k):
                    parsed[k] = v
            return parsed
    except Exception as e:
        log(f"[LLM ERRO] Falha ao gerar reflexão cognitiva estruturada: {e}")
        return {
            "fisiologia": "O corpo está um pouco mais descansado.",
            "tatico": "A área aparenta estar calma.",
            "resumo": "Amanhã será um novo dia de luta.",
            "missoes": [{"titulo": "Procurar mantimentos", "descricao": "Achar comida e água na vizinhança.", "categoria": "suprimentos"}]
        }

def generate_wake_up_speech(missions_list: list) -> str:
    """
    Gera uma fala com tom sugestivo e focada na sensação de repouso físico,
    evitando comandos imperativos.
    """
    if not missions_list:
        return "Sinto-me um pouco mais descansado... Talvez devesse apenas manter a vigilância por enquanto."

    titulo = missions_list[0].get("titulo", "").lower()
    
    opcoes = [
        f"O corpo está um pouco mais descansado... Talvez a prioridade pudesse ser {titulo}.",
        f"Depois deste descanso, sinto-me com um pouco mais de energia. Valeria a pena focar em {titulo}.",
        f"Recuperei forças com o repouso. Quem sabe se tentássemos {titulo} agora."
    ]
    return random.choice(opcoes)
"""
Serviço isolado para comunicação com a API do Ollama (Chat endpoint).
Responsável por gerar respostas estruturadas aplicando a persona e histórico.
"""
import urllib.request
import json
import time
from collections import deque
from src.config import (
    OLLAMA_CHAT_URL, OLLAMA_MODEL,
    LLM_TIMEOUT_S, LLM_TEMPERATURE, LLM_HISTORY, PERSONA
)

# Histórico recente por evento para evitar repetições idênticas
event_histories = {}

JSON_SYSTEM_PROMPT = (
    "Você é um assistente que responde estritamente em JSON válido, "
    "em português do Brasil, sem texto fora do JSON."
)

# Chamadas em JSON_MODE geram textos longos; precisam de mais tempo que as falas curtas
JSON_TIMEOUT_S = max(LLM_TIMEOUT_S, 30)


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[OLLAMA SERVICE] {msg}", flush=True)


def call_ollama_chat(event_type: str,
                     user_prompt: str,
                     system_override: str = None,
                     temperature: float = LLM_TEMPERATURE,
                     json_mode: bool = False) -> str:
    """
    Envia um prompt para o Ollama via /api/chat.

    - Modo normal: usa a PERSONA, o histórico anti-repetição e limpa aspas da resposta.
    - json_mode=True: força format=json, sem persona, sem histórico e sem
      remover aspas (senão o JSON seria destruído).
    """
    if system_override:
        sys_prompt = system_override
    elif json_mode:
        sys_prompt = JSON_SYSTEM_PROMPT
    else:
        sys_prompt = PERSONA

    history_context = ""
    if not json_mode:
        if event_type not in event_histories:
            event_histories[event_type] = deque(maxlen=LLM_HISTORY)

        history_list = list(event_histories[event_type])
        if history_list:
            history_context = (
                "\nO que você disse recentemente e NÃO DEVE REPETIR:\n- "
                + "\n- ".join(history_list)
            )

    messages = [
        {"role": "system", "content": sys_prompt + history_context},
        {"role": "user", "content": user_prompt}
    ]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }
    if json_mode:
        payload["format"] = "json"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    timeout = JSON_TIMEOUT_S if json_mode else LLM_TIMEOUT_S

    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                res_body = json.loads(response.read().decode("utf-8"))
                content = res_body.get("message", {}).get("content", "").strip()

                if not json_mode:
                    # Limpar aspas ou formatações extras que a LLM possa retornar
                    content = content.replace('"', '').replace('«', '').replace('»', '').strip()

                if content:
                    if not json_mode:
                        event_histories[event_type].append(content)
                    elapsed = time.time() - start_time
                    log(f"Resposta gerada em {elapsed:.2f}s para '{event_type}'")
                    return content
    except Exception as e:
        log(f"Erro ao comunicar com Ollama: {e}")

    return ""


def warmup_ollama_service():
    """Realiza o aquecimento do modelo na VRAM no arranque."""
    log(f"A aquecer o modelo Ollama ({OLLAMA_MODEL}) na VRAM...")
    start = time.time()
    res = call_ollama_chat("warmup", "Responda apenas com a palavra: 'PRONTO'.", temperature=0.1)
    if res:
        elapsed = time.time() - start
        log(f"Modelo Ollama aquecido e pronto na VRAM! (Demorou {elapsed:.2f}s)")
        return True
    log("Aviso: Aquecimento do Ollama falhou ou demorou demasiado.")
    return False
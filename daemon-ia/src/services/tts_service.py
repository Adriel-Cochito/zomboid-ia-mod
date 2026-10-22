"""
Pipeline de áudio responsável pela limpeza de texto (clean_text_for_tts),
gestão de cache com hash, carregamento do Coqui XTTS-v2 e reprodução.
"""
import time
import hashlib
import threading
import torch
import re
from pathlib import Path
from TTS.api import TTS
from src.config import CACHE_DIR, LANGUAGE
from src.user_settings import player_speaker_wav

def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def allow_tts_checkpoint_load():
    """PyTorch 2.6 recusa o checkpoint do XTTS com weights_only no padrão True."""
    if getattr(torch.load, "_tts_weights_ok", False):
        return
    original = torch.load

    def load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original(*args, **kwargs)

    load._tts_weights_ok = True
    torch.load = load


class AudioPipeline:
    def __init__(self, speaker_wav=None):
        self.tts_model = None
        self._lock = threading.Lock()  # fala de evento e reflexao nao se sobrepoem nem usam o XTTS juntas
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.speaker_wav = Path(speaker_wav) if speaker_wav else player_speaker_wav()
        
    def load_tts_model(self):
        """Carrega o modelo Coqui XTTS-v2 para a VRAM/Dispositivo se ainda não estiver carregado."""
        if self.tts_model is not None:
            return
        allow_tts_checkpoint_load()
        log(f"[TTS] A carregar o modelo Coqui XTTS-v2 no dispositivo: {self.device.upper()}...")
        t0 = time.time()
        self.tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
        log(f"[TTS] Modelo XTTS-v2 carregado com sucesso! (Demorou {time.time() - t0:.2f}s)")

    def clean_text_for_tts(self, text: str) -> str:
        """
        Limpa o texto gerado pela LLM removendo blocos de pensamento, markdown,
        emojis, símbolos gráficos e pontuações indesejadas antes de enviar para o TTS.
        """
        if not text:
            return ""
        
        # 1. Remove blocos de raciocínio/pensamento de LLMs (<think>...</think>)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # 2. Remove marcações de Markdown (*, #, _, ~, `, >, -)
        cleaned = re.sub(r'[*#_`~>-]', ' ', cleaned)
        
        # 3. Remove emojis e símbolos pictográficos do Unicode de forma ampla
        cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned)
        cleaned = re.sub(r'[^\w\s.,!?;:\u00C0-\u00FF]', '', cleaned)
        
        # 4. Normaliza múltiplos espaços e quebras de linha em espaço único
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # 5. Remove ponto final no encerramento para evitar a pronúncia da palavra "ponto"
        if cleaned.endswith('.'):
            cleaned = cleaned[:-1].strip()
            
        return cleaned
        
    def _cache_path(self, clean_text: str, tts_params: dict):
        # Hash do texto + parametros + voz: mudou algo => gera de novo; igual => reaproveita
        hash_input = f"{clean_text}_{tts_params}_{self.speaker_wav.name}"
        return CACHE_DIR / f"cognition_{hashlib.md5(hash_input.encode('utf-8')).hexdigest()}.wav"

    def _ensure_locked(self, text: str, tts_params: dict):
        """Garante o WAV em cache (gera se faltar). Devolve (caminho|None, status). Chamar com o lock."""
        clean_text = self.clean_text_for_tts(text)
        if not clean_text:
            return None, "failed"

        self.load_tts_model()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        out_path = self._cache_path(clean_text, tts_params)

        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path, "cached"

        log(f"[TTS] A sintetizar áudio: \"{clean_text[:40]}...\"")
        tmp_path = out_path.with_suffix(".tmp.wav")
        try:
            self.tts_model.tts_to_file(
                text=clean_text,
                speaker_wav=str(self.speaker_wav),
                language=LANGUAGE,
                file_path=str(tmp_path),
                **tts_params
            )
            tmp_path.replace(out_path)  # troca atomica: nunca fica arquivo pela metade no cache
        except Exception as e:
            log(f"[TTS ERRO] Falha ao sintetizar \"{clean_text[:40]}\": {e}")
            try:
                tmp_path.unlink()
            except OSError:
                pass
            return None, "failed"
        return out_path, "generated"

    def ensure_audio(self, text: str, tts_params: dict) -> str:
        """Pre-gera o audio sem tocar. Devolve 'generated', 'cached' ou 'failed'."""
        with self._lock:
            return self._ensure_locked(text, tts_params)[1]

    def generate_and_play_audio(self, text: str, tts_params: dict, play_audio_func):
        """Gera (ou reaproveita do cache) e toca."""
        with self._lock:
            out_path, status = self._ensure_locked(text, tts_params)
        if status == "cached":
            log(f"[TTS CACHE] A utilizar áudio em cache para: \"{self.clean_text_for_tts(text)[:30]}...\"")
        if out_path and play_audio_func:
            play_audio_func(str(out_path))
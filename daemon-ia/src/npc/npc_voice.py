"""
Voz própria do NPC: reaproveita o modelo XTTS já carregado pelo AudioPipeline (sem VRAM extra).
  1) Se existir modelos_voz/npc_voice.wav -> clona essa voz.
  2) Senão -> usa uma voz EMBUTIDA do XTTS (nunca a voz do personagem principal).
Cache com prefixo 'npc_' e a identidade da voz no hash.
"""
import hashlib
import time
from pathlib import Path

from src.config import CACHE_DIR, LANGUAGE
from src.npc.npc_config import NPC_BUILTIN_SPEAKER
from src.user_settings import npc_speaker_wav


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[NPC VOZ] {msg}", flush=True)


class NpcVoice:
    def __init__(self, base_pipeline, speaker_wav: Path = None,
                 builtin_speaker: str = NPC_BUILTIN_SPEAKER):
        self.base = base_pipeline
        if speaker_wav is None:
            speaker_wav = npc_speaker_wav()
        self.speaker_wav = Path(speaker_wav) if Path(speaker_wav).exists() else None
        self.builtin_speaker = builtin_speaker
        self._builtin_checked = False
        if self.speaker_wav:
            log(f"Voz do NPC: clonada de {self.speaker_wav.name}")
        else:
            log(f"'{Path(speaker_wav).name}' não encontrado: o NPC usará a voz embutida "
                f"'{builtin_speaker}' (diferente da sua).")

    def _voice_id(self) -> str:
        return self.speaker_wav.name if self.speaker_wav else f"builtin:{self.builtin_speaker}"

    def _cache_path(self, clean_text: str, params: dict) -> Path:
        key = f"{clean_text}_{params}_{self._voice_id()}_npc"
        return CACHE_DIR / f"npc_{hashlib.md5(key.encode('utf-8')).hexdigest()}.wav"

    def _check_builtin(self):
        """Valida o nome da voz embutida contra a lista real do modelo (já carregado)."""
        if self._builtin_checked:
            return
        self._builtin_checked = True
        speakers = list(getattr(self.base.tts_model, "speakers", None) or [])
        if speakers and self.builtin_speaker not in speakers:
            log(f"Voz embutida '{self.builtin_speaker}' não existe neste modelo. "
                f"Usando '{speakers[0]}'. Disponíveis: {', '.join(speakers[:12])}...")
            self.builtin_speaker = speakers[0]

    def ensure(self, text: str, params: dict):
        """Garante o WAV em cache. Devolve o caminho (str) ou None."""
        clean = self.base.clean_text_for_tts(text)
        if not clean:
            return None

        # O modelo precisa estar carregado antes de validar a voz embutida
        if not self.speaker_wav and not self._builtin_checked:
            with self.base._lock:
                self.base.load_tts_model()
                self._check_builtin()

        out = self._cache_path(clean, params)
        if out.exists() and out.stat().st_size > 0:
            return str(out)

        with self.base._lock:              # mesma trava do XTTS do jogador
            if out.exists() and out.stat().st_size > 0:
                return str(out)
            self.base.load_tts_model()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            log(f"A sintetizar: \"{clean[:40]}...\"")
            tmp = out.with_suffix(".tmp.wav")
            voice_kwargs = ({"speaker_wav": str(self.speaker_wav)} if self.speaker_wav
                            else {"speaker": self.builtin_speaker})
            try:
                self.base.tts_model.tts_to_file(
                    text=clean,
                    language=LANGUAGE,
                    file_path=str(tmp),
                    **voice_kwargs,
                    **params,
                )
                tmp.replace(out)
            except Exception as e:
                log(f"Erro ao sintetizar \"{clean[:40]}\": {e}")
                try:
                    tmp.unlink()
                except OSError:
                    pass
                return None
        return str(out)
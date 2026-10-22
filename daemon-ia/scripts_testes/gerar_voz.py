import os
import torch
import torchaudio
import soundfile as sf

# Substitui o load do torchaudio por uma versão que não depende de torchcodec/FFmpeg
def _load_com_soundfile(path, *args, **kwargs):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(data.T), sr

torchaudio.load = _load_com_soundfile

from TTS.api import TTS

os.environ["COQUI_TOS_AGREED"] = "1"

device = "cuda" if torch.cuda.is_available() else "cpu"

tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts.tts_to_file(
    text="Olá! Este é um teste de geração de voz usando o XTTS versão dois.",
    speaker_wav="minha_voz.wav",
    language="pt",
    file_path="saida.wav",
)
print("Pronto: saida.wav")
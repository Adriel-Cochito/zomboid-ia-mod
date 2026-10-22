import os
import torch
import torchaudio
import soundfile as sf

def _load_com_soundfile(path, *args, **kwargs):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(data.T), sr

torchaudio.load = _load_com_soundfile

from TTS.api import TTS

os.environ["COQUI_TOS_AGREED"] = "1"

device = "cuda" if torch.cuda.is_available() else "cpu"
print(device) # Deve imprimir 'cuda'
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Gerando com parâmetros ajustados para maior expressividade/agressividade
tts.tts_to_file(
    text="Sai daqui agora! Você não vai sobreviver a esta noite!",
    speaker_wav="minha_voz.wav",
    language="pt",
    file_path="saida_agressiva.wav",
    temperature=1,       # Máximo recomendado sem corromper a fala (limite seguro: ~0.85)
    length_penalty=0.5,     # Deixa o ritmo da fala ligeiramente mais acelerado e urgente
    repetition_penalty=2.2  # Evita que o modelo repita sílabas ao tentar expressar raiva
)
print("Pronto: saida_agressiva.wav")
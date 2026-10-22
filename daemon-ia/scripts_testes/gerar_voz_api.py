import os
import sys
import time
import torch
import torchaudio
import soundfile as sf
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from TTS.api import TTS

print("Iniciando carregamento das bibliotecas...")

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from TTS.api import TTS
except Exception as e:
    print(f"Erro ao importar bibliotecas: {e}")
    sys.exit(1)

def _load_com_soundfile(path, *args, **kwargs):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return torch.from_numpy(data.T), sr

torchaudio.load = _load_com_soundfile

os.environ["COQUI_TOS_AGREED"] = "1"

app = FastAPI()

print("Carregando modelo XTTS-v2 na GPU...")
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Dispositivo ativo: {device}")

try:
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
except Exception as e:
    print(f"Erro ao carregar o modelo XTTS: {e}")
    sys.exit(1)

# Modelo dinâmico para aceitar parâmetros customizados na requisição POST
class TTSRequest(BaseModel):
    text: str
    speaker_wav: str = "867418__riippumattog__screaming.wav"
    language: str = "pt"
    temperature: float = 0.75         # Controla a expressividade/emoção
    length_penalty: float = 0.85      # Controla o ritmo/velocidade da fala
    repetition_penalty: float = 2.5   # Evita gagueiras e dá firmeza

@app.post("/gerar-voz")
def gerar_voz(req: TTSRequest):
    if not os.path.exists(req.speaker_wav):
        raise HTTPException(status_code=400, detail=f"Arquivo de referência '{req.speaker_wav}' não encontrado.")
    
    try:
        timestamp = int(time.time() * 1000)
        file_name = f"saida_{timestamp}.wav"
        print(f"Gerando áudio dinâmico para: '{req.text}' [Temp: {req.temperature}, Vel: {req.length_penalty}]")
        
        # Otimização de velocidade usando o modo de inferência do PyTorch
        with torch.inference_mode():
            tts.tts_to_file(
                text=req.text,
                speaker_wav=req.speaker_wav,
                language=req.language,
                file_path=file_name,
                temperature=req.temperature,
                length_penalty=req.length_penalty,
                repetition_penalty=req.repetition_penalty
            )
        
        return {
            "status": "sucesso",
            "arquivo": file_name,
            "mensagem": "Áudio gerado com sucesso!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Servidor Uvicorn iniciando na porta 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
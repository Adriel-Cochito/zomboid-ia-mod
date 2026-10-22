import os
import sys

print("Iniciando carregamento das bibliotecas...")

try:
    import torch
    import torchaudio
    import soundfile as sf
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from TTS.api import TTS
except Exception as e:
    print(f"Erro ao importar bibliotecas: {e}")
    sys.exit(1)

# Configuração para evitar problemas de codec
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
    # Carrega direto no device sem conversão manual de half-precision para evitar conflitos de tipos
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
except Exception as e:
    print(f"Erro ao carregar o modelo XTTS: {e}")
    sys.exit(1)

class TTSRequest(BaseModel):
    text: str
    speaker_wav: str = "minha_voz.wav"
    language: str = "pt"
    temperature: float = 0.78

@app.post("/gerar-voz")
def gerar_voz(req: TTSRequest):
    import time
    if not os.path.exists(req.speaker_wav):
        raise HTTPException(status_code=400, detail=f"Arquivo de referência '{req.speaker_wav}' não encontrado.")
    
    try:
        timestamp = int(time.time() * 1000)
        file_name = f"saida_{timestamp}.wav"
        print(f"Gerando áudio para o texto: '{req.text}'")
        
        tts.tts_to_file(
            text=req.text,
            speaker_wav=req.speaker_wav,
            language=req.language,
            file_path=file_name,
            temperature=req.temperature,
            length_penalty=0.9,
            repetition_penalty=2.0
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
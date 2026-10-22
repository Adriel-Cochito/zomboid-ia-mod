import os
import sys
import time
from pathlib import Path
from typing import Optional
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

# Pastas (relativas a este arquivo, funcionam de qualquer diretorio)
BASE = Path(__file__).resolve().parent
AUDIOS_GERADOS = BASE / "audios_gerados"   # onde os audios gerados sao salvos
MODELOS_VOZ = BASE / "modelos_voz"         # onde ficam as vozes de referencia

# >>> VOZ PADRÃO <<<  usada quando a chamada NÃO envia "speaker_wav"
# (nome do arquivo dentro de modelos_voz). Se a chamada enviar, vale a da chamada.
VOZ_PADRAO = "deacon.mp3"


def resolver_voz(nome: Optional[str]) -> Path:
    """Vazio -> voz padrão. Só o nome do arquivo -> procura em modelos_voz. Caminho completo -> usa como está."""
    nome = (nome or "").strip() or VOZ_PADRAO
    p = Path(nome)
    return p if p.is_absolute() else MODELOS_VOZ / p.name
AUDIOS_GERADOS.mkdir(exist_ok=True)
MODELOS_VOZ.mkdir(exist_ok=True)


print("Carregando modelo XTTS-v2 na GPU...")
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Dispositivo ativo: {device}")

try:
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
except Exception as e:
    print(f"Erro ao carregar o modelo XTTS: {e}")
    sys.exit(1)

class TTSRequest(BaseModel):
    text: str
    speaker_wav: Optional[str] = None  # vazio/omitido => usa VOZ_PADRAO
    language: str = "pt"
    temperature: float = 0.8         # Ideal entre 0.65 e 0.75 para evitar robô
    length_penalty: float = 0.80       # Deixe em 1.0 para não estragar o ritmo natural
    repetition_penalty: float = 2.5   # Evita loops e gagueiras
    top_k: int = 50                   # Suaviza a escolha de palavras (evita robô)
    top_p: float = 0.2               # Controla a diversidade fluida da fala
    speed: float = 1.3  # <--- NOVO: Valores acima de 1.0 aceleram a fala (ex: 1.15 a 1.25)

@app.post("/gerar-voz")
def gerar_voz(req: TTSRequest):
    voz = resolver_voz(req.speaker_wav)  # chamada preenchida => da chamada; vazia => VOZ_PADRAO
    if not voz.exists():
        raise HTTPException(status_code=400, detail=f"Arquivo de referência '{voz}' não encontrado.")
    
    try:
        timestamp = int(time.time() * 1000)
        file_path = AUDIOS_GERADOS / f"saida_{timestamp}.wav"
        print(f"Gerando áudio para: '{req.text}' [Temp: {req.temperature}, Top_K: {req.top_k}]")
        
        with torch.inference_mode():
            tts.tts_to_file(
                text=req.text,
                speaker_wav=str(voz),
                language=req.language,
                file_path=str(file_path),
                temperature=req.temperature,
                length_penalty=req.length_penalty,
                repetition_penalty=req.repetition_penalty,
                top_k=req.top_k,
                top_p=req.top_p,
                speed=req.speed  # <--- Repassando a velocidade aqui
            )
        
        return {
            "status": "sucesso",
            "arquivo": file_path.name,
            "caminho": str(file_path),
            "mensagem": "Áudio gerado com sucesso!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Servidor Uvicorn iniciando na porta 8000...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
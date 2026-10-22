"""
Módulo de monitorização do ficheiro de eventos gerado pelo Lua do Project Zomboid.
Faz o 'tail' do ficheiro TTS_events.txt de forma contínua e assíncrona.
"""
import time
from src.config import EVENTS_FILE, POLL_INTERVAL_S

def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)

class EventMonitor:
    def __init__(self, on_event_callback):
        """
        on_event_callback: função a ser chamada com (evento, detalhe) assim que um novo registo for detetado.
        """
        self.on_event_callback = on_event_callback

    def start_monitoring(self):
        """Inicia o loop contínuo de escuta (tail) do ficheiro de eventos."""
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        offset = EVENTS_FILE.stat().st_size if EVENTS_FILE.exists() else 0
        partial = b""
        log(f"[MONITOR] A observar ficheiro de eventos: {EVENTS_FILE}")
        
        while True:
            time.sleep(POLL_INTERVAL_S)
            try:
                size = EVENTS_FILE.stat().st_size
            except FileNotFoundError:
                offset, partial = 0, b""
                continue
            if size < offset:
                offset, partial = 0, b""
            if size == offset:
                continue
                
            with open(EVENTS_FILE, "rb") as f:
                f.seek(offset)
                chunk = f.read()
            offset += len(chunk)
            lines = (partial + chunk).split(b"\n")
            partial = lines.pop()
            
            for raw in lines:
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    parts = line.split("|", 1)
                    evt = parts[0]
                    det = parts[1] if len(parts) > 1 else ""
                    
                    if self.on_event_callback:
                        self.on_event_callback(evt, det)
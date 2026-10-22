"""
Persistência do missions.json: missão atual + resumo do dia + histórico recente.
"""
import json
import time
from src.config import MISSIONS_FILE

HISTORY_LIMIT = 7


def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


class MissionStore:
    def __init__(self, filepath=MISSIONS_FILE):
        self.filepath = filepath

    def save_missions(self, missions_list: list, summary: str = "", context: dict = None):
        if not missions_list:
            return

        previous = self.load_missions()
        historico = previous.get("historico", [])
        if previous.get("missions"):
            historico.append({
                "updated_at": previous.get("updated_at"),
                "resumo_passado": previous.get("resumo_passado", ""),
                "contexto": previous.get("contexto", {}),
                "missions": previous["missions"],
            })
        historico = historico[-HISTORY_LIMIT:]

        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "resumo_passado": summary,
            "contexto": context or {},
            "missions": missions_list,
            "historico": historico,
        }

        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            log(f"[MISSOES] {len(missions_list)} nova(s) missão(ões) salva(s) em: {self.filepath}")
        except Exception as e:
            log(f"[MISSOES ERRO] Falha ao gravar missions.json: {e}")

    def load_missions(self) -> dict:
        if not self.filepath.exists():
            return {"updated_at": None, "missions": []}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"[MISSOES ERRO] Falha ao ler missions.json: {e}")
            return {"updated_at": None, "missions": []}
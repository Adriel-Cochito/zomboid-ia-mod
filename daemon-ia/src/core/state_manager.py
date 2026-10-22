"""
Gerenciador de Estado (StateManager).
"""
import time
import threading


class StateManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.events_buffer = []
        self.player_status = {}

    def add_event(self, evt_type: str, detail: str):
        with self._lock:
            self.events_buffer.append({"timestamp": time.time(), "type": evt_type, "detail": detail})

    def get_events_for_reflection(self) -> list[dict]:
        with self._lock:
            return list(self.events_buffer)

    def get_and_clear_daily_events(self) -> list[dict]:
        with self._lock:
            events = list(self.events_buffer)
            self.events_buffer.clear()
            return events

    def reset_reflection_window(self):
        with self._lock:
            self.events_buffer.clear()

    def get_events_by_type(self, *types: str) -> list[dict]:
        with self._lock:
            return [e for e in self.events_buffer if e["type"] in types]

    def update_player_status(self, status: dict):
        if not status:
            return
        with self._lock:
            cur = self.player_status
            new = {
                "profession": status.get("profession", cur.get("profession", "Sobrevivente")),
                "perks": {**cur.get("perks", {}), **status.get("perks", {})},
            }
            for k in ("days", "hours"):
                if status.get(k) is not None:
                    new[k] = status[k]
                elif cur.get(k) is not None:
                    new[k] = cur[k]
            self.player_status = new

    def get_player_status(self) -> dict:
        with self._lock:
            out = {
                "profession": self.player_status.get("profession", "Sobrevivente"),
                "perks": dict(self.player_status.get("perks", {})),
            }
            for k in ("days", "hours"):
                if k in self.player_status:
                    out[k] = self.player_status[k]
            return out
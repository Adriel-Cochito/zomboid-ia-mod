"""
Estado compartilhado de "jogo pausado", alimentado pelo evento paused/resumed
que o Lua emite (ver NPC_Bridge.lua, Events.OnTickEvenPaused).

Usado para: (1) não tocar áudio enquanto o jogo está pausado, e (2) opcionalmente
evitar começar a sintetizar/gerar fala nova enquanto pausado. É um módulo
isolado, sem dependências, para poder ser importado tanto pelo pipeline do
NPC quanto pelo daemon principal (fala do personagem).
"""
import threading
import time


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[PAUSA] {msg}", flush=True)


class PauseState:
    def __init__(self):
        self._paused = threading.Event()

    def set_paused(self, paused: bool):
        was = self._paused.is_set()
        if paused:
            self._paused.set()
        else:
            self._paused.clear()
        if paused != was:
            log("jogo pausado." if paused else "jogo despausado.")

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def wait_if_paused(self, poll_s: float = 0.2, max_wait_s: float = 600.0):
        """Bloqueia enquanto o jogo estiver pausado (até max_wait_s, por segurança)."""
        waited = 0.0
        while self._paused.is_set() and waited < max_wait_s:
            time.sleep(poll_s)
            waited += poll_s


# instância única do processo: tanto o módulo do NPC quanto o daemon principal
# devem importar e usar ESTA mesma instância.
PAUSE = PauseState()
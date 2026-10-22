"""
Fila de falas do NPC com prioridade, TTL e cooldown por chave.
Sintetiza fora da trava do jogador e só toca quando o 'gate' (daemon.busy) está livre,
então a fala do personagem principal nunca é atropelada por uma fala nova do NPC.
"""
import heapq
import itertools
import threading
import time

from src.npc.pause_state import PAUSE
from src.npc.npc_config import (
    PRIORITY, TTL_S, MAX_QUEUE, NPC_TTS_PARAMS,
)
from src.user_settings import npc_cooldown

_COOLDOWN_KINDS = ("event", "idle", "danger")
_PARAMS_BY_KIND = {"danger": "danger", "idle": "calm"}


class NpcSpeaker:
    def __init__(self, voice, play_fn, gate, on_speak=None, clock=time.time):
        self.voice = voice
        self.play_fn = play_fn
        self.gate = gate
        self.on_speak = on_speak
        self.clock = clock
        self._heap = []
        self._cv = threading.Condition()
        self._count = itertools.count()
        self._last_by_key = {}
        self._stop = False
        self._thread = None
        self.last_spoke_at = 0.0

    def can_say(self, kind: str = "event", key: str = None) -> bool:
        """Checa o cooldown ANTES de gastar uma chamada de LLM."""
        if kind not in _COOLDOWN_KINDS:
            return True
        cd = npc_cooldown(key or kind)
        with self._cv:
            return self.clock() - self._last_by_key.get(key or kind, 0.0) >= cd

    def say(self, text: str, kind: str = "event", key: str = None) -> bool:
        if not text:
            return False
        now = self.clock()
        key = key or kind
        pri, ttl = PRIORITY[kind], TTL_S[kind]

        with self._cv:
            if kind in _COOLDOWN_KINDS:
                cd = npc_cooldown(key)
                if now - self._last_by_key.get(key, 0.0) < cd:
                    return False
            if len(self._heap) >= MAX_QUEUE:
                worst = max(self._heap, key=lambda x: (x[0], -x[1]))
                if pri >= worst[0]:
                    return False
                self._heap.remove(worst)
                heapq.heapify(self._heap)
            if kind in _COOLDOWN_KINDS:
                self._last_by_key[key] = now
            heapq.heappush(self._heap, (pri, next(self._count), now + ttl, text, kind))
            self._cv.notify()
        return True

    def pending(self) -> int:
        with self._cv:
            return len(self._heap)

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="npc-speaker")
        self._thread.start()

    def stop(self):
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def _loop(self):
        while True:
            with self._cv:
                while not self._heap and not self._stop:
                    self._cv.wait(0.5)
                if self._stop:
                    return
                _, _, expires, text, kind = heapq.heappop(self._heap)
            try:
                self._speak(text, kind, expires)
            except Exception as e:
                print(f"[NPC] erro ao falar: {e}", flush=True)

    def _speak(self, text, kind, expires):
        if self.clock() > expires:
            return
        PAUSE.wait_if_paused()  # nao gasta GPU sintetizando enquanto o jogo esta pausado
        if self.clock() > expires:
            return
        params = NPC_TTS_PARAMS[_PARAMS_BY_KIND.get(kind, "normal")]
        path = self.voice.ensure(text, params)       # pode demorar (XTTS)
        if not path:
            return
        while self.clock() < expires:
            if self.gate.acquire(blocking=False):
                try:
                    PAUSE.wait_if_paused()  # nao toca o audio com o jogo pausado
                    self.last_spoke_at = self.clock()
                    if self.on_speak:
                        self.on_speak(text)
                    self.play_fn(path)
                finally:
                    self.gate.release()
                return
            time.sleep(0.2)
        # expirou esperando o personagem principal terminar de falar: descarta
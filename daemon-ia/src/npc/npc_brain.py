"""
Orquestrador do NPC companheiro (NpcCompanion).
Liga: eventos do Lua -> estado -> decisão de modo / falas -> comandos para o Lua + áudio.

Integração com o daemon (3 linhas): veja tts_daemon.py (patch no guia).
"""
import random
import threading
import time

from src.npc import npc_config as cfg
from src.npc.npc_chat import detect_mode, detect_fetch
from src.npc.npc_decision import ModeDecider
from src.npc.npc_persona import NpcMemory
from src.npc.npc_phrases import PhraseMaker
from src.npc.npc_speaker import NpcSpeaker
from src.npc.npc_state import NpcState
from src.npc.pause_state import PAUSE
from src.npc.npc_voice import NpcVoice
from src.npc.protocol import FileTail, CommandWriter, parse_line, parse_kv
from src.user_settings import idle_bounds, npc_enabled


def log(msg):
    print(time.strftime("[%H:%M:%S]"), f"[NPC] {msg}", flush=True)


class NpcCompanion:
    def __init__(self, base_pipeline, play_fn, gate, llm_fn=None, voice=None,
                 events_file=cfg.NPC_EVENTS_FILE, commands_file=cfg.NPC_COMMANDS_FILE,
                 memory_file=cfg.NPC_MEMORY_FILE):
        if llm_fn is None:
            from src.services.ollama_service import call_ollama_chat
            llm_fn = call_ollama_chat

        self._lock = threading.RLock()
        self.state = NpcState()
        self.memory = NpcMemory(memory_file)
        self.phrases = PhraseMaker(llm_fn, self.memory, cfg.NPC_NAME)
        self.decider = ModeDecider(llm_fn)
        self.writer = CommandWriter(commands_file, cfg.COMMANDS_KEEP_LINES)
        self.voice = voice or NpcVoice(base_pipeline)
        self.speaker = NpcSpeaker(self.voice, play_fn, gate, on_speak=self._on_speak)
        self.tail = FileTail(events_file, self._on_line, cfg.POLL_INTERVAL_S)
        self._handlers = {
            "state": self._h_state, "hurt": self._h_hurt, "kill": self._h_kill,
            "loot": self._h_loot, "no_ammo": self._h_no_ammo, "joined": self._h_joined,
            "left": self._h_left, "died": self._h_left, "cmd": self._h_cmd, "say": self._h_say,
            "fetch_fail": self._h_fetch_fail,
            "paused": self._h_paused, "resumed": self._h_resumed,
        }
        self._next_idle = time.time() + random.uniform(*idle_bounds())
        self._stop = threading.Event()

    # ------------------------------------------------------------ ciclo de vida
    def start(self):
        if not cfg.NPC_ENABLED or not npc_enabled():
            log("Módulo desativado.")
            return
        self.precache()
        self.speaker.start()
        self.tail.start()
        threading.Thread(target=self._ticker, daemon=True, name="npc-ticker").start()
        log(f"Companheiro '{cfg.NPC_NAME}' pronto. Eventos: {cfg.NPC_EVENTS_FILE}")

    def stop(self):
        self._stop.set()
        self.tail.stop()
        self.speaker.stop()
        self.memory.save_if_needed(min_interval=0)

    def precache(self):
        """Pré-gera as falas estáticas na voz do NPC (só na 1ª vez; depois vêm do cache)."""
        phrases = []
        for key, options in cfg.NPC_PHRASES.items():
            for text in options:
                if "{item}" in text:
                    phrases += [text.format(item=i) for i in cfg.PRECACHE_LOOT_ITEMS]
                else:
                    phrases.append(text)
        params = cfg.NPC_TTS_PARAMS["normal"]
        ok = 0
        for text in phrases:
            if self.voice.ensure(text, params):
                ok += 1
        log(f"Pré-cache de voz: {ok}/{len(phrases)} falas prontas.")

    # ------------------------------------------------------------ entrada de eventos
    def _on_line(self, line: str):
        evt, payload = parse_line(line)
        handler = self._handlers.get(evt)
        if handler:
            with self._lock:
                handler(payload)

    def _on_speak(self, text: str):
        """Legenda no jogo: o Lua mostra o texto quando o áudio começa."""
        self.writer.send_say(text)
        log(f"Falando: \"{text}\"")

    # ------------------------------------------------------------ handlers
    def _h_state(self, payload):
        was_present = self.state.present
        prev_threats = self.state.threats
        self.state.update(parse_kv(payload))
        st = self.state

        if not was_present:
            self._speak_event("joined")
        if prev_threats == 0 and st.threats >= 2:
            self.speaker.say(self.phrases.static("danger"), "danger", "danger")
        if st.hp <= cfg.LOW_HP:
            self.speaker.say(self.phrases.static("low_hp"), "event", "low_hp")

        d = self.decider.decide(st)
        if d:
            log(f"Decisão ({d.source}): {st.mode} -> {d.mode} | {d.reason}")
            self._apply_mode(d.mode, d.reason)
            self.speaker.say(d.reason, "event", "decision")

    def _apply_mode(self, mode: str, reason: str):
        self.writer.send_mode(mode, reason)
        self.state.mode = mode
        self.decider.note_applied()

    def _h_hurt(self, payload):
        self.speaker.say(self.phrases.static("hurt"), "danger", "hurt")

    def _speak_event(self, key: str, kind: str = "event", item: str = ""):
        """Fala que pode usar LLM: gera em outra thread para não travar o monitor de eventos."""
        if not self.speaker.can_say(kind, key):
            return
        threading.Thread(target=self._speak_worker, args=(key, kind, item, self.state),
                         daemon=True).start()

    def _speak_worker(self, key, kind, item, state):
        text = self.phrases.make(key, state, item)
        if text:
            self.speaker.say(text, kind, key)

    def _h_kill(self, payload):
        self.state.kills += 1
        self.memory.count("abates")
        self.memory.add_bond(1)
        self._speak_event("kill")

    def _h_loot(self, payload):
        item = parse_kv(payload).get("item", "").strip()
        if not item:
            return
        self.memory.remember(f"pegou {item}")
        self.memory.add_bond(1)
        self._speak_event("loot", item=item)

    def _h_no_ammo(self, payload):
        self.state.ammo = "empty"
        self.speaker.say(self.phrases.static("no_ammo"), "event", "no_ammo")

    def _h_joined(self, payload):
        self.state.present = True
        self._speak_event("joined")

    def _h_left(self, payload):
        self.state.present = False
        log("Companheiro saiu/morreu.")

    def _h_cmd(self, payload):
        mode = payload.strip().lower()
        if mode in cfg.MODES:
            self._order(mode)

    def _fetch(self, keywords: str, label: str):
        """Pedido de busca de itens: o corpo (adapter) vai até os contêineres e volta."""
        self.decider.note_manual()
        self.writer.send_fetch(keywords, label)
        self.memory.count("buscas")
        self.memory.remember(f"pediu para buscar {label}")
        self.memory.add_bond(1)
        log(f"  -> BUSCA enviada: {label} ({keywords})")
        self.speaker.say(self.phrases.static("fetch_go", item=label), "order")

    def _h_paused(self, payload):
        PAUSE.set_paused(True)

    def _h_resumed(self, payload):
        PAUSE.set_paused(False)

    def _h_fetch_fail(self, payload):
        reason = parse_kv(payload).get("reason", "none")
        key = "fetch_abort" if reason in ("danger", "timeout") else "fetch_none"
        self.speaker.say(self.phrases.static(key), "event", "fetch")

    def _order(self, mode: str):
        """Ordem do jogador: tem prioridade absoluta sobre a IA por MANUAL_OVERRIDE_S."""
        if mode == "saquear":
            # o Bandits não tem modo "saquear"; vira uma busca genérica de itens úteis
            self._fetch("@util", "coisas úteis")
            return
        self.decider.note_manual()
        self.writer.send_mode(mode, "ordem do jogador")
        self.state.mode = mode
        self.memory.remember(f"recebeu ordem: {mode}")
        self.memory.add_bond(1)
        self.speaker.say(self.phrases.static(f"mode_{mode}"), "order")

    def _h_say(self, payload):
        text = payload.strip()
        if not text:
            return
        log(f"JOGADOR disse: {text!r}")
        fetch = detect_fetch(text)
        if fetch:
            log("  -> interpretado como PEDIDO DE BUSCA")
            self.memory.count("ordens")
            self._fetch(fetch[1], fetch[0])
            return
        mode = detect_mode(text)
        if mode:
            log(f"  -> interpretado como ORDEM: {mode}")
            self.memory.count("ordens")
            self._order(mode)
            return
        self.memory.count("conversas")
        self.memory.remember(f"jogador disse: {text[:40]}")
        self.memory.add_bond(1)
        # resposta de conversa pode demorar (LLM): não bloqueia o monitor de eventos
        threading.Thread(target=self._chat_worker, args=(text,), daemon=True).start()

    def _chat_worker(self, text: str):
        with self._lock:
            state = self.state
        reply = self.phrases.chat_reply(text, state)
        log(f"NPC respondeu: {reply!r}")
        if reply:
            self.memory.remember(f"eu disse: {reply[:40]}")
            self.speaker.say(reply, "chat")

    # ------------------------------------------------------------ tarefas periódicas
    def _ticker(self):
        while not self._stop.wait(5.0):
            try:
                self._tick(time.time())
            except Exception as e:
                log(f"erro no ticker: {e}")

    def _tick(self, now: float):
        if PAUSE.is_paused():
            return
        chatter = False
        with self._lock:
            st = self.state
            if st.is_stale(now):
                st.present = False
                log("Sem sinal do companheiro (estado antigo). Marcado como ausente.")
            self.memory.save_if_needed(now)

            if (cfg.IDLE_CHATTER and st.present and not st.in_combat and now >= self._next_idle
                    and now - self.speaker.last_spoke_at > 30):
                self._next_idle = now + random.uniform(*idle_bounds())
                chatter = True
        if chatter:
            self._speak_event("idle", kind="idle")
"""
Ponto de entrada principal (Orquestrador) do Daemon de IA para Project Zomboid.
"""
import random
import re
import time
import winsound
import threading
import json


from src.config import (
    TTS_PARAMS_NORMAL, TTS_PARAMS_SLOW, TTS_PARAMS_LOOT, TTS_PARAMS_PANIC,
    PHRASES, FALLBACK_TEMPLATES
)
from src.user_settings import player_cooldown, prepare_runtime_env
from src.core.state_manager import StateManager
from src.core.event_monitor import EventMonitor
from src.services.ollama_service import warmup_ollama_service
from src.services.phrase_service import generate_event_phrase
from src.services.tts_service import AudioPipeline
from src.storage.mission_store import MissionStore

from src.engine.log_analyst import build_day_profile
from src.engine.knowledge_filter import KnowledgeFilter
from src.engine.strategy_engine import determine_survival_strategy
from src.engine.narrative_generator import generate_narrative, generate_mission_speech
from src.npc.npc_brain import NpcCompanion

def log(msg):
    print(time.strftime("[%H:%M:%S]"), msg, flush=True)


def short_item(detail: str) -> str:
    """'Weapon:Taco de Basebol (Ensanguentada)' -> 'Taco de Basebol'."""
    if not detail:
        return ""
    raw = detail.split(":", 1)[1] if ":" in detail else detail
    cleaned = re.sub(r"\s*\(.*?\)", "", raw).strip()
    return cleaned or raw.strip()


class TTSDaemon:
    def __init__(self):
        self.state_mgr = StateManager()
        self.audio_pipeline = AudioPipeline()
        self.mission_store = MissionStore()
        self.knowledge_filter = KnowledgeFilter()

        self.busy = threading.Lock()
        self.last_played = {}
        self.last_phrase = {}
        self.is_reflecting = False
        self.last_focus = None
        self.npc = None
        try:
            self.npc = NpcCompanion(self.audio_pipeline, self.play_wav_file, self.busy)
        except Exception as e:
            log(f"[NPC] Módulo NPC desativado por erro: {e}")

    @staticmethod
    def parse_status_detail(detail: str) -> dict:
        """
        Aceita JSON ou 'profession=Cook;days=12;hours=290;Cooking=3;Aiming=2'.
        """
        if not detail:
            return {}
        try:
            data = json.loads(detail)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        status = {"perks": {}}
        for part in detail.split(";"):
            if "=" not in part:
                continue
            k, v = (s.strip() for s in part.split("=", 1))
            k_low = k.lower()
            if k_low == "profession":
                status["profession"] = v
            elif k_low in ("days", "hours"):
                try:
                    status[k_low] = int(float(v))
                except ValueError:
                    pass
            else:
                try:
                    status["perks"][k] = int(float(v))
                except ValueError:
                    pass
        return status

    def play_wav_file(self, filepath: str):
        try:
            winsound.PlaySound(filepath, winsound.SND_FILENAME)
        except Exception as e:
            log(f"[AUDIO ERRO] Falha ao tocar áudio ({filepath}): {e}")

    def precache_static_phrases(self):
        log("[TTS CACHE] A verificar e pré-gerar áudios estáticos em cache...")
        phrases_to_cache = {}
        for evt, lista in PHRASES.items():
            for frase in lista:
                phrases_to_cache[frase] = TTS_PARAMS_PANIC if evt in ["zombie_back", "zombie_indoor", "hurt", "panic"] else TTS_PARAMS_NORMAL

        exemplo_itens = ["Lata de Feijão", "Água", "Taco de Basebol", "Caixa de Munição", "Chocolate"]
        for evt, templates in FALLBACK_TEMPLATES.items():
            for tpl in templates:
                for item in exemplo_itens:
                    try:
                        frase = tpl.format(item=item)
                        phrases_to_cache[frase] = TTS_PARAMS_LOOT if "loot" in evt else TTS_PARAMS_NORMAL
                    except Exception:
                        pass

        generated = cached = failed = 0
        for frase, params in sorted(phrases_to_cache.items()):
            status = self.audio_pipeline.ensure_audio(frase, params)
            if status == "generated":
                generated += 1
            elif status == "cached":
                cached += 1
            else:
                failed += 1

        log(f"[TTS CACHE] Pré-geração concluída: {generated} gerados, {cached} já em cache, {failed} falhas.")

    def make_phrase(self, evt: str, detail: str):
        item = short_item(detail)
        use_static_first = random.random() < 0.40

        if use_static_first:
            if evt in FALLBACK_TEMPLATES and item:
                try:
                    return random.choice(FALLBACK_TEMPLATES[evt]).format(item=item)
                except Exception:
                    pass
            if evt in PHRASES and PHRASES[evt]:
                return random.choice(PHRASES[evt])

        text = generate_event_phrase(evt, detail, item)
        if text:
            return text

        if evt in FALLBACK_TEMPLATES and item:
            try:
                return random.choice(FALLBACK_TEMPLATES[evt]).format(item=item)
            except Exception:
                pass
        if evt in PHRASES and PHRASES[evt]:
            return random.choice(PHRASES[evt])
        return None

    def process_event(self, evt: str, detail: str):
        try:
            text = self.make_phrase(evt, detail)
            if not text:
                return
            self.last_phrase[evt] = text

            panico_events = ["zombie_back", "zombie_indoor", "hurt", "panic", "stealth_broken"]
            if "loot" in evt:
                params = TTS_PARAMS_LOOT
            elif evt in panico_events:
                params = TTS_PARAMS_PANIC
            else:
                params = TTS_PARAMS_NORMAL

            log(f"[SPEAKER] A falar ({evt}): \"{text}\"")
            self.audio_pipeline.generate_and_play_audio(text, params, self.play_wav_file)
        except Exception as e:
            log(f"[ERRO] Falha ao processar '{evt}': {e}")
        finally:
            self.busy.release()

    def process_reflection_sequence(self):
        """
        Passado -> decisão sobre o futuro. Dois áudios no final:
        1) reflexão sobre o dia  2) possível objetivo/missão para o próximo dia.
        """
        if not self.busy.acquire(timeout=30):
            log("[COGNICAO] Ocupado por mais de 30s, reflexão cancelada.")
            self.is_reflecting = False
            return

        try:
            log("[COGNICAO] A iniciar pipeline de fim de dia (descanso)...")

            raw_events = self.state_mgr.get_and_clear_daily_events()
            status = self.state_mgr.get_player_status()
            log(f"[COGNICAO] Eventos do dia: {len(raw_events)} | dias de vida: {status.get('days', '?')}")

            profile = build_day_profile(raw_events, status, self.knowledge_filter)
            log(f"[PIPELINE 1/4] Perfil do dia: loot={profile['loot']} incidentes={profile['incidents']} "
                f"pendentes={profile['unresolved']} etapa={profile['stage']}")

            strategy = determine_survival_strategy(profile, self.knowledge_filter, avoid_focus=self.last_focus)
            log("[PIPELINE 2/4] Direções: " + " | ".join(
                f"{d['categoria']} ({d['score']}): {d['motivo']}" for d in strategy["direcoes"]))

            narrative = generate_narrative(profile, strategy)
            self.last_focus = narrative["foco"]
            log("[PIPELINE 3/4] Narrativa gerada.")

            mission_speech = generate_mission_speech(profile, strategy)
            log("[PIPELINE 4/4] Fala de objetivo possível gerada.")

            self.mission_store.save_missions(
                narrative["missoes"],
                summary=narrative["resumo_passado"],
                context={"dias": profile["days"], "etapa": profile["stage"],
                         "foco": narrative["foco"], "loot": profile["loot"],
                         "incidentes": profile["incidents"],
                         "fala_missao": mission_speech},
            )

            reflection = narrative["fala_voz"]
            if reflection:
                log(f"[SPEAKER] Reflexão ao descansar: \"{reflection}\"")
                self.audio_pipeline.generate_and_play_audio(reflection, TTS_PARAMS_SLOW, self.play_wav_file)

            if mission_speech:
                time.sleep(0.8)
                log(f"[SPEAKER] Possível objetivo: \"{mission_speech}\"")
                self.audio_pipeline.generate_and_play_audio(mission_speech, TTS_PARAMS_SLOW, self.play_wav_file)

            log("[COGNICAO] Ciclo de descanso e reflexão concluído com sucesso.")

        except Exception as e:
            log(f"[COGNICAO ERRO] Falha no pipeline de reflexão: {e}")
        finally:
            self.is_reflecting = False
            self.busy.release()

    def handle_event(self, evt: str, detail: str):
        now = time.time()

        self.state_mgr.add_event(evt, detail)

        if evt in ("rest", "player_status"):
            self.state_mgr.update_player_status(self.parse_status_detail(detail))

        if self.is_reflecting:
            return

        if evt == "rest":
            self.is_reflecting = True
            threading.Thread(target=self.process_reflection_sequence, daemon=True).start()
            return

        if evt == "player_status":
            return

        if not self.busy.acquire(blocking=False):
            log(f"[IGNORADO] '{evt}' (ocupado falando)")
            return

        cooldown = player_cooldown(evt)
        if now - self.last_played.get(evt, 0) < cooldown:
            self.busy.release()
            return
        self.last_played[evt] = now

        threading.Thread(target=self.process_event, args=(evt, detail), daemon=True).start()

    def run(self):
        prepare_runtime_env()
        log("=== A INICIAR DAEMON DE IA E VOZ (PROJECT ZOMBOID) ===")
        warmup_ollama_service()
        self.audio_pipeline.load_tts_model()
        self.precache_static_phrases()
        if self.npc:
            try:
                self.npc.start()
            except Exception as e:
                log(f"[NPC] Falha ao iniciar o módulo NPC: {e}")
        monitor = EventMonitor(on_event_callback=self.handle_event)
        monitor.start_monitoring()


if __name__ == "__main__":
    daemon = TTSDaemon()
    daemon.run()
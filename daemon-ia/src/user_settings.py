"""
Preferências locais da janela de config (vozes, quantidade de falas, NPC ligado).

app_dir() não importa src.config: config.py importa app_dir daqui.
Cooldowns e caminhos de voz importam config e npc_config só na chamada,
quando esses módulos já terminaram de carregar (ciclo de importação).
"""
import json
import os
import shutil
import sys
import uuid
import urllib.request
from pathlib import Path

TALK_MULTIPLIER = {"baixo": 2.0, "medio": 1.0, "alto": 0.5}
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg"}
_OLLAMA_TAGS = "http://localhost:11434/api/tags"


def app_dir() -> Path:
    """Raiz gravável: pasta do daemon (a que tem configurar.py), senão a pasta do .exe."""
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
        for candidate in (here, here.parent):
            if (candidate / "configurar.py").is_file():
                return candidate
        return here
    return Path(__file__).resolve().parent.parent


def zomboid_lua_dir() -> Path:
    return Path.home() / "Zomboid" / "Lua"


def settings_path() -> Path:
    return app_dir() / "config_usuario.json"


def python_executable() -> str:
    """Python do daemon, se o preparador já criou. Senão, o interpretador atual."""
    root = app_dir()
    for candidate in (
        root / "runtime" / "venv" / "Scripts" / "python.exe",
        root / "runtime" / "python" / "python.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def prepare_runtime_env() -> None:
    """ffmpeg e cache do XTTS ficam em runtime/ quando o preparador já rodou."""
    root = app_dir()
    ffmpeg = root / "runtime" / "ffmpeg" / "bin"
    if ffmpeg.is_dir():
        os.environ["PATH"] = str(ffmpeg) + os.pathsep + os.environ.get("PATH", "")
    private = (
        (root / "runtime" / "venv" / "Scripts" / "python.exe").is_file()
        or (root / "runtime" / "python" / "python.exe").is_file()
    )
    if private:
        tts_home = root / "runtime" / "tts_models"
        tts_home.mkdir(parents=True, exist_ok=True)
        os.environ["TTS_HOME"] = str(tts_home)
    os.environ["COQUI_TOS_AGREED"] = "1"


def default_settings() -> dict:
    return {
        "voices": [],
        "assign": {"player": "", "npc": ""},
        "talk": {"player": "medio", "npc": "medio"},
        "npc_enabled": True,
    }


def load(path: Path = None) -> dict:
    path = Path(path) if path else settings_path()
    data = default_settings()
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    voices = raw.get("voices")
    if isinstance(voices, list):
        data["voices"] = [v for v in voices if isinstance(v, dict) and v.get("id") and v.get("file")]
    assign = raw.get("assign")
    if isinstance(assign, dict):
        data["assign"]["player"] = str(assign.get("player") or "")
        data["assign"]["npc"] = str(assign.get("npc") or "")
    talk = raw.get("talk")
    if isinstance(talk, dict):
        for role in ("player", "npc"):
            level = str(talk.get(role) or "medio")
            data["talk"][role] = level if level in TALK_MULTIPLIER else "medio"
    if "npc_enabled" in raw:
        data["npc_enabled"] = bool(raw["npc_enabled"])
    return data


def save(data: dict, path: Path = None) -> None:
    path = Path(path) if path else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def talk_multiplier(role: str, data: dict = None) -> float:
    data = data if data is not None else load()
    level = (data.get("talk") or {}).get(role, "medio")
    return TALK_MULTIPLIER.get(level, 1.0)


def player_cooldown(event: str, data: dict = None) -> float:
    from src.config import EVENT_COOLDOWN_S
    return EVENT_COOLDOWN_S.get(event, 10.0) * talk_multiplier("player", data)


def npc_cooldown(key: str, data: dict = None) -> float:
    from src.npc.npc_config import DEFAULT_KEY_COOLDOWN_S, KEY_COOLDOWN_S
    base = KEY_COOLDOWN_S.get(key, DEFAULT_KEY_COOLDOWN_S)
    return base * talk_multiplier("npc", data)


def idle_bounds(data: dict = None) -> tuple:
    from src.npc.npc_config import IDLE_MAX_S, IDLE_MIN_S
    factor = talk_multiplier("npc", data)
    return IDLE_MIN_S * factor, IDLE_MAX_S * factor


def npc_enabled(data: dict = None) -> bool:
    data = data if data is not None else load()
    return bool(data.get("npc_enabled", True))


def _assigned_file(role: str, data: dict = None):
    from src.config import MODELOS_VOZ
    data = data if data is not None else load()
    voice_id = (data.get("assign") or {}).get(role) or ""
    if not voice_id:
        return None
    for voice in data.get("voices") or []:
        if voice.get("id") != voice_id:
            continue
        path = MODELOS_VOZ / voice["file"]
        return path if path.is_file() else None
    return None


def player_speaker_wav(data: dict = None) -> Path:
    from src.config import MODELOS_VOZ, VOZ_MODELO
    chosen = _assigned_file("player", data)
    if chosen is not None:
        return chosen
    return MODELOS_VOZ / VOZ_MODELO


def npc_speaker_wav(data: dict = None) -> Path:
    from src.config import MODELOS_VOZ
    chosen = _assigned_file("npc", data)
    if chosen is not None:
        return chosen
    return MODELOS_VOZ / "npc_voice.wav"


def sync_voices(data: dict, folder: Path = None) -> dict:
    """Inclui os áudios de modelos_voz. O nome exibido é o do arquivo, sem extensão."""
    from src.config import MODELOS_VOZ
    folder = Path(folder) if folder else MODELOS_VOZ
    by_file = {}
    for voice in data.get("voices") or []:
        filename = voice.get("file")
        if filename and voice.get("id"):
            by_file[filename] = voice
    found = []
    if folder.is_dir():
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES),
            key=lambda p: p.name.lower(),
        )
        for path in files:
            prev = by_file.get(path.name)
            found.append({
                "id": prev["id"] if prev else uuid.uuid4().hex[:12],
                "name": path.stem,
                "file": path.name,
            })
    data["voices"] = found
    ids = {voice["id"] for voice in found}
    assign = data.setdefault("assign", {"player": "", "npc": ""})
    for role in ("player", "npc"):
        if assign.get(role) not in ids:
            assign[role] = ""
    return data


def _safe_stem(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name.strip())
    cleaned = cleaned.strip("_")
    return cleaned[:40]


def attach_voice(data: dict, source: Path, name: str) -> dict:
    from src.config import MODELOS_VOZ
    source = Path(source)
    if source.suffix.lower() not in AUDIO_SUFFIXES:
        raise ValueError("Use um arquivo .wav, .mp3, .flac ou .ogg.")
    if not source.is_file():
        raise ValueError("Arquivo de áudio não encontrado.")
    label = (name or "").strip() or source.stem
    MODELOS_VOZ.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(label) or "voz"
    dest = MODELOS_VOZ / f"{stem}{source.suffix.lower()}"
    n = 2
    while dest.exists():
        dest = MODELOS_VOZ / f"{stem}_{n}{source.suffix.lower()}"
        n += 1
    shutil.copy2(source, dest)
    entry = {"id": uuid.uuid4().hex[:12], "name": label, "file": dest.name}
    data.setdefault("voices", []).append(entry)
    return entry


def detach_voice(data: dict, voice_id: str) -> None:
    from src.config import MODELOS_VOZ, VOZ_MODELO
    voices = data.get("voices") or []
    target = next((v for v in voices if v.get("id") == voice_id), None)
    data["voices"] = [v for v in voices if v.get("id") != voice_id]
    assign = data.setdefault("assign", {})
    for role in ("player", "npc"):
        if assign.get(role) == voice_id:
            assign[role] = ""
    if not target:
        return
    others = [v for v in data["voices"] if v.get("file") == target.get("file")]
    if others:
        return
    filename = target.get("file") or ""
    if filename in (VOZ_MODELO, "npc_voice.wav"):
        return
    path = MODELOS_VOZ / filename
    if path.is_file() and path.resolve().parent == MODELOS_VOZ.resolve():
        path.unlink()


def connection_status(timeout: float = 1.5) -> dict:
    lua = zomboid_lua_dir()
    ollama = False
    try:
        with urllib.request.urlopen(_OLLAMA_TAGS, timeout=timeout) as resp:
            ollama = resp.status == 200
    except Exception:
        ollama = False
    return {
        "lua_dir": str(lua),
        "lua_ok": lua.is_dir(),
        "tts_events": (lua / "TTS_events.txt").is_file(),
        "npc_events": (lua / "NPC_events.txt").is_file(),
        "ollama_ok": ollama,
    }

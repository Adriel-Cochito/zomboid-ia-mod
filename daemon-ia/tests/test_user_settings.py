"""
Preferências locais: multiplicadores, JSON e pasta do programa.
Sem GUI, sem XTTS e sem Ollama.
Rodar na pasta daemon-ia:  python tests/test_user_settings.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import EVENT_COOLDOWN_S  # noqa: E402
from src.npc.npc_config import DEFAULT_KEY_COOLDOWN_S, IDLE_MIN_S, KEY_COOLDOWN_S  # noqa: E402
from src.user_settings import (  # noqa: E402
    app_dir,
    default_settings,
    idle_bounds,
    load,
    npc_cooldown,
    npc_enabled,
    player_cooldown,
    save,
    sync_voices,
    talk_multiplier,
)


def test_app_dir():
    assert app_dir() == Path(__file__).resolve().parent.parent


def test_multipliers():
    data = default_settings()
    assert talk_multiplier("player", data) == 1.0
    data["talk"]["player"] = "baixo"
    data["talk"]["npc"] = "alto"
    assert talk_multiplier("player", data) == 2.0
    assert talk_multiplier("npc", data) == 0.5
    data["talk"]["player"] = "estranho"
    assert talk_multiplier("player", data) == 1.0

    hurt = EVENT_COOLDOWN_S["hurt"]
    assert player_cooldown("hurt", default_settings()) == hurt
    baixo = default_settings()
    baixo["talk"]["player"] = "baixo"
    assert player_cooldown("hurt", baixo) == hurt * 2
    alto = default_settings()
    alto["talk"]["player"] = "alto"
    alto["talk"]["npc"] = "alto"
    assert player_cooldown("nao_existe", alto) == 10.0 * 0.5

    assert npc_cooldown("hurt", default_settings()) == KEY_COOLDOWN_S["hurt"]
    assert npc_cooldown("sem_chave", alto) == DEFAULT_KEY_COOLDOWN_S * 0.5
    lo, hi = idle_bounds(alto)
    assert lo == IDLE_MIN_S * 0.5
    assert hi == lo * 2


def test_roundtrip():
    data = default_settings()
    data["voices"] = [{"id": "abc", "name": "Ana", "file": "ana.wav"}]
    data["assign"] = {"player": "abc", "npc": ""}
    data["talk"] = {"player": "baixo", "npc": "alto"}
    data["npc_enabled"] = False
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config_usuario.json"
        save(data, path)
        loaded = load(path)
    assert loaded["voices"][0]["name"] == "Ana"
    assert loaded["assign"]["player"] == "abc"
    assert loaded["talk"]["npc"] == "alto"
    assert npc_enabled(loaded) is False
    assert npc_enabled(default_settings()) is True


def test_sync_voices():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "capitao_nascimento.mp3").write_bytes(b"a")
        (folder / "outra.wav").write_bytes(b"b")
        (folder / "nota.txt").write_text("ignora", encoding="utf-8")
        data = default_settings()
        data["voices"] = [{"id": "keep", "name": "Outro nome", "file": "outra.wav"}]
        data["assign"] = {"player": "keep", "npc": "sumiu"}
        synced = sync_voices(data, folder)
        by_file = {voice["file"]: voice for voice in synced["voices"]}
        assert set(by_file) == {"capitao_nascimento.mp3", "outra.wav"}
        assert by_file["outra.wav"]["id"] == "keep"
        assert by_file["outra.wav"]["name"] == "outra"
        assert by_file["capitao_nascimento.mp3"]["name"] == "capitao_nascimento"
        assert synced["assign"]["player"] == "keep"
        assert synced["assign"]["npc"] == ""


def test_corrupt_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config_usuario.json"
        path.write_text("{", encoding="utf-8")
        loaded = load(path)
    assert loaded["talk"]["player"] == "medio"
    assert loaded["npc_enabled"] is True


if __name__ == "__main__":
    test_app_dir()
    test_multipliers()
    test_roundtrip()
    test_sync_voices()
    test_corrupt_file()
    print("ok")

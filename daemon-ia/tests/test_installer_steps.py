"""
Passos do preparador: o que já está pronto é pulado.
Não baixa Python, torch nem modelos.
Rodar na pasta daemon-ia:  python tests/test_installer_steps.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from instalar import (  # noqa: E402
    format_download,
    gather_facts,
    needed_steps,
    python_supports_tts,
    reclaim_misplaced_runtime,
    torch_index,
    torch_install_args,
)


def _ready_probes():
    return {
        "vc_redist": lambda: True,
        "nvidia": lambda: False,
        "torch": lambda: True,
        "tts": lambda: True,
        "ollama": lambda: True,
        "gemma": lambda: True,
    }


def test_skip_when_present():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "runtime" / "python").mkdir(parents=True)
        (root / "runtime" / "python" / "python.exe").write_bytes(b"")
        (root / "runtime" / "ffmpeg" / "bin").mkdir(parents=True)
        (root / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe").write_bytes(b"")
        (root / "runtime" / "tts_models").mkdir()
        (root / "runtime" / "tts_models" / ".xtts_ready").write_text("ok", encoding="utf-8")
        facts = gather_facts(root, probes=_ready_probes())
        assert needed_steps(facts) == []


def test_missing_steps_keep_order():
    facts = {step: False for step in (
        "python", "vc_redist", "torch", "tts", "ffmpeg", "ollama", "gemma", "xtts",
    )}
    assert needed_steps(facts) == [
        "python", "vc_redist", "torch", "tts", "ffmpeg", "ollama", "gemma", "xtts",
    ]
    facts["python"] = True
    facts["ffmpeg"] = True
    pending = needed_steps(facts)
    assert "python" not in pending
    assert "ffmpeg" not in pending
    assert pending[0] == "vc_redist"
    assert pending.index("torch") < pending.index("tts")
    assert pending.index("ollama") < pending.index("gemma")


def test_format_download_without_size():
    assert "MB recebidos" in format_download(5 * 1024 * 1024, 0)
    assert "50%" in format_download(50, 100)


def test_reclaim_moves_runtime_out_of_dist():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "dist" / "runtime" / "python"
        src.mkdir(parents=True)
        (src / "python.exe").write_bytes(b"")
        reclaim_misplaced_runtime(root, log=lambda _message: None)
        assert (root / "runtime" / "python" / "python.exe").is_file()
        assert not (root / "dist" / "runtime" / "python" / "python.exe").exists()


def test_tts_rejects_python_312():
    assert python_supports_tts((3, 10))
    assert python_supports_tts((3, 11))
    assert not python_supports_tts((3, 12))
    assert not python_supports_tts((3, 8))


def test_torch_index():
    assert torch_index(False).endswith("/cpu")
    assert "cu124" in torch_index(True)
    cuda = [str(part) for part in torch_install_args(Path("python"), True)]
    assert "torch==2.6.0+cu124" in cuda
    assert "https://pypi.org/simple" in cuda
    cpu = [str(part) for part in torch_install_args(Path("python"), False)]
    assert "torch==2.6.0+cpu" in cpu


if __name__ == "__main__":
    test_skip_when_present()
    test_missing_steps_keep_order()
    test_format_download_without_size()
    test_reclaim_moves_runtime_out_of_dist()
    test_tts_rejects_python_312()
    test_torch_index()
    print("ok")

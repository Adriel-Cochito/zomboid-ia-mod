"""
Prepara o ambiente de quem baixa o daemon e não tem Python, Ollama nem bibliotecas.
Não altera o Python do sistema: tudo fica em runtime/, ao lado deste programa.

O Coqui TTS só instala no Python 3.9, 3.10 ou 3.11. O preparador procura um
desses que já esteja no computador e cria uma cópia em runtime/venv.
Não remove o Python do sistema.

Na pasta daemon-ia:  python instalar.py
O executável de distribuição sai de build_preparar.ps1.
"""
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import winreg
import zipfile
from pathlib import Path

if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).resolve().parent
else:
    _ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.user_settings import app_dir  # noqa: E402

PYTHON_VERSION = "3.11.9"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-amd64.exe"
PYTHON_STANDALONE = Path(r"C:\DaemonZomboid\python")
VC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
FFMPEG_URLS = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
)
OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"
XTTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_TRANSFORMERS = "transformers==4.40.2"
STEP_ORDER = ("python", "vc_redist", "torch", "tts", "ffmpeg", "ollama", "gemma", "xtts")
_UA = "daemon-ia-preparar"


class InstallError(Exception):
    pass


PYPI_INDEX = "https://pypi.org/simple"
TORCH_BUILD = "2.6.0"


def torch_index(nvidia: bool) -> str:
    return TORCH_CUDA_INDEX if nvidia else TORCH_CPU_INDEX


def torch_install_args(python: Path, nvidia: bool) -> list:
    """O índice CUDA não tem as dependências. O PyPI entra só para elas.

    A versão fica com +cu124 ou +cpu para o pip não trocar pelo torch comum.
    """
    tag = "cu124" if nvidia else "cpu"
    return [
        python, "-m", "pip", "install",
        f"torch=={TORCH_BUILD}+{tag}",
        f"torchaudio=={TORCH_BUILD}+{tag}",
        "--index-url", torch_index(nvidia),
        "--extra-index-url", PYPI_INDEX,
    ]


def needed_steps(facts: dict) -> list:
    return [step for step in STEP_ORDER if not facts.get(step)]


def python_supports_tts(version: tuple) -> bool:
    """O Coqui TTS publicado para no 3.11. O 3.12 não tem pacote."""
    return len(version) >= 2 and (3, 9) <= (version[0], version[1]) < (3, 12)


def _private_candidates(root: Path) -> tuple:
    return (
        root / "runtime" / "venv" / "Scripts" / "python.exe",
        root / "runtime" / "python" / "python.exe",
    )


def _version_of(exe: Path):
    if not exe.is_file() or exe.stat().st_size < 64:
        return None
    try:
        completed = subprocess.run(
            [str(exe), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = (completed.stdout or "").split()
    if completed.returncode != 0 or len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def _python_exe(root: Path) -> Path:
    present = [path for path in _private_candidates(root) if path.is_file()]
    for path in present:
        version = _version_of(path)
        if version is not None and python_supports_tts(version):
            return path
    if present:
        return present[0]
    return _private_candidates(root)[0]


def _compatible_base() -> Path | None:
    """Python 3.9, 3.10 ou 3.11 já instalado. O 3.12 do PATH não serve para o TTS."""
    for minor in (11, 10, 9):
        completed = subprocess.run(
            ["py", f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        text = (completed.stdout or "").strip()
        if completed.returncode != 0 or not text:
            continue
        path = Path(text)
        version = _version_of(path)
        if version is not None and python_supports_tts(version):
            return path
    found = shutil.which("python")
    if not found:
        return None
    path = Path(found)
    version = _version_of(path)
    if version is not None and python_supports_tts(version):
        return path
    return None


def _remove_tree(path: Path) -> None:
    def onerror(func, file_path, _exc):
        os.chmod(file_path, stat.S_IWRITE)
        func(file_path)

    shutil.rmtree(path, onerror=onerror)


def _ffmpeg_exe(root: Path) -> Path:
    return root / "runtime" / "ffmpeg" / "bin" / "ffmpeg.exe"


def xtts_ready(root: Path) -> bool:
    return (root / "runtime" / "tts_models" / ".xtts_ready").is_file()


def vc_redist_installed() -> bool:
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, _kind = winreg.QueryValueEx(key, "Installed")
            return int(value) == 1
    except OSError:
        return False


def nvidia_smi_ok() -> bool:
    try:
        completed = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=20, check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ollama_exe() -> Path:
    found = shutil.which("ollama")
    candidates = []
    if found:
        candidates.append(Path(found))
    local = os.environ.get("LOCALAPPDATA", "")
    program = os.environ.get("ProgramFiles", "")
    candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    candidates.append(Path(program) / "Ollama" / "ollama.exe")
    for path in candidates:
        if path.is_file():
            return path
    return None


def gather_facts(root: Path, probes: dict = None) -> dict:
    """O que já está pronto. probes substitui checagens de rede, registro e processos."""
    probes = probes or {}
    root = Path(root)

    def probe(name, default):
        if name in probes:
            return bool(probes[name]())
        return bool(default())

    return {
        "python": probe("python", lambda: _python_exe(root).is_file()),
        "vc_redist": probe("vc_redist", vc_redist_installed),
        "torch": probe("torch", lambda: False),
        "tts": probe("tts", lambda: False),
        "ffmpeg": probe("ffmpeg", lambda: _ffmpeg_exe(root).is_file()),
        "ollama": probe("ollama", lambda: False),
        "gemma": probe("gemma", lambda: False),
        "xtts": probe("xtts", lambda: xtts_ready(root)),
        "nvidia": probe("nvidia", nvidia_smi_ok),
    }


def live_facts(root: Path) -> dict:
    """Checagem real, usada pelo preparador. torch e TTS só existem no Python privado."""
    python = _python_exe(root)
    version = _version_of(python) if python.is_file() else None
    python_ok = version is not None and python_supports_tts(version)
    ollama = ollama_exe()

    def module_ok(code: str) -> bool:
        if not python_ok:
            return False
        completed = subprocess.run(
            [str(python), "-c", code], capture_output=True, timeout=120, check=False,
        )
        return completed.returncode == 0

    def ollama_up() -> bool:
        if ollama is None:
            return False
        from src.user_settings import connection_status
        return connection_status(timeout=2).get("ollama_ok", False)

    def gemma_up() -> bool:
        if ollama is None or not ollama_up():
            return False
        completed = subprocess.run(
            [str(ollama), "list"], capture_output=True, text=True, timeout=30, check=False,
        )
        return _ollama_model() in (completed.stdout or "")

    return gather_facts(root, probes={
        "python": lambda: python_ok,
        "torch": lambda: module_ok("import torch"),
        "tts": lambda: module_ok("import TTS"),
        "ollama": lambda: ollama_exe() is not None,
        "gemma": gemma_up,
        "nvidia": nvidia_smi_ok,
        "vc_redist": vc_redist_installed,
    })


def _ollama_model() -> str:
    from src.config import OLLAMA_MODEL
    return OLLAMA_MODEL


def _log_default(message: str) -> None:
    print(message, flush=True)


def format_download(done: int, total: int) -> str:
    received = done / (1024 * 1024)
    if total:
        whole = total / (1024 * 1024)
        percent = int(done * 100 / total)
        return f"  {received:.1f} MB de {whole:.1f} MB ({percent}%)"
    return f"  {received:.1f} MB recebidos"


def download(url: str, dest: Path, log) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    log(f"Baixando {url}")
    request = urllib.request.Request(url, headers={"User-Agent": _UA})
    done = 0
    reported = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if done - reported >= 1024 * 1024:
                    reported = done
                    log(format_download(done, total))
        if done <= 0:
            raise InstallError(f"Download vazio: {url}")
        partial.replace(dest)
    except Exception:
        try:
            partial.unlink()
        except OSError:
            pass
        raise
    log(f"Download concluído. {format_download(done, done)}")


def _run(cmd, log, env=None, cwd=None) -> None:
    log(" ".join(str(part) for part in cmd))
    process = subprocess.Popen(
        [str(part) for part in cmd],
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout is not None:
        for line in process.stdout:
            text = line.rstrip()
            if text:
                log(text)
    code = process.wait()
    if code != 0:
        raise InstallError(f"Comando falhou ({code}): {cmd[0]}")


def _clear_stale_user_python(version: str, log) -> None:
    """Apaga o registro só quando a pasta do Python já não existe. Não desinstala nada."""
    key_path = rf"Software\Python\PythonCore\{version}\InstallPath"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            install_path, _ = winreg.QueryValueEx(key, "")
    except OSError:
        return
    if (Path(install_path) / "python.exe").is_file():
        return
    log(f"O registro do Python {version} aponta para uma pasta que não existe mais.")
    subprocess.run(
        ["reg", "delete", rf"HKCU\Software\Python\PythonCore\{version}", "/f"],
        check=False, capture_output=True,
    )


def _install_standalone_python(root: Path, log) -> Path:
    target = PYTHON_STANDALONE
    exe = target / "python.exe"
    version = _version_of(exe)
    if version is not None and python_supports_tts(version):
        return exe
    installer = root / "runtime" / "python-installer.exe"
    download(PYTHON_URL, installer, log)
    _clear_stale_user_python("3.11", log)
    log(f"Instalando Python {PYTHON_VERSION} em {target}. O Python do sistema não é removido.")
    command = [
        str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=0",
        "Include_launcher=0", "Include_test=0", "Include_doc=0",
        "Include_pip=1", "Include_tcltk=1", "AssociateFiles=0", "Shortcuts=0",
        f"TargetDir={target}",
    ]
    log(" ".join(command))
    completed = subprocess.run(command, check=False)
    log(f"Código de saída: {completed.returncode}")
    if not exe.is_file():
        raise InstallError(f"O Python {PYTHON_VERSION} não apareceu em {target}.")
    return exe


def install_python(root: Path, log) -> None:
    venv = root / "runtime" / "venv"
    venv_py = venv / "Scripts" / "python.exe"
    venv_version = _version_of(venv_py)
    if venv_py.is_file() and not python_supports_tts(venv_version or ()):
        shown = ".".join(str(part) for part in venv_version) if venv_version else "desconhecida"
        log(f"A cópia em runtime\\venv é Python {shown}. O Coqui TTS só instala até o 3.11.")
        log("Apagando só essa cópia. O Python do sistema continua instalado.")
        _remove_tree(venv)
    current = _python_exe(root)
    current_version = _version_of(current)
    if current.is_file() and python_supports_tts(current_version or ()):
        log(f"Python do daemon já existe: {current}")
        return
    base = _compatible_base()
    if base is None:
        base = _install_standalone_python(root, log)
        log(f"Cópia local a partir de {base}.")
    else:
        base_version = _version_of(base)
        shown = ".".join(str(part) for part in base_version) if base_version else "?"
        log(f"Usando o Python {shown} que já está no computador ({base}).")
    try:
        _run([base, "-m", "venv", str(venv)], log)
    except InstallError:
        log("Criando a cópia sem o pip embutido e colocando o pip só nela.")
        if venv.exists():
            _remove_tree(venv)
        _run([base, "-m", "venv", str(venv), "--without-pip"], log)
    if not venv_py.is_file():
        raise InstallError("Não foi possível criar runtime\\venv.")
    probe = subprocess.run([str(venv_py), "-m", "pip", "--version"], capture_output=True, check=False)
    if probe.returncode != 0:
        get_pip = root / "runtime" / "get-pip.py"
        log("Colocando o pip só dentro de runtime\\venv.")
        download("https://bootstrap.pypa.io/get-pip.py", get_pip, log)
        _run([venv_py, str(get_pip)], log)
    if not venv_py.is_file():
        raise InstallError("O Python do daemon não apareceu em runtime\\venv.")


def install_vc_redist(root: Path, log) -> None:
    dest = root / "runtime" / "vc_redist.x64.exe"
    download(VC_REDIST_URL, dest, log)
    log("Instalando Visual C++. O Windows pode pedir permissão.")
    completed = subprocess.run(
        [str(dest), "/install", "/quiet", "/norestart"], check=False,
    )
    if completed.returncode not in (0, 1638, 3010):
        raise InstallError(f"Visual C++ retornou {completed.returncode}.")


def install_torch(root: Path, nvidia: bool, log) -> None:
    python = _python_exe(root)
    kind = "CUDA" if nvidia else "CPU"
    log(f"Instalando PyTorch ({kind}).")
    _run([python, "-m", "pip", "install", "typing-extensions>=4.10"], log)
    _run(torch_install_args(python, nvidia), log)


def install_tts(root: Path, log) -> None:
    python = _python_exe(root)
    freeze = subprocess.run(
        [str(python), "-m", "pip", "freeze"],
        capture_output=True, text=True, check=False,
    )
    if freeze.returncode != 0:
        raise InstallError("Não foi possível ler as versões do PyTorch.")
    pinned = []
    for line in freeze.stdout.splitlines():
        name = line.split("==", 1)[0].strip().lower()
        if name in ("torch", "torchaudio", "torchvision"):
            pinned.append(line.strip())
    if not any(item.startswith("torch==") for item in pinned):
        raise InstallError("O PyTorch não está instalado no Python privado.")
    constraints = root / "runtime" / "torch-constraint.txt"
    constraints.write_text("\n".join(pinned) + "\n", encoding="utf-8")
    log("Instalando Coqui TTS sem trocar o PyTorch.")
    _run([python, "-m", "pip", "install", "TTS", "-c", constraints], log)
    ensure_xtts_imports(python, log)


def ensure_xtts_imports(python: Path, log) -> None:
    """O TTS puxa um transformers novo, que não tem mais BeamSearchScorer."""
    probe = subprocess.run(
        [str(python), "-c",
         "from transformers import BeamSearchScorer, ConstrainedBeamSearchScorer"],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode == 0:
        return
    log("Ajustando o transformers para a versão que o XTTS ainda importa.")
    _run([python, "-m", "pip", "install", XTTS_TRANSFORMERS], log)


def install_ffmpeg(root: Path, log) -> None:
    archive = root / "runtime" / "ffmpeg.zip"
    unpack = root / "runtime" / "ffmpeg_unpack"
    last_error = None
    for url in FFMPEG_URLS:
        try:
            download(url, archive, log)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            log(f"Esse download falhou ({exc}). Tentando outro endereço.")
            try:
                archive.unlink()
            except OSError:
                pass
    if last_error is not None:
        raise InstallError(f"Não foi possível baixar o ffmpeg: {last_error}")
    if unpack.exists():
        shutil.rmtree(unpack)
    unpack.mkdir(parents=True)
    with zipfile.ZipFile(archive) as packed:
        packed.extractall(unpack)
    exe = next(unpack.rglob("ffmpeg.exe"), None)
    if exe is None:
        raise InstallError("O pacote do ffmpeg não trouxe ffmpeg.exe.")
    dest = root / "runtime" / "ffmpeg" / "bin"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(exe.parent, dest)
    shutil.rmtree(unpack, ignore_errors=True)


def ollama_api_up() -> bool:
    from src.user_settings import connection_status
    return connection_status(timeout=2).get("ollama_ok", False)


def ensure_ollama_server(log, wait_s: int = 90) -> None:
    """O instalador abre o Ollama depois. O pull só funciona com a porta 11434 no ar."""
    exe = ollama_exe()
    if exe is None:
        raise InstallError("Ollama não encontrado.")
    if ollama_api_up():
        log("Ollama já está respondendo.")
        return
    app = exe.with_name("ollama app.exe")
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    if app.is_file():
        log("Abrindo o aplicativo do Ollama.")
        subprocess.Popen([str(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    else:
        log("Abrindo o servidor do Ollama.")
        subprocess.Popen(
            [str(exe), "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if ollama_api_up():
            log("Ollama respondeu na porta 11434.")
            return
        left = max(0, int(deadline - time.time()))
        log(f"Aguardando o Ollama abrir ({left}s).")
        time.sleep(3)
    raise InstallError("O Ollama não abriu a porta 11434 a tempo.")


def install_ollama(root: Path, log) -> None:
    if ollama_exe() is not None:
        log("Ollama já está instalado. Não vou baixar de novo.")
        return
    dest = root / "runtime" / "OllamaSetup.exe"
    download(OLLAMA_URL, dest, log)
    log("Instalando o Ollama. O Windows pode pedir permissão.")
    completed = subprocess.run([str(dest), "/VERYSILENT", "/NORESTART"], check=False)
    if completed.returncode not in (0, 3010):
        raise InstallError(f"O instalador do Ollama retornou {completed.returncode}.")
    if ollama_exe() is None:
        raise InstallError("Ollama instalado, mas ollama.exe não foi encontrado.")


def install_gemma(log) -> None:
    exe = ollama_exe()
    if exe is None:
        raise InstallError("Ollama não encontrado para baixar o modelo.")
    ensure_ollama_server(log)
    model = _ollama_model()
    log(f"Baixando o modelo {model}.")
    try:
        _run([exe, "pull", model], log)
    except InstallError:
        log("O download do modelo falhou porque o Ollama ainda estava fechado. Tentando de novo.")
        ensure_ollama_server(log)
        _run([exe, "pull", model], log)


def install_xtts(root: Path, log) -> None:
    python = _python_exe(root)
    ensure_xtts_imports(python, log)
    home = root / "runtime" / "tts_models"
    home.mkdir(parents=True, exist_ok=True)
    script = root / "runtime" / "_preload_xtts.py"
    script.write_text(
        "import os\n"
        "os.environ['COQUI_TOS_AGREED'] = '1'\n"
        "from pathlib import Path\n"
        "import torch\n"
        "_load = torch.load\n"
        "def load(*args, **kwargs):\n"
        "    kwargs.setdefault('weights_only', False)\n"
        "    return _load(*args, **kwargs)\n"
        "torch.load = load\n"
        "from TTS.api import TTS\n"
        f"TTS({XTTS_MODEL!r})\n"
        "Path(os.environ['TTS_HOME'], '.xtts_ready').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["TTS_HOME"] = str(home)
    env["COQUI_TOS_AGREED"] = "1"
    ffmpeg = root / "runtime" / "ffmpeg" / "bin"
    if ffmpeg.is_dir():
        env["PATH"] = str(ffmpeg) + os.pathsep + env.get("PATH", "")
    log("Baixando o modelo de voz XTTS-v2. Isso leva vários GB.")
    _run([python, str(script)], log, env=env)


_RUNNERS = {
    "python": lambda root, facts, log: install_python(root, log),
    "vc_redist": lambda root, facts, log: install_vc_redist(root, log),
    "torch": lambda root, facts, log: install_torch(root, facts.get("nvidia", False), log),
    "tts": lambda root, facts, log: install_tts(root, log),
    "ffmpeg": lambda root, facts, log: install_ffmpeg(root, log),
    "ollama": lambda root, facts, log: install_ollama(root, log),
    "gemma": lambda root, facts, log: install_gemma(log),
    "xtts": lambda root, facts, log: install_xtts(root, log),
}


def reclaim_misplaced_runtime(root: Path, log=None) -> None:
    """O Preparar.exe gravou em dist/runtime. Traz isso para a pasta do daemon."""
    log = log or _log_default
    dest = root / "runtime"
    src = root / "dist" / "runtime"
    if (dest / "python" / "python.exe").is_file() or not (src / "python" / "python.exe").is_file():
        return
    if not dest.exists():
        log("Aproveitando o que já foi instalado em dist\\runtime")
        shutil.move(str(src), str(dest))
        return
    log("Juntando o que já foi instalado em dist\\runtime")
    for item in list(src.iterdir()):
        target = dest / item.name
        if target.exists():
            continue
        shutil.move(str(item), str(target))


def open_config(root: Path) -> None:
    python = _python_exe(root)
    launcher = str(python) if python.is_file() else sys.executable
    subprocess.Popen([launcher, str(root / "configurar.py")], cwd=str(root))


def run_prepare(root: Path = None, log=None, facts: dict = None) -> list:
    """Executa só os passos que facts marcar como faltando. Devolve a lista que rodou."""
    root = Path(root) if root else app_dir()
    log = log or _log_default
    facts = dict(facts if facts is not None else live_facts(root))
    pending = set(needed_steps(facts))
    if not pending:
        log("Tudo que o daemon precisa já está instalado.")
        return []
    log("O que já estiver instalado é pulado. O download que faltar passa de vários GB.")
    log("A licença do XTTS-v2 é de uso não comercial.")
    ran = []
    for step in STEP_ORDER:
        if step not in pending:
            log(f"--- {step}: já instalado, pulando ---")
            continue
        log(f"--- {step} ---")
        _RUNNERS[step](root, facts, log)
        ran.append(step)
    log("Ambiente pronto.")
    return ran


def run_and_open(root: Path = None) -> None:
    root = Path(root) if root else app_dir()
    reclaim_misplaced_runtime(root)
    run_prepare(root)
    _log_default("Abrindo a tela de configuração.")
    open_config(root)


def main() -> int:
    try:
        run_and_open()
    except Exception as exc:
        _log_default(f"ERRO: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

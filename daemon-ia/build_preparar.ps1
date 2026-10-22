# Gera Preparar.exe. Nao usa o pip do Python do sistema (ele pode nao existir
# ou estar sem permissao). A janela fica aberta ate voce apertar Enter.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location -LiteralPath $root
$log = Join-Path $root "build_preparar.log"
Set-Content -LiteralPath $log -Value "inicio $(Get-Date -Format o)" -Encoding utf8

function Say([string]$Message) {
    Write-Host $Message
    Add-Content -LiteralPath $log -Value $Message -Encoding utf8
}

try {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { $pythonCmd = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $pythonCmd) {
        throw "Python nao encontrado no PATH. Instale Python 3.11 ou mais novo marcando Add python.exe to PATH."
    }
    $python = $pythonCmd.Source
    Say "Python: $python"

    $venv = Join-Path $root "runtime\build-venv"
    $venvPy = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Say "Criando Python local em runtime\build-venv"
        & $python -m venv $venv --without-pip
        if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel criar o ambiente em runtime\build-venv." }
    }

    & $venvPy -m pip --version
    if ($LASTEXITCODE -ne 0) {
        $getPip = Join-Path $root "runtime\get-pip.py"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $getPip) | Out-Null
        Say "Baixando pip para o Python local"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
        & $venvPy $getPip
        if ($LASTEXITCODE -ne 0) { throw "A instalacao do pip no Python local falhou." }
    }

    Say "Instalando PyInstaller no Python local"
    & $venvPy -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller falhou." }

    Say "Gerando Preparar.exe"
    & $venvPy -m PyInstaller --noconfirm --onefile --windowed --name Preparar --paths . --hidden-import tkinter --hidden-import tkinter.ttk instalar.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

    Say "Gerado: $(Join-Path $root 'dist\Preparar.exe')"
    Say "Execute esse arquivo para baixar Python, bibliotecas, Ollama e os modelos."
}
catch {
    Say "ERRO: $($_.Exception.Message)"
    if ($_.ScriptStackTrace) { Say $_.ScriptStackTrace }
}
finally {
    Write-Host ""
    Read-Host "Enter para fechar"
}

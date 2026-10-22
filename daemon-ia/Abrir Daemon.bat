@echo off
cd /d "%~dp0"
if exist "%~dp0runtime\ffmpeg\bin" set "PATH=%~dp0runtime\ffmpeg\bin;%PATH%"
if exist "%~dp0runtime\python\python.exe" (
  set "TTS_HOME=%~dp0runtime\tts_models"
  "%~dp0runtime\python\python.exe" "%~dp0configurar.py"
) else (
  python "%~dp0configurar.py"
)

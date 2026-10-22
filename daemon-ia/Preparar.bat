@echo off
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python nao encontrado no PATH.
  echo O preparador precisa de um Python apenas para comecar. O resto fica em runtime\.
  pause
  exit /b 1
)
python instalar.py
if errorlevel 1 (
  echo.
  echo A preparacao falhou. Veja as linhas acima.
  pause
  exit /b 1
)

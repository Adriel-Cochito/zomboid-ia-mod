@echo off
cd /d "%~dp0"
set "AQUI=%~dp0"
if "%AQUI:~-1%"=="\" set "AQUI=%AQUI:~0,-1%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'Iniciar Daemon Zomboid.lnk')); $s.TargetPath='%~f0'; $s.WorkingDirectory='%AQUI%'; $s.Description='Instala o que faltar e abre a voz do Project Zomboid'; $s.Save()"

if not exist "%AQUI%\daemon-ia\instalar.py" (
  echo Nao achei a pasta daemon-ia ao lado deste arquivo.
  echo Ela precisa ficar junta com o iniciar.bat.
  echo.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python nao encontrado.
  echo Na primeira vez o Windows precisa de um Python instalado so para comecar.
  echo O resto e baixado aqui na pasta, sem mexer no resto do computador.
  echo.
  pause
  exit /b 1
)

cd /d "%AQUI%\daemon-ia"
python instalar.py
if errorlevel 1 (
  echo.
  echo Algo deu errado. Olhe as linhas acima.
  echo Se a janela perguntar y/n, digite y e aperte Enter.
  echo.
  pause
  exit /b 1
)

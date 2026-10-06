@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher nao encontrado. Instale Python 3.9 ou superior e marque "Add Python to PATH".
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 (
  echo Nao foi possivel criar o ambiente virtual.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo A instalacao falhou. Verifique sua conexao e tente novamente.
  pause
  exit /b 1
)
echo Instalacao concluida. Agora execute run_windows.bat.
pause

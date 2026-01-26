@echo off
REM VigilantCore Launcher (Windows)
REM
REM Usage:
REM   run.bat          - Start web dashboard (default)
REM   run.bat web      - Start web dashboard
REM   run.bat qt       - Start Qt desktop app
REM   run.bat both     - Start both (web in background)
REM   run.bat stop     - Stop all instances
REM   run.bat status   - Check status

setlocal

cd /d "%~dp0"

REM Create venv if needed
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Upgrade pip quietly
python -m pip install -q --upgrade pip 2>nul

REM Check if dependencies are installed
python -c "import flask, PySide6, ollama" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -q -r requirements.txt
)

REM Run the launcher with argument (default: web)
if "%~1"=="" (
    python vigilant.py web
) else (
    python vigilant.py %1
)

endlocal

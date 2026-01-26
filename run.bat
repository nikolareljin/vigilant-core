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

REM Check for Ollama and install if needed
where ollama >nul 2>&1
if errorlevel 1 (
    echo Ollama not found. Installing via winget...
    where winget >nul 2>&1
    if not errorlevel 1 (
        winget install -e --id Ollama.Ollama --silent
        echo Please restart this script after Ollama installation completes.
        pause
        exit /b 0
    ) else (
        echo Warning: winget not found. Install Ollama from https://ollama.com/download
    )
)

REM Start Ollama service if not running and Ollama is available
where ollama >nul 2>&1
if not errorlevel 1 (
    tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
    if errorlevel 1 (
        echo Starting Ollama service...
        start /B ollama serve
        timeout /t 2 /nobreak >nul
    )
    
    REM Download default model if not present
    set "DEFAULT_MODEL=llama3.2:1b"
    ollama list | find "!DEFAULT_MODEL!" >nul 2>&1
    if errorlevel 1 (
        echo Downloading Ollama model: !DEFAULT_MODEL!...
        ollama pull !DEFAULT_MODEL! || echo Warning: Failed to download model.
    )
)

REM Run the launcher with argument (default: web)
if "%~1"=="" (
    python vigilant.py web
) else (
    python vigilant.py %1
)

endlocal

@echo off
REM VigilantCore Quickstart Script (Windows Batch)
REM One-command setup: clone/update repo, install dependencies, Ollama, and run

setlocal EnableDelayedExpansion

set "REPO_URL_DEFAULT=https://github.com/nikolareljin/vigilant-core.git"
set "TARGET_DIR_DEFAULT=vigilant-core"

if not defined REPO_URL set "REPO_URL=%REPO_URL_DEFAULT%"
if not defined TARGET_DIR set "TARGET_DIR=%TARGET_DIR_DEFAULT%"

REM Check for Python
where python >nul 2>&1
if errorlevel 1 (
    echo Python is required but not found in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    exit /b 1
)

REM Check for Git
where git >nul 2>&1
if errorlevel 1 (
    echo Git is required but not found in PATH.
    echo Please install Git from https://git-scm.com/downloads
    exit /b 1
)

REM Clone or update repository
if not exist "%TARGET_DIR%" (
    echo Cloning %REPO_URL% into %TARGET_DIR%
    git clone "%REPO_URL%" "%TARGET_DIR%"
    if errorlevel 1 (
        echo Failed to clone repository
        exit /b 1
    )
)

cd /d "%TARGET_DIR%"

REM Update repository
if exist ".git" (
    echo Updating repository...
    git pull --ff-only
)

if exist "update" (
    call update
) else (
    git submodule update --init --recursive
)

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip and install dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

REM Check for Ollama and install if needed
where ollama >nul 2>&1
if errorlevel 1 (
    echo Ollama not found. Installing via winget...
    where winget >nul 2>&1
    if errorlevel 1 (
        echo.
        echo WARNING: winget not found. Please install Ollama manually:
        echo   1. Download from https://ollama.com/download
        echo   2. Install the downloaded file
        echo   3. Restart this script
        echo.
        pause
        exit /b 1
    ) else (
        winget install -e --id Ollama.Ollama
        REM Refresh PATH to detect newly installed ollama
        echo Please close this window and run the script again to complete setup.
        pause
        exit /b 0
    )
)

REM Start Ollama service if not running
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if errorlevel 1 (
    echo Starting Ollama service...
    start /B ollama serve
    timeout /t 3 /nobreak >nul
)

REM Download default model if not present
set "DEFAULT_MODEL=llama3.2:1b"
ollama list | find "%DEFAULT_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo Downloading Ollama model: %DEFAULT_MODEL%...
    echo This may take a few minutes depending on your connection.
    ollama pull %DEFAULT_MODEL%
    if errorlevel 1 (
        echo Warning: Failed to download model. You can download it later with:
        echo   ollama pull %DEFAULT_MODEL%
    )
) else (
    echo Ollama model %DEFAULT_MODEL% already available.
)

REM Run the application
echo.
echo Starting VigilantCore web dashboard...
python -m src.web_app

endlocal

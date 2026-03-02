@echo off
REM VigilantCore Quickstart Script (Windows Batch)
REM One-command setup: clone/update repo, install dependencies, Ollama, and run

setlocal EnableDelayedExpansion

set "REPO_URL_DEFAULT=https://github.com/nikolareljin/vigilant-core.git"
set "TARGET_DIR_DEFAULT=vigilant-core"

if not defined REPO_URL set "REPO_URL=%REPO_URL_DEFAULT%"
if not defined TARGET_DIR set "TARGET_DIR=%TARGET_DIR_DEFAULT%"

call :resolve_python_312
if errorlevel 2 exit /b 0
if errorlevel 1 exit /b 1

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
REM If an existing venv is not Python 3.12, recreate it to enforce compatibility.
if exist "venv\Scripts\python.exe" (
    set "VENV_PY_VER="
    for /f "usebackq delims=" %%v in (`venv\Scripts\python.exe -c "import sys; print(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))"`) do set "VENV_PY_VER=%%v"
    if not "!VENV_PY_VER!"=="3.12" (
        echo Existing virtual environment uses Python !VENV_PY_VER!, but Python 3.12 is required. Recreating virtual environment...
        rmdir /s /q "venv"
    )
) else (
    if exist "venv" (
        echo Existing virtual environment is invalid or missing python.exe. Recreating virtual environment...
        rmdir /s /q "venv"
    )
)

if not exist "venv" (
    echo Creating virtual environment...
    %PYTHON_LAUNCH% -m venv venv
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
exit /b %ERRORLEVEL%

:resolve_python_312
set "PYTHON_CMD="
set "PYTHON_ARGS="
set "PYTHON_LAUNCH="

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    set "PYTHON_ARGS=-3.12"
    goto :python_ready
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        set "PYTHON_ARGS="
        goto :python_ready
    )
)

echo Python 3.12 is required. Attempting to install Python 3.12.2...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$installer = Join-Path $env:TEMP 'python-3.12.2-amd64.exe'; try { Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe' -OutFile $installer; $sig = Get-AuthenticodeSignature -FilePath $installer; if ($sig.Status -ne 'Valid' -or -not $sig.SignerCertificate -or -not $sig.SignerCertificate.Subject.Contains('Python Software Foundation')) { throw 'Python installer signature validation failed.' }; $process = Start-Process -FilePath $installer -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1' -Wait -PassThru; if ($process.ExitCode -ne 0) { throw ('Python installer failed with exit code ' + $process.ExitCode) } } finally { if (Test-Path $installer) { Remove-Item $installer -Force -ErrorAction SilentlyContinue } }"
if errorlevel 1 (
    echo ERROR: Python installer failed.
    echo Install Python 3.12 manually from https://www.python.org/downloads/release/python-3122/
    exit /b 1
)

echo.
echo Python 3.12.2 installer has completed.
echo Your current CMD session may not see the updated PATH yet.
echo Please close this window, open a new terminal, and run this script again.
echo If needed, install manually from https://www.python.org/downloads/release/python-3122/
exit /b 2

:python_ready
set "PYTHON_LAUNCH=%PYTHON_CMD% %PYTHON_ARGS%"
echo Using Python launcher: %PYTHON_LAUNCH%
exit /b 0

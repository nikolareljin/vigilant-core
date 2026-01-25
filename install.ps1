$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py" }

try {
  & $Python -V | Out-Null
} catch {
  Write-Host "Python 3 is required. Please install Python 3.10+ and retry." -ForegroundColor Red
  exit 1
}

if (-not (Test-Path "venv")) {
  & $Python -m venv venv
}

& .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m src.web_app

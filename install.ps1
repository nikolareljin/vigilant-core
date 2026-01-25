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

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Write-Host "Ollama not found. Attempting install via winget..." -ForegroundColor Yellow
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install -e --id Ollama.Ollama | Out-Null
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
      Write-Host "Ollama install did not complete. Install from https://ollama.com/download and re-run." -ForegroundColor Yellow
    }
  } else {
    Write-Host "winget not found. Install Ollama from https://ollama.com/download and re-run." -ForegroundColor Yellow
  }
}

if (-not (Test-Path "venv")) {
  & $Python -m venv venv
}

& .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m src.web_app

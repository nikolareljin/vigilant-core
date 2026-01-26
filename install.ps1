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
    winget install -e --id Ollama.Ollama --silent
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
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

# Start Ollama service if not running
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  $ollamaProcess = Get-Process -Name ollama -ErrorAction SilentlyContinue
  if (-not $ollamaProcess) {
    Write-Host "Starting Ollama service..." -ForegroundColor Cyan
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
  }
  
  # Download default model if not present
  $defaultModel = "llama3.2:1b"
  $modelList = ollama list 2>&1 | Out-String
  if ($modelList -notmatch $defaultModel) {
    Write-Host "Downloading Ollama model: $defaultModel..." -ForegroundColor Cyan
    Write-Host "This may take a few minutes..." -ForegroundColor Yellow
    try {
      ollama pull $defaultModel
      Write-Host "Model downloaded successfully!" -ForegroundColor Green
    } catch {
      Write-Host "Warning: Failed to download model. You can download it later with: ollama pull $defaultModel" -ForegroundColor Yellow
    }
  } else {
    Write-Host "Ollama model $defaultModel already available." -ForegroundColor Green
  }
}

python -m src.web_app

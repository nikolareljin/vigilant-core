# VigilantCore Launcher (Windows PowerShell)
#
# Usage:
#   .\run.ps1          # Start web dashboard (default)
#   .\run.ps1 web      # Start web dashboard
#   .\run.ps1 qt       # Start Qt desktop app
#   .\run.ps1 both     # Start both (web in background)
#   .\run.ps1 stop     # Stop all instances
#   .\run.ps1 status   # Check status

param(
    [Parameter(Position=0)]
    [string]$Command = "web"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Create venv if needed
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

# Activate venv
& .\venv\Scripts\Activate.ps1

# Upgrade pip quietly
python -m pip install -q --upgrade pip 2>$null

# Check if dependencies are installed
$depCheck = python -c "import flask, PySide6, ollama" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dependencies..."
    python -m pip install -q -r requirements.txt
}

# Check for Ollama and install if needed
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama not found. Installing via winget..." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Ollama.Ollama --silent
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            Write-Host "Please restart this script after Ollama installation completes." -ForegroundColor Yellow
            Read-Host "Press Enter to exit"
            exit 0
        }
    } else {
        Write-Host "Warning: winget not found. Install Ollama from https://ollama.com/download" -ForegroundColor Yellow
    }
}

# Start Ollama service if not running
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    $ollamaProcess = Get-Process -Name ollama -ErrorAction SilentlyContinue
    if (-not $ollamaProcess) {
        Write-Host "Starting Ollama service..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
    
    # Download default model if not present
    $defaultModel = "llama3.2:1b"
    $modelList = ollama list 2>&1 | Out-String
    if ($modelList -notmatch $defaultModel) {
        Write-Host "Downloading Ollama model: $defaultModel..."
        try {
            ollama pull $defaultModel
        } catch {
            Write-Host "Warning: Failed to download model." -ForegroundColor Yellow
        }
    }
}

# Run the launcher
python vigilant.py $Command

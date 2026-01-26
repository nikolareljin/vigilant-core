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

# Run the launcher
python vigilant.py $Command

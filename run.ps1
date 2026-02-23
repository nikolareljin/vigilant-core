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

function Get-ListeningPid {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return $null
}

function Ensure-WebPortAvailable {
    param([string]$Mode)
    if ($Mode -notin @("web", "both")) { return }

    $pid = Get-ListeningPid -Port 8765
    if (-not $pid) { return }

    Write-Host "Port 8765 is already in use. Attempting to stop an existing VigilantCore web instance..."
    try { python vigilant.py stop *> $null } catch { }
    Start-Sleep -Seconds 1

    $pid = Get-ListeningPid -Port 8765
    if (-not $pid) { return }

    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match '^python') {
        Write-Host "Stopping stale VigilantCore web listener (PID $pid)..."
        try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch { }
        Start-Sleep -Seconds 1
    }

    $pid = Get-ListeningPid -Port 8765
    if ($pid) {
        Write-Host "Error: Port 8765 is still in use." -ForegroundColor Red
        Write-Host "Stop the process using it, or run .\run.ps1 stop if it's a stale VigilantCore instance." -ForegroundColor Yellow
        $owner = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($owner) {
            Write-Host ("Listening process: {0} (PID {1})" -f $owner.ProcessName, $pid)
        }
        exit 1
    }
}

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
Ensure-WebPortAvailable -Mode $Command
python vigilant.py $Command

#Requires -Version 5.1
<#
.SYNOPSIS
    VigilantCore Quickstart Script (Windows PowerShell)
    
.DESCRIPTION
    One-command setup: clone/update repo, install dependencies, Ollama, and run
    
.PARAMETER RepoUrl
    Git repository URL (default: https://github.com/nikolareljin/vigilant-core.git)
    
.PARAMETER TargetDir
    Target directory for clone (default: vigilant-core)
    
.EXAMPLE
    .\quickstart.ps1
    .\quickstart.ps1 -TargetDir "my-vigilant"
#>

param(
    [string]$RepoUrl = "https://github.com/nikolareljin/vigilant-core.git",
    [string]$TargetDir = "vigilant-core"
)

$ErrorActionPreference = "Stop"

# Function to check if command exists
function Test-Command {
    param($CommandName)
    $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

# Check for Python
if (-not (Test-Command python)) {
    Write-Host "ERROR: Python is required but not found in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Check Python version
$pythonVersion = python --version 2>&1 | Out-String
if ($pythonVersion -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -ne 3 -or $minor -lt 10 -or $minor -gt 12) {
        Write-Host "ERROR: Python 3.10-3.12 is required for Windows. Found: $pythonVersion" -ForegroundColor Red
        Write-Host "Download Python 3.12 from https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "Note: Python 3.13+ is not supported on Windows." -ForegroundColor Yellow
        exit 1
    }
}

# Check for Git
if (-not (Test-Command git)) {
    Write-Host "ERROR: Git is required but not found in PATH." -ForegroundColor Red
    Write-Host "Please install Git from https://git-scm.com/downloads" -ForegroundColor Yellow
    exit 1
}

# Clone or update repository
if (-not (Test-Path $TargetDir)) {
    Write-Host "Cloning $RepoUrl into $TargetDir" -ForegroundColor Cyan
    git clone $RepoUrl $TargetDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to clone repository" -ForegroundColor Red
        exit 1
    }
}

Set-Location $TargetDir

# Update repository
if (Test-Path ".git") {
    Write-Host "Updating repository..." -ForegroundColor Cyan
    git pull --ff-only
}

if (Test-Path "update") {
    & .\update
} else {
    git submodule update --init --recursive
}

# Create virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet 2>$null
pip install -r requirements.txt --quiet

# Check for Ollama and install if needed
if (-not (Test-Command ollama)) {
    Write-Host "Ollama not found. Installing..." -ForegroundColor Yellow
    
    if (Test-Command winget) {
        Write-Host "Installing Ollama via winget..." -ForegroundColor Cyan
        winget install -e --id Ollama.Ollama --silent
        
        # Refresh environment variables
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        
        # Check if ollama is now available
        if (-not (Test-Command ollama)) {
            Write-Host ""
            Write-Host "WARNING: Ollama installation completed but not yet available in PATH." -ForegroundColor Yellow
            Write-Host "Please:" -ForegroundColor Yellow
            Write-Host "  1. Close this PowerShell window" -ForegroundColor White
            Write-Host "  2. Open a new PowerShell window" -ForegroundColor White
            Write-Host "  3. Run this script again" -ForegroundColor White
            Write-Host ""
            Read-Host "Press Enter to exit"
            exit 0
        }
    } else {
        Write-Host ""
        Write-Host "ERROR: winget not found. Please install Ollama manually:" -ForegroundColor Red
        Write-Host "  1. Download from https://ollama.com/download" -ForegroundColor White
        Write-Host "  2. Install the downloaded file" -ForegroundColor White
        Write-Host "  3. Restart this script" -ForegroundColor White
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Start Ollama service if not running
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
    Write-Host "This may take a few minutes depending on your connection." -ForegroundColor Yellow
    
    try {
        ollama pull $defaultModel
        Write-Host "Model downloaded successfully!" -ForegroundColor Green
    } catch {
        Write-Host "Warning: Failed to download model. You can download it later with:" -ForegroundColor Yellow
        Write-Host "  ollama pull $defaultModel" -ForegroundColor White
    }
} else {
    Write-Host "Ollama model $defaultModel already available." -ForegroundColor Green
}

# Run the application
Write-Host ""
Write-Host "Starting VigilantCore web dashboard..." -ForegroundColor Green
Write-Host "Dashboard will be available at http://127.0.0.1:8765" -ForegroundColor Cyan
Write-Host ""
python -m src.web_app

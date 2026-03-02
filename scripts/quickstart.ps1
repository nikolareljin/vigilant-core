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
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe"
$PythonInstallerPath = Join-Path $env:TEMP "python-3.12.2-amd64.exe"
$PythonExpectedPublisher = "Python Software Foundation"
$PythonExe = $null
$PythonExeArgs = @()

# Function to check if command exists
function Test-Command {
    param($CommandName)
    $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Test-Python312 {
    param(
        [string]$CommandName,
        [string[]]$CommandArgs = @()
    )
    if (-not (Test-Command $CommandName)) {
        return $false
    }

    try {
        & $CommandName @CommandArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Resolve-Python312 {
    if (Test-Python312 -CommandName "py" -CommandArgs @("-3.12")) {
        return @{
            Exe = "py"
            Args = @("-3.12")
        }
    }
    if (Test-Python312 -CommandName "python") {
        return @{
            Exe = "python"
            Args = @()
        }
    }
    return $null
}

function Install-Python312 {
    Write-Host "Python 3.12 not found. Installing Python 3.12.2..." -ForegroundColor Yellow
    Write-Host "Downloading installer from $PythonInstallerUrl" -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $PythonInstallerPath

        # Validate Authenticode signature before execution.
        $sig = Get-AuthenticodeSignature -FilePath $PythonInstallerPath
        if ($sig.Status -ne "Valid" -or -not $sig.SignerCertificate -or -not $sig.SignerCertificate.Subject.Contains($PythonExpectedPublisher)) {
            Write-Host "ERROR: Python installer signature validation failed." -ForegroundColor Red
            return $false
        }

        # Install per-user so quickstart works in non-admin shells.
        $installerProcess = Start-Process -FilePath $PythonInstallerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait -PassThru
        if ($installerProcess.ExitCode -ne 0) {
            Write-Host "ERROR: Python installer failed with exit code $($installerProcess.ExitCode)." -ForegroundColor Red
            Write-Host "Check endpoint protection policy or install Python 3.12 manually." -ForegroundColor Yellow
            return $false
        }
    } finally {
        Remove-Item -Path $PythonInstallerPath -ErrorAction SilentlyContinue
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    return $true
}

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    & $script:PythonExe @($script:PythonExeArgs) @Arguments
}

$pythonCmd = Resolve-Python312
if (-not $pythonCmd) {
    if (-not (Install-Python312)) {
        exit 1
    }
    $pythonCmd = Resolve-Python312
    if (-not $pythonCmd) {
        Write-Host "Python 3.12 installation completed, but this terminal cannot see the updated PATH yet." -ForegroundColor Yellow
        Write-Host "Close this PowerShell window, open a new one, and run this script again." -ForegroundColor Yellow
        exit 0
    }
}
$PythonExe = $pythonCmd.Exe
$PythonExeArgs = $pythonCmd.Args
Write-Host "Using Python launcher: $PythonExe $($PythonExeArgs -join ' ')" -ForegroundColor Green

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
    Invoke-Python -m venv venv
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

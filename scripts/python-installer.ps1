#Requires -Version 5.1
<#
.SYNOPSIS
    Shared Python installer helper for Windows quickstart scripts.

.PARAMETER Version
    Python patch version in X.Y.Z format. Must be 3.12.x.
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$expectedPublisher = "Python Software Foundation"

if ($Version -notmatch '^\d+\.\d+\.\d+$' -or $Version.Contains('/') -or $Version.Contains('\')) {
    Write-Host "ERROR: Invalid Python version '$Version'. Expected X.Y.Z without path separators." -ForegroundColor Red
    exit 1
}
if ($Version -notmatch '^3\.12\.') {
    Write-Host "ERROR: Unsupported Python version '$Version'. This installer currently supports Python 3.12.x only." -ForegroundColor Red
    exit 1
}

$baseUrl = "https://www.python.org/ftp/python/$Version"
$effectiveArch = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) {
    $effectiveArch = $env:PROCESSOR_ARCHITEW6432
}

switch -Regex ($effectiveArch) {
    "ARM64" {
        $installerFile = "python-$Version-arm64.exe"
    }
    "^(x86|X86)$" {
        $installerFile = "python-$Version.exe"
    }
    default {
        $installerFile = "python-$Version-amd64.exe"
    }
}

$installerUrl = "$baseUrl/$installerFile"
$installerPath = Join-Path $env:TEMP $installerFile

Write-Host "Downloading installer from $installerUrl" -ForegroundColor Cyan
try {
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
    } else {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    }

    $sig = Get-AuthenticodeSignature -FilePath $installerPath
    if ($sig.Status -ne "Valid" -or -not $sig.SignerCertificate -or $sig.SignerCertificate.Subject.IndexOf($expectedPublisher, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Write-Host "ERROR: Python installer signature validation failed." -ForegroundColor Red
        exit 1
    }

    $proc = Start-Process -FilePath $installerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1" -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Host "ERROR: Python installer failed with exit code $($proc.ExitCode)." -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host ("ERROR: Failed to download or run Python installer from '{0}' to '{1}': {2}" -f $installerUrl, $installerPath, $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    Remove-Item -Path $installerPath -Force -ErrorAction SilentlyContinue
}

exit 0

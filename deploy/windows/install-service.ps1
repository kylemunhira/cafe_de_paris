#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install Café de Paris as a Windows service using NSSM + Waitress.

.DESCRIPTION
    Registers a Windows service that runs run_waitress.py with the project venv.
    Requires NSSM (https://nssm.cc/download). Default location: C:\nssm\nssm.exe

.EXAMPLE
    .\install-service.ps1
    .\install-service.ps1 -ServiceName "CafeDeParis" -NssmPath "C:\nssm\nssm.exe"
#>
param(
    [string]$ServiceName = "CafeDeParis",
    [string]$NssmPath = "C:\nssm\nssm.exe"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RunScript = Join-Path $ProjectRoot "run_waitress.py"
$LogsDir = Join-Path $ProjectRoot "logs"
$VenvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if (-not (Test-Path $RunScript)) {
    throw "run_waitress.py not found at $RunScript"
}

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonExe) {
        throw "Python not found. Create a venv (python -m venv venv) and install requirements first."
    }
    Write-Warning "venv not found; using $PythonExe"
}

function Find-Nssm {
    param([string]$ExplicitPath)
    if ($ExplicitPath -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }
    foreach ($Candidate in @("C:\nssm\nssm.exe", (Join-Path $PSScriptRoot "nssm\nssm.exe"))) {
        if (Test-Path $Candidate) {
            return (Resolve-Path $Candidate).Path
        }
    }
    $OnPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source
    if ($OnPath) {
        return $OnPath
    }
    throw @"
NSSM not found. Expected at C:\nssm\nssm.exe. Download from https://nssm.cc/download or pass -NssmPath.
"@
}

$Nssm = Find-Nssm -ExplicitPath $NssmPath

$Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($Existing) {
    if ($Existing.Status -eq "Running") {
        Write-Host "Stopping existing service '$ServiceName'..."
        & $Nssm stop $ServiceName confirm
        Start-Sleep -Seconds 2
    }
    Write-Host "Removing existing service '$ServiceName'..."
    & $Nssm remove $ServiceName confirm
    Start-Sleep -Seconds 1
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

Write-Host "Installing service '$ServiceName'..."
Write-Host "  Python:  $PythonExe"
Write-Host "  Script:  $RunScript"
Write-Host "  Workdir: $ProjectRoot"

& $Nssm install $ServiceName $PythonExe $RunScript
& $Nssm set $ServiceName AppDirectory $ProjectRoot
& $Nssm set $ServiceName DisplayName "Cafe de Paris"
& $Nssm set $ServiceName Description "Cafe de Paris Django app (Waitress WSGI server)"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout (Join-Path $LogsDir "service-stdout.log")
& $Nssm set $ServiceName AppStderr (Join-Path $LogsDir "service-stderr.log")
& $Nssm set $ServiceName AppStdoutCreationDisposition 4
& $Nssm set $ServiceName AppStderrCreationDisposition 4
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760

Write-Host "Starting service '$ServiceName'..."
& $Nssm start $ServiceName

Start-Sleep -Seconds 2
$Svc = Get-Service -Name $ServiceName
Write-Host "Service status: $($Svc.Status)"
Write-Host ""
Write-Host "Logs: $LogsDir"
Write-Host "Manage: & '$Nssm' status $ServiceName | restart | stop $ServiceName"

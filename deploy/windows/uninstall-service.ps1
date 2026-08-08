#Requires -RunAsAdministrator
param(
    [string]$ServiceName = "CafeDeParis",
    [string]$NssmPath = "C:\nssm\nssm.exe"
)

$ErrorActionPreference = "Stop"

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
    throw "NSSM not found. Pass -NssmPath or add nssm to PATH."
}

$Nssm = Find-Nssm -ExplicitPath $NssmPath
$Existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

if (-not $Existing) {
    Write-Host "Service '$ServiceName' is not installed."
    exit 0
}

if ($Existing.Status -eq "Running") {
    Write-Host "Stopping '$ServiceName'..."
    & $Nssm stop $ServiceName confirm
    Start-Sleep -Seconds 2
}

Write-Host "Removing '$ServiceName'..."
& $Nssm remove $ServiceName confirm
Write-Host "Done."

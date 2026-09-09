# Deploy kitchen APK OTA update on the Windows production server.
# Run this ON the server (RDP), from the cafe_de_paris app root (e.g. C:\Apps\cafe_de_paris).
#
# Usage:
#   .\deploy\windows\publish-kitchen-apk.ps1 -ApkPath "C:\Users\...\kitchen.apk"
#   .\deploy\windows\publish-kitchen-apk.ps1 -ApkPath ".\releases\kitchen.apk" -VersionCode 4 -VersionName "1.2.3"

param(
    [Parameter(Mandatory = $true)]
    [string]$ApkPath,
    [int]$VersionCode = 4,
    [string]$VersionName = "1.2.3",
    [string]$ReleaseNotes = "HQ admin/superuser branch selection on login",
    [string]$ServiceName = "CafeDeParis",
    [string]$NssmPath = "C:\nssm\nssm.exe"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not (Test-Path $ApkPath)) {
    throw "APK not found: $ApkPath"
}

$releases = Join-Path $Root "releases"
New-Item -ItemType Directory -Force -Path $releases | Out-Null
$dest = Join-Path $releases "kitchen.apk"
Copy-Item $ApkPath $dest -Force
Write-Host "Copied APK -> $dest ($((Get-Item $dest).Length) bytes)"

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    throw ".env not found at $envFile"
}

$raw = Get-Content $envFile -Raw
function Set-EnvKey([string]$text, [string]$key, [string]$value) {
    if ($text -match "(?m)^$key=") {
        return [regex]::Replace($text, "(?m)^$key=.*$", "$key=$value")
    }
    return $text.TrimEnd() + "`r`n$key=$value`r`n"
}

$raw = Set-EnvKey $raw "KITCHEN_APP_VERSION_CODE" "$VersionCode"
$raw = Set-EnvKey $raw "KITCHEN_APP_VERSION_NAME" $VersionName
$raw = Set-EnvKey $raw "KITCHEN_APP_RELEASE_NOTES" $ReleaseNotes
Set-Content -Path $envFile -Value $raw -NoNewline
Write-Host "Updated .env -> version $VersionName ($VersionCode)"

if (Test-Path $NssmPath) {
    & $NssmPath restart $ServiceName
    Write-Host "Restarted service $ServiceName"
} else {
    Write-Warning "NSSM not found at $NssmPath — restart the CafeDeParis service manually."
}

Write-Host ""
Write-Host "Verify: curl http://127.0.0.1:8000/api/app-version/?version_code=3"
Write-Host "Expect update_available=true and latest_version_code=$VersionCode"

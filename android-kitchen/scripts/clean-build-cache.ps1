# Run AFTER closing Android Studio completely.
# Right-click -> "Run with PowerShell" or run from a terminal:
#   powershell -ExecutionPolicy Bypass -File scripts\clean-build-cache.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "Cleaning Android build caches in: $root" -ForegroundColor Cyan

# Stop Gradle daemons if wrapper exists
$gradlew = Join-Path $root "gradlew.bat"
if (Test-Path $gradlew) {
    Write-Host "Stopping Gradle daemons..."
    & $gradlew --stop 2>$null
    Start-Sleep -Seconds 2
}

$targets = @(
    (Join-Path $root "app\build"),
    (Join-Path $root "build"),
    (Join-Path $root ".gradle"),
    (Join-Path $env:LOCALAPPDATA "cafe-de-paris\android-kitchen")
)

foreach ($dir in $targets) {
    if (-not (Test-Path -LiteralPath $dir)) {
        Write-Host "  Skip (not found): $dir"
        continue
    }
    Write-Host "  Removing: $dir"
    try {
        Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction Stop
        Write-Host "    OK" -ForegroundColor Green
    } catch {
        Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "    Close Android Studio, wait 10 seconds, then run this script again." -ForegroundColor Yellow
        Write-Host "    If OneDrive syncs Documents, pause sync or move the repo outside OneDrive." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Done. Reopen Android Studio -> Build -> Rebuild Project." -ForegroundColor Cyan

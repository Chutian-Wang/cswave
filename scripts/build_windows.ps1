param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Push-Location $Root
try {
    $Version = (& $Python -c "from app_info import APP_VERSION; print(APP_VERSION)").Trim()
    & $Python -m pip install -r requirements.txt -r requirements-build.txt
    if (-not $SkipTests) {
        & $Python -m pytest
    }
    & $Python -m PyInstaller --noconfirm --clean cswave.spec

    $ReleaseDir = Join-Path $Root "release"
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    $Zip = Join-Path $ReleaseDir "cswave-$Version-windows-x64.zip"
    if (Test-Path $Zip) {
        Remove-Item -LiteralPath $Zip -Force
    }
    Start-Sleep -Seconds 2
    Compress-Archive -Path (Join-Path $Root "dist\cswave\*") -DestinationPath $Zip
    Write-Host "Created $Zip"
}
finally {
    Pop-Location
}

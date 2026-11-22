# GitHub Release Tracker (Python / PyQt6) - Automated PyInstaller EXE Builder
# Compiles dist\GitHubReleaseTracker.exe, generates dist\GitHubReleaseTracker.exe.sha256,
# and writes dist\release-notes-v2.0.0.md.

param(
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if ((Test-Path "pyqt6-project\github_release_tracker.py") -and -not (Test-Path "github_release_tracker.py")) {
    Set-Location -LiteralPath (Join-Path $PSScriptRoot "pyqt6-project")
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " GitHub Release Tracker (Python / PyQt6) - EXE Builder  " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[X] Python is not installed (python not found in PATH)." -ForegroundColor Red
    Write-Host "    Install Python 3.10+ from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
    exit 1
}

$ver = "2.0.0"
Write-Host "Version: $ver (PyQt6 + PyInstaller single-file .exe)" -ForegroundColor Green
Write-Host ""

Write-Host "[1/4] Setting up virtual environment & installing PyQt6 + PyInstaller ..." -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & python -m venv .venv
}
$venvPy = ".\.venv\Scripts\python.exe"
$venvPyInstaller = ".\.venv\Scripts\pyinstaller.exe"

& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet

if (-not $SkipTests) {
    Write-Host ""
    Write-Host "[2/4] Running built-in Python unit tests (github_release_tracker.py --test) ..." -ForegroundColor Cyan
    & $venvPy github_release_tracker.py --test
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Unit tests failed. Aborting build." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[2/4] Skipping unit tests (-SkipTests)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[3/4] Building dist\GitHubReleaseTracker.exe with PyInstaller ..." -ForegroundColor Cyan
if (Test-Path "icon.ico") {
    & $venvPyInstaller --noconfirm --clean --noconsole --onefile --name GitHubReleaseTracker --icon icon.ico --add-data "icon.ico;." github_release_tracker.py
} else {
    & $venvPyInstaller --noconfirm --clean --noconsole --onefile --name GitHubReleaseTracker github_release_tracker.py
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] PyInstaller build failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[4/4] Packaging dist\GitHubReleaseTracker.exe & SHA-256 checksum ..." -ForegroundColor Cyan
$distExe = "dist\GitHubReleaseTracker.exe"
if (Test-Path "tools\release-notes.ps1") {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "tools\release-notes.ps1" -Version $ver -Exe $distExe -Out "dist\release-notes-v$ver.md"
} else {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $distExe).Hash.ToLower()
    Set-Content -Encoding ASCII -LiteralPath "$distExe.sha256" -Value "$hash  GitHubReleaseTracker.exe"
    Write-Host "SHA-256: $hash"
}

$size = (Get-Item -LiteralPath $distExe).Length
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host " DONE" -ForegroundColor Green
Write-Host "  dist\GitHubReleaseTracker.exe ($size bytes)"
Write-Host "  dist\GitHubReleaseTracker.exe.sha256"
Write-Host "  dist\release-notes-v$ver.md"
Write-Host "========================================================" -ForegroundColor Green

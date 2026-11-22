# GitHub Release Tracker (Rust) - Automated EXE Builder
# Compiles dist\GitHubReleaseTracker.exe, generates dist\GitHubReleaseTracker.exe.sha256,
# and writes dist\release-notes-vX.Y.Z.md.

param(
    [switch]$InstallRust,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if ((Test-Path "rust-project\Cargo.toml") -and -not (Test-Path "Cargo.toml")) {
    Set-Location -LiteralPath (Join-Path $PSScriptRoot "rust-project")
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " GitHub Release Tracker (Rust) - EXE Builder  " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# Check for cargo
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if (Test-Path (Join-Path $cargoBin "cargo.exe")) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
}

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    if ($InstallRust) {
        Write-Host "[*] Rust not found. Downloading rustup-init.exe ..." -ForegroundColor Yellow
        $rustup = Join-Path $env:TEMP "rustup-init.exe"
        Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $rustup
        & $rustup -y --default-toolchain stable-x86_64-pc-windows-msvc --profile minimal
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
    } else {
        Write-Host ""
        Write-Host "[X] Rust is not installed (cargo not found)." -ForegroundColor Red
        Write-Host "    1. Install Rust from https://rustup.rs (default 'MSVC' option)"
        Write-Host "       OR re-run this script with -InstallRust"
        Write-Host "    2. Install 'Build Tools for Visual Studio' with workload 'Desktop development with C++'"
        exit 1
    }
}

# Read version from Cargo.toml
$cargoToml = Get-Content -LiteralPath "Cargo.toml" -Encoding UTF8
$verMatch = ($cargoToml | Select-String -Pattern '^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"').Matches
if (-not $verMatch) {
    Write-Host "[X] Could not read version from Cargo.toml." -ForegroundColor Red
    exit 1
}
$ver = $verMatch[0].Groups[1].Value
Write-Host "Version: $ver (tag v$ver)" -ForegroundColor Green
Write-Host ""

if (-not $SkipTests) {
    Write-Host "[1/3] Running the logic tests (including Source & Target columns) ..." -ForegroundColor Cyan
    & cargo test --lib --locked --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Unit tests failed. Aborting build." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[1/3] Skipping unit tests (-SkipTests)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[2/3] Building release executable (statically linked CRT) ..." -ForegroundColor Cyan
& cargo build --release --locked
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[X] Build failed. Ensure Build Tools for Visual Studio ('Desktop development with C++' + Windows 10/11 SDK) is installed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[3/3] Packaging dist\GitHubReleaseTracker.exe & SHA-256 checksum ..." -ForegroundColor Cyan
if (-not (Test-Path "dist")) {
    New-Item -ItemType Directory -Path "dist" | Out-Null
}
$targetExe = "target\release\github-release-tracker.exe"
$distExe = "dist\GitHubReleaseTracker.exe"
Copy-Item -LiteralPath $targetExe -Destination $distExe -Force

if (Test-Path "tools\release-notes.ps1") {
    & powershell -NoProfile -ExecutionPolicy Bypass -File "tools\release-notes.ps1" -Version $ver -Exe $distExe -Out "dist\release-notes-v$ver.md"
} else {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $distExe).Hash.ToLower()
    Set-Content -Encoding ASCII -LiteralPath "$distExe.sha256" -Value "$hash  GitHubReleaseTracker.exe"
    Write-Host "SHA-256: $hash"
}

$size = (Get-Item -LiteralPath $distExe).Length
Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " DONE" -ForegroundColor Green
Write-Host "  dist\GitHubReleaseTracker.exe ($size bytes)"
Write-Host "  dist\GitHubReleaseTracker.exe.sha256"
Write-Host "  dist\release-notes-v$ver.md"
Write-Host "==============================================" -ForegroundColor Green

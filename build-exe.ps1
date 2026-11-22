# GitHub Release Tracker (Rust) - Automated EXE Builder (Root Wrapper)
param(
    [switch]$InstallRust,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$targetScript = Join-Path $PSScriptRoot "rust-project\build-exe.ps1"
if (Test-Path $targetScript) {
    & $targetScript @PSBoundParameters
} else {
    Write-Error "Could not find rust-project\build-exe.ps1"
}

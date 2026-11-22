# GitHub Release Tracker (Python / PyQt6) - Automated EXE Builder (Root Wrapper)
param(
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$targetScript = Join-Path $PSScriptRoot "pyqt6-project\build-exe.ps1"
if (Test-Path $targetScript) {
    & $targetScript @PSBoundParameters
} else {
    Write-Error "Could not find pyqt6-project\build-exe.ps1"
}

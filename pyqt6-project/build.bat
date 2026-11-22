@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ========================================================
echo  GitHub Release Tracker (Python / PyQt6) - EXE Builder
echo ========================================================

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [X] Python is not installed ^(python not found in PATH^).
    echo     1. Install Python 3.10+ from https://www.python.org/downloads/
    echo        ^(tick "Add python.exe to PATH" during installation^)
    echo     2. Open a NEW window and run build.bat again.
    goto :fail
)

set "VER=2.0.0"
echo Version: %VER%   ^(PyQt6 + PyInstaller single-file .exe^)
echo.

echo [1/4] Creating virtual environment ^& installing PyQt6 + PyInstaller ...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo [X] Failed to create virtual environment.
        goto :fail
    )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [X] Failed to install PyQt6 / PyInstaller from requirements.txt.
    goto :fail
)

echo.
echo [2/4] Running built-in Python unit tests ^(github_release_tracker.py --test^) ...
python github_release_tracker.py --test
if errorlevel 1 (
    echo [X] Unit tests failed. Not building.
    goto :fail
)

echo.
echo [3/4] Building standalone dist\GitHubReleaseTracker.exe with PyInstaller ...
if exist "icon.ico" (
    pyinstaller --noconfirm --clean --noconsole --onefile --name GitHubReleaseTracker --icon icon.ico --add-data "icon.ico;." github_release_tracker.py
) else (
    pyinstaller --noconfirm --clean --noconsole --onefile --name GitHubReleaseTracker github_release_tracker.py
)
if errorlevel 1 (
    echo [X] PyInstaller build failed.
    goto :fail
)

echo.
echo [4/4] Generating SHA-256 checksum and release notes ...
if exist "tools\release-notes.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "tools\release-notes.ps1" -Version "%VER%" -Exe "dist\GitHubReleaseTracker.exe" -Out "dist\release-notes-v%VER%.md"
) else (
    powershell -NoProfile -Command "$h=(Get-FileHash -Algorithm SHA256 'dist\GitHubReleaseTracker.exe').Hash.ToLower(); Set-Content -Encoding ASCII 'dist\GitHubReleaseTracker.exe.sha256' \"$h  GitHubReleaseTracker.exe\"; Write-Host \"SHA-256: $h\""
)

echo.
echo ========================================================
echo  DONE
echo   dist\GitHubReleaseTracker.exe
echo   dist\GitHubReleaseTracker.exe.sha256
echo   dist\release-notes-v%VER%.md
echo ========================================================
for %%F in ("dist\GitHubReleaseTracker.exe") do echo  Size: %%~zF bytes
if not defined CI pause
exit /b 0

:fail
echo.
if not defined CI pause
exit /b 1

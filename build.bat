@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "rust-project\build.bat" (
    cd /d "%~dp0rust-project"
    call build.bat
    exit /b %ERRORLEVEL%
)
echo [X] Could not find rust-project\build.bat
exit /b 1

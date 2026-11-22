@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "pyqt6-project\build.bat" (
    cd /d "%~dp0pyqt6-project"
    call build.bat
    exit /b %ERRORLEVEL%
)
echo [X] Could not find pyqt6-project\build.bat
exit /b 1

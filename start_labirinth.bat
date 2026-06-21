@echo off
cd /d "%~dp0"

echo Start folder: %~dp0
echo.

if not exist "%~dp0Demo.exe" (
    echo ERROR: Demo.exe not found in this folder!
    pause
    exit /b 1
)

echo Starting Demo.exe...
start "Demo" /D "%~dp0" "%~dp0Demo.exe"

echo Waiting for Demo.exe to initialize...
timeout /t 3 /nobreak >nul

if not exist "%~dp0start4.py" (
    echo ERROR: start4.py not found in this folder!
    pause
    exit /b 1
)

echo Starting game start4.py...
python "%~dp0start4.py"

pause

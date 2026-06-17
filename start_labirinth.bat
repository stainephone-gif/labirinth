@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Папка запуска: %~dp0
echo.

if not exist "%~dp0Demo.exe" (
    echo ОШИБКА: файл Demo.exe не найден в этой папке!
    pause
    exit /b 1
)

echo Запуск Demo.exe...
start "Demo" /D "%~dp0" "%~dp0Demo.exe"
if errorlevel 1 (
    echo ОШИБКА: не удалось запустить Demo.exe, код %errorlevel%
    pause
    exit /b 1
)

echo Ожидание инициализации Demo.exe...
timeout /t 3 /nobreak >nul

if not exist "%~dp0start4.py" (
    echo ОШИБКА: файл start4.py не найден в этой папке!
    pause
    exit /b 1
)

echo Запуск игры start4.py...
python "%~dp0start4.py"

pause

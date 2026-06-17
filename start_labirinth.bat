@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Запуск Demo.exe...
start "" "%~dp0Demo.exe"

echo Ожидание инициализации Demo.exe...
timeout /t 3 /nobreak >nul

echo Запуск игры start4.py...
python "%~dp0start4.py"

pause

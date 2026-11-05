@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
    echo Установка остановлена. Прочитайте сообщение выше.
    pause
    exit /b %errorlevel%
)
echo Установка завершена. Окно можно закрыть.
pause
exit /b %errorlevel%

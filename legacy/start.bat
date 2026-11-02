@echo off
chcp 65001 >nul
title Yandex Station Telegram Control Bot
cd /d "%~dp0bot"

if exist "..\..\.venv\Scripts\python.exe" (
    set "PY=..\..\.venv\Scripts\python.exe"
) else if exist "..\.venv\Scripts\python.exe" (
    set "PY=..\.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set "PY=py -3"
    ) else (
        where python >nul 2>nul
        if %errorlevel% equ 0 (
            set "PY=python"
        ) else (
            where python3 >nul 2>nul
            if %errorlevel% equ 0 (
                set "PY=python3"
            ) else (
                echo ❌ Python не найден! Установите Python с python.org
                pause
                exit /b 1
            )
        )
    )
)

"%PY%" run_bot.py %*
pause

@echo off
chcp 65001 >nul
title Установка и настройка Yandex Station Telegram Bot
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
                echo =================================================================
                echo ❌ ОШИБКА: Python не найден на вашем компьютере!
                echo =================================================================
                echo Скачайте Python с сайта: https://www.python.org/downloads/
                echo При установке обязательно отметьте галочку:
                echo    [v] "Add python.exe to PATH"
                echo =================================================================
                pause
                exit /b 1
            )
        )
    )
)

"%PY%" setup.py %*
pause

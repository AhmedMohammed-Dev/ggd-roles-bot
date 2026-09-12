@echo off
chcp 65001 >nul
title Goose Goose Duck - Roles Bot
cd /d "%~dp0"

echo ============================================================
echo   Goose Goose Duck  -  Roles Bot  (Arabic Guide)
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python is not installed.
    echo     Download it from https://www.python.org/downloads/
    echo     IMPORTANT: tick "Add python.exe to PATH" during the install.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating the virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :failed
) else (
    echo [1/4] Virtual environment OK.
)

echo [2/4] Installing libraries ^(about 1 minute the first time^)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto :failed

echo [3/4] Checking your settings and the token...
".venv\Scripts\python.exe" check_setup.py
if errorlevel 1 (
    echo.
    echo [X] Fix the problems above first ^(the token lives in the .env file^).
    echo.
    pause
    exit /b 1
)

echo [4/4] Starting the bot...  ^(press Ctrl+C to stop^)
echo.
".venv\Scripts\python.exe" -u bot.py

echo.
echo Bot stopped.
pause
exit /b 0

:failed
echo.
echo [X] Setup failed. Make sure you are connected to the internet.
echo.
pause
exit /b 1

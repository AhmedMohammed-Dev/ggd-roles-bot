@echo off
chcp 65001 >nul
title Push the bot to GitHub
cd /d "%~dp0"

echo ============================================================
echo   Step 1 of the hosting setup: upload the code to GitHub
echo ============================================================
echo.
echo BEFORE you continue, create an EMPTY PRIVATE repo named  ggd-roles-bot
echo here (do not add a README or .gitignore):
echo     https://github.com/new
echo.
set /p GHUSER=Type your GitHub username and press Enter:
if "%GHUSER%"=="" (
    echo.
    echo [X] You must type your GitHub username.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [X] Git is not installed. Get it from https://git-scm.com/downloads
    pause
    exit /b 1
)

echo.
echo Linking to https://github.com/%GHUSER%/ggd-roles-bot.git ...
git remote remove origin >nul 2>nul
git remote add origin "https://github.com/%GHUSER%/ggd-roles-bot.git"
git branch -M main

echo Uploading the code ...
git push -u origin main
if errorlevel 1 (
    echo.
    echo [X] Upload failed. The most common causes:
    echo     1. The repository does not exist yet  -^> create it at https://github.com/new
    echo     2. Wrong username  -^> run this file again
    echo     3. The repo is not empty  -^> it must have no README/.gitignore
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] The code is on GitHub. The .env file was NOT uploaded (it is ignored).
echo      Next: dashboard.render.com -^> New + -^> Blueprint -^> pick this repo.
echo.
pause
exit /b 0

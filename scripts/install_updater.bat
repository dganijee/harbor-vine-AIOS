@echo off
REM Install Harbor & Vine Realty FluentOS auto-updater as a Windows scheduled task
REM Runs daily at 4:00 AM to pull latest updates from GitHub

set SCRIPT_DIR=%~dp0
set PYTHON_PATH=python
set UPDATE_SCRIPT=%SCRIPT_DIR%auto_update.py

echo.
echo ============================================
echo   Harbor & Vine Realty FluentOS — Updater Installer
echo ============================================
echo.

REM Create the scheduled task
schtasks /create /tn "HarborVine-FluentOS-AutoUpdate" /tr "\"%PYTHON_PATH%\" \"%UPDATE_SCRIPT%\"" /sc daily /st 04:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo   [OK] Scheduled task created successfully
    echo   Task: HarborVine-FluentOS-AutoUpdate
    echo   Schedule: Daily at 4:00 AM
    echo   Script: %UPDATE_SCRIPT%
    echo.
) else (
    echo.
    echo   [ERROR] Failed to create scheduled task
    echo   Try running this script as Administrator
    echo.
)

pause

@echo off
setlocal enabledelayedexpansion
title OCR Workspace Setup

echo ===================================================
echo     OCR Workspace - 1-Click Setup (Windows)
echo ===================================================
echo.

:: Check for powershell
where powershell >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PowerShell is required but was not found on PATH.
    echo Please install Windows PowerShell or run setup manually.
    pause
    exit /b 1
)

:: Run bootstrap.ps1 with ExecutionPolicy Bypass
echo Running setup script (this may take a few minutes on first run)...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Setup encountered an issue (Exit Code %ERRORLEVEL%).
    echo Please check the error messages above.
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ===================================================
echo Setup finished successfully!
echo To launch the application:
echo   - Double-click run.bat
echo   - Or run: npm run dev
echo ===================================================
echo.
pause

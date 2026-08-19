@echo off
setlocal enabledelayedexpansion
title OCR Workspace - Running

echo ===================================================
echo     OCR Workspace - Starting Servers (Windows)
echo ===================================================
echo.

:: Check if virtualenv exists
if not exist "%~dp0apps\api\.venv\Scripts\python.exe" (
    echo [WARNING] Backend virtualenv not found.
    echo Running setup first...
    echo.
    call "%~dp0setup.bat"
    if !ERRORLEVEL! NEQ 0 (
        echo [ERROR] Setup failed. Cannot start application.
        pause
        exit /b !ERRORLEVEL!
    )
)

:: Run dev.ps1 with ExecutionPolicy Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Servers stopped with code %ERRORLEVEL%.
    pause
)

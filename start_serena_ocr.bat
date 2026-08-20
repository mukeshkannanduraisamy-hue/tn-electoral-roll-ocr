@echo off
title Serena OCR Local Auto-Deployment
cd /d "%~dp0"
echo Starting Serena OCR Local Servers...
call npm run dev
pause

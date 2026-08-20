@echo off
title TN Electoral Roll OCR - Cloudflare Tunnel
echo ===================================================
echo Starting Cloudflare Tunnel for TN Electoral Roll OCR
echo ===================================================
echo.
echo Make sure your frontend (port 3001) and backend (port 8080) are running!
echo.
"%~dp0cloudflared.exe" tunnel --url http://localhost:3001
pause

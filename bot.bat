@echo off
rem Opens the control console for the bot. Double-click this file.
setlocal
cd /d "%~dp0"
title WhatsApp Sticker Converter - console

where py >nul 2>&1
if %errorlevel%==0 (
    py console.py
) else (
    python console.py
)

echo.
echo Console chiusa. Premi un tasto per uscire.
pause >nul

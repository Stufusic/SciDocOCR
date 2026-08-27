@echo off
title SciDoc OCR Studio - Launcher
cd /d "%~dp0"

echo ========================================================
echo   SciDoc OCR Studio - Scientific Document OCR & AI
echo ========================================================
echo.

python -m app.main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] Phat hien thieu thu vien. Dang mo trinh Launcher Cai dat tu dong...
    python launcher.py
)
pause

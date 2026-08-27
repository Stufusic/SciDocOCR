@echo off
title SciDoc OCR Studio - Environment Installer
cd /d "%~dp0"

echo ========================================================
echo   SciDoc OCR Studio - Automated Dependency Installer
echo ========================================================
echo.

echo [1/3] Kiem tra va cai dat uv (Bo quan ly thu vien sieu toc)...
pip install uv --upgrade

echo.
echo [2/3] Cai dat tat ca thu vien phu thuoc bang uv...
uv pip install -r requirements.txt

echo.
echo [3/3] Kiem tra MinerU CLI...
where magic-pdf >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Neu ban muon dung dong co MinerU cuc bo, chay lenh:
    echo        uv pip install -U "mineru[all]"
) else (
    echo [OK] MinerU da duoc cai dat san tren may.
)

echo.
echo ========================================================
echo   CAI DAT HOAN TAT! Ban co the chay SciDoc OCR ngay.
echo ========================================================
pause

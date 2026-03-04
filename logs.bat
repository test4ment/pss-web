@echo off
chcp 65001 >nul
title Логи — МЧС ПСС
if not exist "logs\app.log" (
    echo Логи пока пусты. Запустите сервис через install.bat
    pause
    exit /b
)
echo ═══ Последние 50 строк лога ═══
powershell -Command "Get-Content logs\app.log -Tail 50"
echo.
echo ═══ Ошибки (если есть) ═══
if exist "logs\error.log" (
    powershell -Command "Get-Content logs\error.log -Tail 20"
)
pause

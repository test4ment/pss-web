@echo off
chcp 65001 >nul
net session >nul 2>&1 || (echo Нужны права администратора & pause & exit /b 1)
echo Перезапускаю сервис...
tools\nssm.exe restart PSS_Analytics
echo Готово. Сайт: http://localhost:8000
timeout /t 2 /nobreak >nul
start http://localhost:8000

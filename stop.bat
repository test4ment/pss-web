@echo off
chcp 65001 >nul
title Управление сервисом ПСС
net session >nul 2>&1 || (echo Нужны права администратора & pause & exit /b 1)
echo Останавливаю сервис...
tools\nssm.exe stop PSS_Analytics
echo Готово.
pause

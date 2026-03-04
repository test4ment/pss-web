@echo off
chcp 65001 >nul
title МЧС ПСС — Режим разработки

echo.
echo  МЧС ПСС — Запуск в режиме разработки (без сервиса)
echo  Остановить: Ctrl+C
echo  Сайт:       http://localhost:8000
echo  API docs:   http://localhost:8000/docs
echo.

if not exist "venv" (
    echo Создаю окружение...
    python -m venv venv
    call venv\Scripts\pip install -r requirements.txt -q
)

if not exist ".env" (
    echo [!] Создайте .env файл из .env.example
    pause
    exit /b
)

start http://localhost:8000
call venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

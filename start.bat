@echo off
chcp 65001 >nul

echo.
echo ╔══════════════════════════════════════╗
echo ║   МЧС ПСС — Аналитическая система    ║
echo ╚══════════════════════════════════════╝
echo.

REM Проверка .env
if not exist ".env" (
    echo  [!] Файл .env не найден.
    echo     Скопируйте .env.example в .env и заполните токены.
    pause
    exit /b 1
)

REM Загрузка .env переменных
if exist .env (
    for /f "tokens=1,2 delims==" %%i in (.env) do set %%i=%%j
    echo  [✓] .env загружен
)

REM Проверка виртуального окружения
if not exist "venv" (
    echo  [*] Создаю виртуальное окружение...
    python -m venv venv
    call venv\Scripts\pip install -r requirements.txt -q
) else (
    echo  [✓] venv найден
    REM Пропускаем повторную установку (быстрее)
    if not exist "venv\Lib\site-packages\fastapi" (
        echo  [*] Устанавливаю зависимости...
        call venv\Scripts\pip install -r requirements.txt -q
    ) else (
        echo  [✓] Зависимости уже установлены
    )
)

REM Запуск сервера ИЗ КОРНЯ проекта
echo.
echo  [✓] Запускаю сервер...
echo  [✓] Откройте: http://localhost:8000 ^(Ctrl+C для остановки^)
echo.
start http://localhost:8000
venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

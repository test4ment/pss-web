@echo off
chcp 65001 >nul
:: Открывает сайт в браузере. Сервис запускается автоматически при входе в Windows.
start http://localhost:8000
exit

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   МЧС ПСС — Аналитическая система   ║
echo  ╚══════════════════════════════════════╝
echo.

if not exist ".env" (
    echo  [!] Файл .env не найден.
    echo      Скопируйте .env.example в .env и заполните токены.
    pause
    exit /b 1
)

if not exist "venv" (
    echo  [*] Создаю виртуальное окружение...
    python -m venv venv
)

echo  [*] Устанавливаю зависимости...
call venv\Scripts\pip install -r requirements.txt -q

echo.
echo  [✓] Запускаю сервер...
echo  [✓] Откройте браузер: http://localhost:8000
echo.

cd backend
..\venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8000 --reload

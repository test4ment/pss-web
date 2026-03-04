@echo off
chcp 65001 >nul
title МЧС ПСС — Установка

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║   МЧС ПСС — Установщик (Windows)              ║
echo  ║   После запуска сайт будет работать как сервис ║
echo  ╚════════════════════════════════════════════════╝
echo.

:: Проверяем права администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  [!] Требуются права администратора.
    echo      Нажмите правой кнопкой на install.bat → "Запуск от имени администратора"
    pause
    exit /b 1
)

set "INSTALL_DIR=%~dp0"
set "VENV_DIR=%INSTALL_DIR%venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "UVICORN_EXE=%VENV_DIR%\Scripts\uvicorn.exe"
set "NSSM_EXE=%INSTALL_DIR%tools\nssm.exe"
set "SERVICE_NAME=PSS_Analytics"
set "APP_PORT=8000"

echo  [1/6] Проверка Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo  [!] Python не найден.
    echo      Скачайте и установите Python 3.11+: https://www.python.org/downloads/
    echo      При установке отметьте "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [✓] Python %PYVER%

echo.
echo  [2/6] Проверка .env...
if not exist "%INSTALL_DIR%.env" (
    if exist "%INSTALL_DIR%.env.example" (
        echo  [!] Файл .env не найден. Создаю из шаблона...
        copy "%INSTALL_DIR%.env.example" "%INSTALL_DIR%.env" >nul
        echo  [!] ВАЖНО: Откройте .env в блокноте и заполните токены!
        echo      Затем запустите install.bat повторно.
        notepad "%INSTALL_DIR%.env"
        pause
        exit /b 1
    ) else (
        echo  [!] Файл .env не найден!
        pause
        exit /b 1
    )
)
echo  [✓] .env найден

echo.
echo  [3/6] Создание виртуального окружения...
if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%"
    echo  [✓] Окружение создано
) else (
    echo  [✓] Окружение уже существует
)

echo.
echo  [4/6] Установка зависимостей...
call "%VENV_DIR%\Scripts\pip" install -r "%INSTALL_DIR%requirements.txt" -q --no-warn-script-location
if %errorLevel% neq 0 (
    echo  [!] Ошибка установки зависимостей
    pause
    exit /b 1
)
echo  [✓] Зависимости установлены

echo.
echo  [5/6] Установка NSSM (менеджер сервисов)...
if not exist "%INSTALL_DIR%tools" mkdir "%INSTALL_DIR%tools"
if not exist "%NSSM_EXE%" (
    echo  Скачиваю NSSM...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%INSTALL_DIR%tools\nssm.zip'}" 2>nul
    if exist "%INSTALL_DIR%tools\nssm.zip" (
        powershell -Command "Expand-Archive -Path '%INSTALL_DIR%tools\nssm.zip' -DestinationPath '%INSTALL_DIR%tools\nssm_tmp' -Force" 2>nul
        :: Ищем nssm.exe в распакованной папке (64-bit)
        for /r "%INSTALL_DIR%tools\nssm_tmp" %%f in (nssm.exe) do (
            if "%%~pf" == "win64\" copy "%%f" "%NSSM_EXE%" >nul 2>&1
        )
        :: Если не нашли win64 — берём любой
        if not exist "%NSSM_EXE%" (
            for /r "%INSTALL_DIR%tools\nssm_tmp" %%f in (nssm.exe) do copy "%%f" "%NSSM_EXE%" >nul 2>&1
        )
        rd /s /q "%INSTALL_DIR%tools\nssm_tmp" 2>nul
        del "%INSTALL_DIR%tools\nssm.zip" 2>nul
    )
)

if not exist "%NSSM_EXE%" (
    echo  [!] NSSM не удалось скачать автоматически.
    echo      Скачайте вручную: https://nssm.cc/download
    echo      Поместите nssm.exe в папку: %INSTALL_DIR%tools\
    echo.
    echo  Продолжаю без сервиса — будет создан только ярлык запуска.
    goto :create_shortcut
)
echo  [✓] NSSM готов

echo.
echo  [6/6] Регистрация Windows-сервиса...

:: Останавливаем и удаляем старый сервис если был
"%NSSM_EXE%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM_EXE%" remove %SERVICE_NAME% confirm >nul 2>&1

:: Регистрируем новый
"%NSSM_EXE%" install %SERVICE_NAME% "%UVICORN_EXE%"
"%NSSM_EXE%" set %SERVICE_NAME% AppParameters "backend.main:app --host 0.0.0.0 --port %APP_PORT%"
"%NSSM_EXE%" set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
"%NSSM_EXE%" set %SERVICE_NAME% DisplayName "МЧС ПСС Аналитика"
"%NSSM_EXE%" set %SERVICE_NAME% Description "Веб-платформа аналитики выездов ПСС"
"%NSSM_EXE%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_EXE%" set %SERVICE_NAME% AppStdout "%INSTALL_DIR%logs\app.log"
"%NSSM_EXE%" set %SERVICE_NAME% AppStderr "%INSTALL_DIR%logs\error.log"
"%NSSM_EXE%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_EXE%" set %SERVICE_NAME% AppRotateSeconds 86400

if not exist "%INSTALL_DIR%logs" mkdir "%INSTALL_DIR%logs"

:: Запускаем сервис
"%NSSM_EXE%" start %SERVICE_NAME%
timeout /t 3 /nobreak >nul

:: Проверяем что запустился
"%NSSM_EXE%" status %SERVICE_NAME% | findstr "SERVICE_RUNNING" >nul
if %errorLevel% equ 0 (
    echo  [✓] Сервис запущен и работает
    echo  [✓] Автозапуск при включении компьютера: ДА
) else (
    echo  [!] Сервис установлен, но не запустился. Проверьте логи: %INSTALL_DIR%logs\error.log
)

:create_shortcut
:: Создаём ярлык на рабочем столе
powershell -Command "& {$ws=New-Object -ComObject WScript.Shell; $sc=$ws.CreateShortcut([System.Environment]::GetFolderPath('Desktop')+'\МЧС ПСС.url'); $sc.TargetPath='http://localhost:%APP_PORT%'; $sc.Save()}" 2>nul

:: Открываем firewall для порта
netsh advfirewall firewall delete rule name="PSS Analytics" >nul 2>&1
netsh advfirewall firewall add rule name="PSS Analytics" dir=in action=allow protocol=TCP localport=%APP_PORT% >nul 2>&1

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║   УСТАНОВКА ЗАВЕРШЕНА                          ║
echo  ╠════════════════════════════════════════════════╣
echo  ║   Сайт:     http://localhost:%APP_PORT%               ║
echo  ║   В сети:   http://[IP-адрес-ПК]:%APP_PORT%          ║
echo  ║   Ярлык:    На рабочем столе "МЧС ПСС"        ║
echo  ║   Логи:     logs\app.log                       ║
echo  ╚════════════════════════════════════════════════╝
echo.
echo  Управление сервисом:
echo    start.bat    — открыть сайт
echo    stop.bat     — остановить сервис
echo    restart.bat  — перезапустить
echo    logs.bat     — просмотр логов
echo.

:: Открываем браузер
timeout /t 2 /nobreak >nul
start http://localhost:%APP_PORT%

pause

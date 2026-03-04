# Деплой на Windows — пошаговая инструкция

## Что получится в итоге

```
Windows PC / Сервер
    ├─ Сайт работает как служба Windows (как антивирус)
    ├─ Запускается автоматически при включении ПК
    ├─ Доступен по http://localhost:8000 локально
    └─ Доступен по http://[IP-ПК]:8000 из локальной сети
```

---

## Шаг 1 — Установить Python

Скачать: https://www.python.org/downloads/ (Python 3.11 или 3.12)

**ВАЖНО** при установке:
- ✅ Отметить "Add Python to PATH"
- ✅ Отметить "Install for all users" (если деплой на сервер)

Проверить:
```
Win+R → cmd → python --version
```
Должно показать `Python 3.11.x`

---

## Шаг 2 — Установить PostgreSQL

Скачать: https://www.postgresql.org/download/windows/

При установке:
- Запомнить пароль пользователя `postgres`
- Порт оставить `5432`

После установки создать базу данных:
```
Win+R → psql -U postgres
```
```sql
CREATE DATABASE pss_db;
\q
```

Или через pgAdmin (ставится вместе с PostgreSQL):
Правая кнопка на "Databases" → Create → Database → имя `pss_db`

---

## Шаг 3 — Настроить .env

Открыть файл `.env.example`, сохранить как `.env`, заполнить:

```ini
# Пока нет токенов GigaChat — используем Anthropic для теста:
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-ВАШ_КЛЮЧ

# Или когда получите GigaChat:
# AI_PROVIDER=gigachat
# GIGACHAT_CREDENTIALS=BASE64_CREDENTIALS

PG_HOST=localhost
PG_PORT=5432
PG_DB=pss_db
PG_USER=postgres
PG_PASSWORD=пароль_который_вы_задали_при_установке_postgresql
```

---

## Шаг 4 — Установить как службу Windows

```
Правая кнопка на install.bat → Запуск от имени администратора
```

Скрипт сам:
- Создаст виртуальное окружение Python
- Установит все зависимости
- Скачает NSSM (менеджер служб)
- Зарегистрирует службу "МЧС ПСС Аналитика"
- Настроит автозапуск
- Добавит ярлык на рабочий стол
- Откроет сайт в браузере

---

## Управление после установки

| Файл          | Действие                          |
|---------------|-----------------------------------|
| `start.bat`   | Открыть сайт в браузере           |
| `dev.bat`     | Режим разработки (с hot-reload)   |
| `stop.bat`    | Остановить сервис (от админа)     |
| `restart.bat` | Перезапустить (от админа)         |
| `logs.bat`    | Посмотреть логи                   |

Или через стандартный диспетчер служб Windows:
```
Win+R → services.msc → найти "МЧС ПСС Аналитика"
```

---

## Если нужен доступ по домену / из интернета

### Вариант 1 — Nginx (рекомендуется)

Скачать: https://nginx.org/en/download.html

Конфиг `nginx.conf`:
```nginx
server {
    listen 80;
    server_name ваш-домен.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Запустить nginx как службу через NSSM (аналогично основному приложению).

### Вариант 2 — Только локальная сеть

Узнать IP-адрес компьютера:
```
Win+R → cmd → ipconfig
```
Найти строку "IPv4-адрес", например `192.168.1.100`

Сайт будет доступен: `http://192.168.1.100:8000`

---

## Обновление приложения

```
1. Остановить: stop.bat (от админа)
2. Заменить файлы в папке backend/ и frontend/
3. Запустить: restart.bat (от админа)
```

---

## Диагностика проблем

**Сайт не открывается:**
```
logs.bat → посмотреть ошибки
```

**PostgreSQL не подключается:**
```
Win+R → services.msc → проверить что служба "postgresql-x64-XX" запущена
```

**Порт занят другой программой:**
```
cmd → netstat -ano | findstr :8000
```
Изменить порт в install.bat: `set "APP_PORT=8001"` и переустановить.

**Полная переустановка:**
```
1. stop.bat (от админа)
2. Win+R → services.msc → удалить "МЧС ПСС Аналитика"
3. Удалить папку venv/
4. install.bat (от админа)
```

# МЧС ПСС — Веб-платформа аналитики

Веб-сайт для анализа журналов выездов Поисково-спасательной службы.

## Стек

| Слой       | Технология                          |
|------------|-------------------------------------|
| Фронтенд   | HTML/CSS/JS (без фреймворков)        |
| Бэкенд     | Python + FastAPI                    |
| ИИ         | GigaChat (Сбер) / Claude (запасной) |
| База данных | PostgreSQL                          |
| Парсинг    | openpyxl + Этап 1 встроен в бэкенд  |

## Структура

```
pss_web/
├── backend/
│   └── main.py          ← FastAPI: API + парсер + ИИ-чат
├── frontend/
│   └── index.html       ← весь фронтенд в одном файле
├── requirements.txt
├── .env.example         ← скопируйте в .env
└── start.bat            ← запуск одной командой (Windows)
```

## Быстрый старт (Windows)

### 1. Установить PostgreSQL
Скачать: https://www.postgresql.org/download/windows/
При установке запомните пароль пользователя `postgres`.

После установки создать базу данных:
```sql
CREATE DATABASE pss_db;
```

### 2. Получить токены GigaChat
1. Зайти на https://developers.sber.ru/studio
2. Создать проект → подключить GigaChat API
3. Получить Client ID и Client Secret
4. Закодировать в Base64: `ClientID:ClientSecret`
   - Онлайн: https://www.base64encode.org/
   - PowerShell: `[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("ID:Secret"))`

Пока нет токенов GigaChat — использовать Claude:
```
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Настроить .env
```
copy .env.example .env
# Открыть .env в блокноте и заполнить токены
```

### 4. Запустить
```
start.bat
```
Открыть браузер: **http://localhost:8000**

---

## Переключение ИИ-провайдера

В файле `.env`:
```
# GigaChat (когда дадут токены):
AI_PROVIDER=gigachat
GIGACHAT_CREDENTIALS=...

# Claude (для тестирования):
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```
Перезапустить сервер — больше ничего менять не нужно.

---

## API эндпоинты

| Метод  | Путь                    | Описание                        |
|--------|-------------------------|---------------------------------|
| POST   | /api/upload             | Загрузить Excel-журнал выездов  |
| GET    | /api/stats              | Общая статистика                |
| GET    | /api/departures         | Список выездов (с фильтрами)    |
| GET    | /api/search?q=...       | Поиск по описаниям              |
| POST   | /api/chat               | Чат с ИИ-аналитиком             |
| DELETE | /api/chat/{session_id}  | Очистить историю чата           |
| GET    | /api/chart/types        | График: типы происшествий       |
| GET    | /api/chart/districts    | График: по районам              |
| GET    | /api/chart/timeline     | График: динамика по датам       |

Документация Swagger: http://localhost:8000/docs

---

## Для команды

- **Этап 2** — подключайтесь к той же PostgreSQL: таблицы `pss_departures`, `pss_lessons`
- **Этап 3** — поле `description_raw` в каждой записи = полный оригинальный текст для RAG
- **Этап 4** — поля `district`, `incident_type`, `victims`, `duration_travel_min` для графиков

## Деплой на сервер (Ubuntu)

```bash
# Зависимости
sudo apt install python3-pip postgresql

# Клонировать / скопировать проект
cd /opt/pss_web

# Установить
pip3 install -r requirements.txt

# Запустить через systemd или просто:
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

# Для домена — настроить nginx как reverse proxy на порт 8000
```

# Деплой No Skip Club Bot на Bothost.ru

Бот работает через **long polling** (как на ПК) — webhook настраивать не нужно.

## Важно перед стартом

1. **Останови локального бота** (закрой терминал с `python bot.py`).  
   Один `BOT_TOKEN` = один запущенный процесс. Два polling конфликтуют.
2. Токены и ключи **не клади в zip** — только в Env-панель Bothost.
3. На платном тарифе включи **постоянный диск (Volume)**, иначе SQLite может обнулиться при редеплое.

---

## Шаг 1. Архив для загрузки

На рабочем столе уже есть готовый zip (см. `no_skip_club_bot_bothost.zip`),  
или собери сам **из папки `no_skip_club_bot` (внутренняя, где лежит `bot.py`)**:

В zip должны быть:
- `bot.py`, `config.py`, `database.py`, `content.py`, `keyboards.py`, `scheduler.py`, `video_catalog.py`
- `handlers/`, `data/`, `requirements.txt`
- по желанию `no_skip.db` (чтобы перенести текущих пользователей)
- `Dockerfile` (если Bothost просит Docker)

**Не клади:** `venv/`, `__pycache__/`, `.env`

---

## Шаг 2. Создай проект на Bothost

1. Зайди на https://bothost.ru → панель
2. **Новый проект / New bot**
3. Тип: **Telegram** / **Python**
4. Загрузка: **ZIP** (или GitHub, если репозиторий уже есть)
5. Entry / start command: `python bot.py`  
   (если есть Dockerfile — Bothost соберёт сам, CMD уже прописан)
6. Python: **3.11 или 3.12**
7. Requirements: `requirements.txt`

---

## Шаг 3. Переменные окружения (Env)

Скопируй **те же значения**, что в локальном `.env`:

| Переменная | Пример / заметка |
|---|---|
| `BOT_TOKEN` | токен от @BotFather |
| `ADMIN_CHAT_ID` | твой numeric id |
| `TZ` | `Asia/Almaty` (или `Europe/Moscow`) |
| `REMINDER_HOUR` | `8` |
| `CHARACTER_ENABLED` | `false` |
| `PENALTY_AMOUNT_RUB` | `500` |
| `PENALTY_AMOUNT_KZT` | `3000` |
| `COACH_USERNAME` | `jimon_000` |
| `MISTRAL_API_KEY` | ключ Mistral |
| `MISTRAL_MODEL` | `mistral-small-latest` |
| `MISTRAL_VISION_MODEL` | `pixtral-12b-2409` |
| `DB_PATH` | `/app/data/no_skip.db` (Bothost volume; **не** клади JSON-каталоги в `/app/data`) |

`WEBAPP_URL` можно не задавать — персонаж выключен.

---

## Шаг 4. Volume (база данных)

Если в панели есть **Volume / Persistent storage**:
1. Монтируй путь `/data`
2. Поставь `DB_PATH=/data/no_skip.db`
3. Если заливал `no_skip.db` в zip — после первого запуска можно один раз скопировать:
   - либо положи файл сразу как `/data/no_skip.db` через файловый менеджер Bothost,
   - либо первый деплой без Volume с `no_skip.db` в корне, потом перенеси файл на Volume.

Без Volume пользователи и стрики **могут пропасть** после рестарта.

---

## Шаг 5. Запуск

1. Deploy / Start
2. Открой **Logs** — должно быть:
   - `База данных готова`
   - `Бот запущен (polling)`
3. В Telegram: `/start` у своего бота

---

## Если что-то не так

| Симптом | Что проверить |
|---|---|
| Бот молчит | Логи; `BOT_TOKEN`; не запущен ли ещё локальный `bot.py` |
| Conflict / getUpdates | Два инстанса с одним токеном — останови ПК или второй деплой |
| Напоминания не в 8:00 | `TZ=Asia/Almaty` (или свой город) |
| Пропали пользователи | Volume + `DB_PATH` |
| ИИ/фото не работают | `MISTRAL_API_KEY` в Env |
| Admin-команды не видны | `ADMIN_CHAT_ID` — числовой id, не username |
| После рестарта всё ок, потом снова «Материалы» / мало видео | Крутится **старая сборка** или на Volume старый JSON. **Перезалей свежий ZIP** (или Redeploy с GitHub `main`). В логах: `build=2026-07-19-videos-v2`, каталог **~277**. Кнопки «Материалы» быть не должно. Старые `sportkuznica_exercises.json` / `training_plans.json` на `/data` можно удалить (базу `no_skip.db` не трогай). |

### Как проверить новую версию

1. Restart → **Logs**
2. Строка: `=== No Skip Club bot start build=2026-07-19-videos-v2 ===`
3. Строка: `Каталог видео: 277` (или около)
4. В Telegram `/menu` — есть «🎬 Видео упражнений», **нет** «Материалы (фото/видео)»

Поддержка Bothost: https://t.me/bothostru · support@bothost.ru

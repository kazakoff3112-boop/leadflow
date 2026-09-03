# LeadFlow

LeadFlow — небольшой full-stack сервис для приёма заявок с сайта. Он сохраняет
заявки в локальную базу данных и автоматически отправляет информацию
администратору в Telegram и Google Sheets.

Проект создан как законченная демонстрационная работа для портфолио.

## Возможности

- адаптивная форма заявки;
- backend на FastAPI;
- хранение заявок в SQLite;
- уведомления через Telegram Bot API;
- добавление строк через Google Sheets API;
- защита от одинаковых заявок в течение пяти минут;
- проверка имени, телефона, email и сообщения;
- сохранение заявки при сбое Telegram или Google Sheets;
- health-check приложения и базы данных;
- автоматические тесты.

## Как работает

```text
Браузер
   ↓
FastAPI
   ↓
SQLite
   ├── Telegram
   └── Google Sheets
```

Браузер отправляет заполненную форму в FastAPI. Backend проверяет данные и
ищет недавний дубликат. Новая заявка сначала сохраняется в SQLite, а затем
backend независимо пытается отправить уведомление в Telegram и добавить строку
в Google Sheets. Если внешний сервис временно недоступен, сохранённая заявка не
теряется.

## Стек

- HTML;
- CSS;
- JavaScript;
- Python;
- FastAPI;
- Pydantic;
- SQLite;
- Telegram Bot API;
- Google Sheets API;
- pytest.

## Структура проекта

```text
LeadFlow/
├── backend/
│   ├── __init__.py
│   └── main.py
├── tests/
│   └── test_main.py
├── .env.example
├── .gitignore
├── index.html
├── requirements.txt
├── script.js
└── styles.css
```

Файл базы данных, `.env`, виртуальное окружение и Google credentials создаются
только локально и не публикуются.

## Установка

Нужен установленный Python 3.9 или новее.

1. Клонируйте будущий репозиторий и перейдите в папку проекта:

   ```bash
   git clone ВАШ_URL_РЕПОЗИТОРИЯ
   cd LeadFlow
   ```

2. Создайте виртуальное окружение:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   В Windows команда активации выглядит так:

   ```powershell
   .venv\Scripts\activate
   ```

3. Установите зависимости:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Создайте локальный `.env` из примера:

   ```bash
   cp .env.example .env
   ```

   В Windows можно выполнить:

   ```powershell
   Copy-Item .env.example .env
   ```

5. Создайте Telegram-бота через BotFather, получите идентификатор нужного чата
   и заполните Telegram-переменные в `.env`.

6. В Google Cloud включите Google Sheets API и создайте service account.
   Скачанный JSON-ключ сохраните в корне проекта под именем
   `google-service-account.json`. Предоставьте email service account права
   редактора нужной Google-таблицы, затем заполните Google-переменные в `.env`.

7. Запустите FastAPI из корня проекта:

   ```bash
   uvicorn backend.main:app --reload
   ```

8. Откройте в браузере [http://127.0.0.1:8000](http://127.0.0.1:8000).
   Frontend раздаётся самим FastAPI, поэтому открывать `index.html` напрямую не
   требуется.

## Переменные окружения

В локальном `.env` используются:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GOOGLE_SHEETS_CREDENTIALS_FILE
GOOGLE_SHEETS_SPREADSHEET_ID
GOOGLE_SHEETS_SHEET_NAME
```

Назначение и безопасные примеры значений находятся в `.env.example`. Настоящие
токены и credentials нельзя добавлять в Git или README.

## Тестирование

Тесты используют временную SQLite-базу и подменяют Telegram и Google Sheets,
поэтому реальные сообщения и строки не создаются.

Запуск из корня проекта:

```bash
python -m pytest -v
```

## API

### `POST /api/leads`

Принимает заявку с полями `name`, `phone`, `email` и `message`. Возвращает
результат приёма и признак дубликата. Некорректные данные получают HTTP 422.

### `GET /health`

Проверяет доступность приложения и SQLite. Возвращает HTTP 200 при рабочей базе
или безопасный HTTP 503 при ошибке.

Публичный `GET /api/leads` намеренно отсутствует, чтобы персональные данные
клиентов нельзя было получить без административной авторизации.

## Надёжность и безопасность

- секреты загружаются из переменных окружения;
- `.env`, Google credentials и SQLite исключены из Git;
- входные данные проверяются до сохранения;
- повтор одинаковой заявки блокируется в течение пяти минут;
- SQLite остаётся основной точкой сохранения;
- ошибки Telegram и Google Sheets не удаляют принятую заявку;
- публичного endpoint со списком клиентов нет;
- логи внешних сервисов не содержат токены и credentials.

## Статус проекта

LeadFlow — законченный демонстрационный full-stack проект для портфолио. Он
готов к локальному запуску и дальнейшей безопасной публикации после проверки
Git-состояния и выбора лицензии.

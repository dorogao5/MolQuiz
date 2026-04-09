# MolQuiz

Telegram-бот для тренировки органической номенклатуры.

Бот присылает PNG со структурой, пользователь пишет название в чат, бот проверяет ответ. Есть два режима: `IUPAC` и `Рациональная`.

## Что уже есть

- Telegram UX на `aiogram 3`
- webhook-режим на `FastAPI`
- `PostgreSQL` для данных
- `Redis` для сессий
- `RDKit` для генерации картинок и дескрипторов
- `OPSIN` sidecar для проверки английских IUPAC-названий
- импорт карточек, review-пайплайн и публикация только после проверки
- Docker Compose для локального и серверного запуска

## Стек

- Python 3.12
- `uv`
- `aiogram`
- `FastAPI`
- `SQLAlchemy 2`
- `Alembic`
- `PostgreSQL`
- `Redis`
- `RDKit`
- `OPSIN`

## Быстрый старт локально

1. Установить зависимости:

```bash
uv sync --extra dev
```

2. Поднять инфраструктуру:

```bash
docker compose up -d postgres redis opsin
```

3. Применить миграции:

```bash
uv run alembic upgrade head
```

4. Загрузить демо-данные:

```bash
uv run molquiz-seed-demo --path data/demo_cards.yaml
uv run molquiz-seed-rational --path data/rational_curated.yaml
```

5. Запустить бота в polling-режиме:

```bash
MOLQUIZ_REDIS_URL=memory:// uv run molquiz-dev
```

## Запуск через Docker

```bash
docker compose up --build -d postgres redis opsin bot worker
docker compose exec bot uv run alembic upgrade head
docker compose exec bot uv run molquiz-seed-demo --path data/demo_cards.yaml
docker compose exec bot uv run molquiz-seed-rational --path data/rational_curated.yaml
```

Для production с HTTPS:

```bash
MOLQUIZ_DOMAIN=your.domain.tld docker compose --profile prod up --build -d
```

## Переменные окружения

Скопировать `.env.example` в `.env` и заполнить минимум:

- `MOLQUIZ_TELEGRAM_TOKEN`
- `MOLQUIZ_TELEGRAM_WEBHOOK_SECRET`
- `MOLQUIZ_TELEGRAM_WEBHOOK_BASE_URL`
- `MOLQUIZ_DATABASE_URL`
- `MOLQUIZ_REDIS_URL`
- `MOLQUIZ_OPSIN_BASE_URL`

## Полезные команды

Запуск webhook-приложения:

```bash
uv run molquiz-web
```

Фоновой воркер:

```bash
uv run molquiz-worker
```

Импорт из PubChem по списку CID:

```bash
uv run molquiz-import-pubchem data/pubchem_seed_cids.txt
```

Генерация картинок:

```bash
uv run molquiz-generate-depictions
```

Экспорт задач на review:

```bash
uv run molquiz-review-export --output data/review_exports/pending.yaml
```

Применение review-решений:

```bash
uv run molquiz-review-apply data/review_decisions.example.yaml
```

Пересчёт publish-state:

```bash
uv run molquiz-publish-ready
```

## Проверки

```bash
uv run ruff check src tests alembic
uv run pytest
```

## Health endpoints

- `/health/live`
- `/health/ready`
- `/metrics`

## Статус

Это уже рабочий MVP. Дальше по-хорошему наращивать базу карточек, улучшать модерацию и добавлять нагрузочные тесты.

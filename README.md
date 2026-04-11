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
- production seed с `2200` IUPAC-карточками и `75` rational-карточками
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

По умолчанию сервисы публикуются только на `localhost` и на портах `15432`, `16379` и `18080`, чтобы не конфликтовать с уже установленными на машине `PostgreSQL`/`Redis`.
Если и эти порты заняты, переопредели `MOLQUIZ_POSTGRES_HOST_PORT`, `MOLQUIZ_REDIS_HOST_PORT` и `MOLQUIZ_OPSIN_HOST_PORT` в `.env` перед запуском.

3. Применить миграции:

```bash
uv run alembic upgrade head
```

4. Загрузить полный банк карточек:

```bash
uv run molquiz-seed-full
```

5. Запустить бота в polling-режиме:

```bash
MOLQUIZ_REDIS_URL=memory:// uv run molquiz-dev
```

## Запуск через Docker

Обычный запуск, без webhook и без `443`:

```bash
docker compose up --build -d postgres redis opsin bot worker
docker compose exec bot uv run alembic upgrade head
docker compose exec bot uv run molquiz-seed-full
```

В этом режиме бот работает через polling. Никакие `MOLQUIZ_TELEGRAM_WEBHOOK_SECRET` и `MOLQUIZ_TELEGRAM_WEBHOOK_BASE_URL` не нужны.
`postgres`, `redis` и `opsin` внутри compose по-прежнему доступны как сервисы `postgres:5432`, `redis:6379` и `opsin:8080`, а на хост публикуются только на `localhost` и нестандартных портах из `.env.example`.

Если зачем-то нужен именно webhook, тогда уже отдельный production-профиль:

```bash
MOLQUIZ_DOMAIN=your.domain.tld docker compose --profile prod up --build -d
```

## Переменные окружения

Скопировать `.env.example` в `.env` и заполнить минимум:

- `MOLQUIZ_TELEGRAM_TOKEN`
- `MOLQUIZ_DATABASE_URL`
- `MOLQUIZ_REDIS_URL`
- `MOLQUIZ_OPSIN_BASE_URL`

Webhook-переменные нужны только для режима `prod` с `molquiz-web`.

Если хочешь использовать Qwen для офлайн-подсказок на review, можно добавить:

- `MOLQUIZ_QWEN_COMMAND=qwen`

Это не API и не отдельный endpoint. Воркер просто вызывает локальную команду `qwen -p ...`. Соответственно, `qwen` должен быть установлен и уже авторизован на этой машине.

## Полезные команды

Запуск polling-бота:

```bash
uv run molquiz-dev
```

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

Пересобрать production IUPAC seed из официальных PubChem bulk-файлов:

```bash
uv run molquiz-build-iupac-seed
```

Загрузить весь контент:

```bash
uv run molquiz-seed-full
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

## CI/CD

В репозитории есть GitHub Actions для `CI` и `CD`.

- `CI`: линтер, тесты, `docker compose config`, сборка Docker-образов
- `CD`: selective build/push в `GHCR` и selective deploy на сервер по `SSH`

Подробная схема и список нужных secrets: [docs/cicd.md](docs/cicd.md)

## Health endpoints

- `/health/live`
- `/health/ready`
- `/metrics`

## Статус

В репозитории уже лежит полный стартовый банк для v1:

- `data/iupac_curated.yaml` на `2200` карточек
- `data/rational_curated.yaml` на `75` карточек

Дальше имеет смысл улучшать модерацию, добавлять QA для контента и нагрузочные тесты.

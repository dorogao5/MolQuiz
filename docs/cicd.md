# CI/CD for MolQuiz

Этот репозиторий настроен под image-based deploy через GitHub Actions и `GHCR`.

## Что делает пайплайн

- `CI` запускается на каждый `pull_request` и на каждый `push`, кроме `main`.
- `CD` запускается на `push` в `main`.
- На `CI` выполняются:
  - `uv sync --extra dev --frozen`
  - `uv run ruff check src tests alembic`
  - `uv run pytest`
  - `docker compose config`
  - сборка Docker-образов приложения и `OPSIN`
- На `CD` выполняются:
  - те же проверки качества
  - определение, какие части реально изменились
  - публикация только нужных образов в `ghcr.io`
  - деплой на сервер по `SSH`
  - запуск миграций только при изменениях в app image
  - перезапуск только нужных контейнеров

## Что считается изменением сервисов

- `app image`:
  - `Dockerfile`
  - `.dockerignore`
  - `.python-version`
  - `pyproject.toml`
  - `uv.lock`
  - `alembic.ini`
  - `alembic/**`
  - `src/**`
  - `data/**`
- `OPSIN image`:
  - `docker/opsin/**`
- `runtime redeploy` без пересборки image:
  - `docker-compose.yml`

## Почему данные не теряются

- `postgres`, `redis` и storage используют named volumes.
- Имена volumes зафиксированы явно:
  - `molquiz_postgres_data`
  - `molquiz_redis_data`
  - `molquiz_storage_data`
- Во время деплоя не используется `docker compose down -v`.
- Деплой работает через `pull` и `up -d`, а не через удаление volumes.
- `postgres` и `redis` вообще не пересобираются.

## Что нужно сделать один раз на сервере

1. Держать production checkout в `/srv/MolQuiz`.
2. Убедиться, что там есть актуальный `.env`.
3. Убедиться, что пользователь деплоя имеет доступ к `docker compose`.
4. Не хранить никаких локальных изменений в серверном checkout.
   `deploy.sh` специально падает, если рабочее дерево грязное.
5. Не коммитить `.env.deploy`.
   Этот файл создаётся автоматически на сервере и хранит refs последних задеплоенных образов.

## GitHub secrets

Нужно добавить следующие secrets в репозиторий:

- `DEPLOY_SSH_HOST`
- `DEPLOY_SSH_PORT`
- `DEPLOY_SSH_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_SSH_KNOWN_HOSTS`
- `GHCR_USERNAME`
- `GHCR_TOKEN`

Для `GHCR_TOKEN` достаточно отдельного токена с правом `read:packages`.
Если образы в `GHCR` будут публичными, логин можно не использовать, но текущая схема готова к приватным образам.

## Рекомендуемая настройка GitHub

- Создать environment `production`.
- Повесить на него required reviewers, если хочешь ручное подтверждение перед деплоем.
- Ограничить деплой только на `main`.

## Как проходит deploy

1. GitHub Actions определяет, изменились ли app image и/или `OPSIN`.
2. Для изменившихся образов выполняется `docker buildx build --push`.
3. На сервер по `SSH` уходит маленький env-файл с флагами деплоя.
4. `scripts/deploy.sh` на сервере делает:
   - `git fetch` и `git pull --ff-only`
   - загружает `.env.deploy`, если он уже есть
   - `docker login ghcr.io` при наличии credentials
   - `docker compose up -d postgres redis`
   - `docker compose up -d --no-build opsin`
   - `docker compose pull ...` только для нужных сервисов
   - `docker compose run --rm --no-deps migrate` только при изменениях app image
   - `docker compose up -d --no-deps --no-build ...` только для нужных контейнеров
   - обновляет `.env.deploy` новыми image refs

## Что не делается автоматически
- `molquiz-seed-full`
- любые одноразовые data-fix команды
- backup базы перед каждым deploy
Это специально. Seed и ad hoc data migration не должны запускаться на каждый merge в `main`.
## Правило для миграций

Миграции должны быть совместимыми с rolling restart на одном хосте:

- сначала additive changes
- потом код, использующий новые поля
- destructive cleanup только отдельным шагом позже

Для этого проекта polling-бот все равно будет иметь короткое окно перезапуска, но база не должна требовать ручного аварийного восстановления.
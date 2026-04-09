# MolQuiz

MolQuiz is a Telegram bot for training organic nomenclature on skeletal structure images.

The bot sends a PNG with a molecular structure, the user replies with a name in chat, and the backend validates the answer against reviewed aliases or, for English IUPAC names, via OPSIN structure parsing. The project is designed for a content-review workflow: automatic ingest and depiction generation first, human review of naming variants second, publication only after the required aliases are approved.

## Current Scope

- Telegram UX with buttons and session-based practice flow
- Two practice modes: `iupac` and `rational`
- Russian bot UI
- Acceptance of both Russian and English answers for published cards
- RDKit-based depiction generation and descriptor extraction
- OPSIN sidecar for English IUPAC name-to-structure validation
- PostgreSQL data model for molecules, cards, attempts, stats, and review tasks
- Redis-backed active practice sessions
- Review export/apply CLI flow for publishing imported content
- Docker-first local and production deployment path

## Tech Stack

- Python 3.12
- `uv` for dependency management and execution
- `aiogram` 3 for Telegram bot handling
- FastAPI for webhook mode
- SQLAlchemy 2 + Alembic
- PostgreSQL
- Redis
- RDKit
- OPSIN sidecar
- Docker Compose

## Repository Layout

```text
src/molquiz/
  bot/            Telegram handlers and keyboards
  cli/            Import, seeding, review, and publication commands
  db/             SQLAlchemy models and session helpers
  services/       Content, checking, depictions, OPSIN, practice logic
  main.py         FastAPI webhook app
  dev_polling.py  Local long-polling runner
  worker.py       Offline review/depiction worker

data/
  demo_cards.yaml
  rational_curated.yaml
  review_decisions.example.yaml

docker/
  opsin/          OPSIN sidecar container
  caddy/          Optional reverse proxy config

alembic/
  versions/       Database migrations
```

## Main Data Model

- `molecules`: canonical structure, formula, descriptors, provenance, publish state
- `depiction_variants`: generated PNG variants and cached Telegram `file_id`
- `naming_variants`: accepted aliases by mode and locale
- `cards`: practice units with mode, difficulty, hints, topic tags, publication flag
- `attempts`: raw user answers, normalized answers, verdict, error category, latency
- `user_stats`: aggregate counters and streaks
- `review_tasks`: offline moderation queue for generated RU aliases and depiction jobs

## Environment Variables

Copy `.env.example` to `.env` and set the required values.

Important variables:

- `MOLQUIZ_TELEGRAM_TOKEN`: Telegram bot token
- `MOLQUIZ_TELEGRAM_WEBHOOK_SECRET`: webhook path secret
- `MOLQUIZ_TELEGRAM_WEBHOOK_BASE_URL`: public HTTPS base URL for webhook mode
- `MOLQUIZ_DATABASE_URL`: SQLAlchemy async database URL
- `MOLQUIZ_REDIS_URL`: Redis URL, or `memory://` for simple local runs
- `MOLQUIZ_OPSIN_BASE_URL`: OPSIN sidecar base URL
- `MOLQUIZ_STORAGE_DIR`: local storage for depictions and runtime artifacts
- `MOLQUIZ_QWEN_BASE_URL`: optional Qwen headless endpoint
- `MOLQUIZ_QWEN_OAUTH_TOKEN`: optional OAuth token for Qwen headless mode

## Local Development

### 1. Install dependencies

```bash
uv sync --extra dev
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis opsin
```

### 3. Apply migrations

```bash
uv run alembic upgrade head
```

### 4. Seed demo content

```bash
uv run molquiz-seed-demo --path data/demo_cards.yaml
uv run molquiz-seed-rational --path data/rational_curated.yaml
```

### 5. Run in development polling mode

```bash
MOLQUIZ_REDIS_URL=memory:// uv run molquiz-dev
```

This is the easiest way to test the bot locally without public webhook exposure.

## Webhook Mode

The webhook app runs through FastAPI:

```bash
uv run molquiz-web
```

Available operational endpoints:

- `/health/live`
- `/health/ready`
- `/metrics`
- `/telegram/webhook/<secret>`

## Content Workflow

### Seed curated demo and rational cards

```bash
uv run molquiz-seed-demo --path data/demo_cards.yaml
uv run molquiz-seed-rational --path data/rational_curated.yaml
```

### Import PubChem content by CID list

```bash
uv run molquiz-import-pubchem data/pubchem_seed_cids.txt
```

The import path:

1. saves the structure and descriptors
2. stores English IUPAC as approved
3. generates a rule-based Russian candidate as pending
4. creates review tasks
5. leaves the card unpublished until review is approved

### Generate depictions

```bash
uv run molquiz-generate-depictions
```

### Export pending review tasks

```bash
uv run molquiz-review-export --output data/review_exports/pending.yaml
```

### Apply review decisions

Use `data/review_decisions.example.yaml` as a template, then:

```bash
uv run molquiz-review-apply data/review_decisions.example.yaml
```

### Recalculate publication flags

```bash
uv run molquiz-publish-ready
```

Published cards require:

- at least one active depiction
- approved `ru` naming variant
- approved `en` naming variant

## Worker

Run the offline worker to process review-side jobs:

```bash
uv run molquiz-worker
```

The worker currently handles:

- depiction generation tasks
- RU IUPAC enrichment tasks
- optional Qwen-based suggestion enrichment if configured

## Docker Compose

The default Compose stack contains:

- `postgres`
- `redis`
- `opsin`
- `bot`
- `worker`
- optional `caddy` profile for public reverse proxying

Start the stack:

```bash
docker compose up --build
```

For a production-like run with reverse proxy:

```bash
MOLQUIZ_DOMAIN=your.domain.example docker compose --profile prod up --build -d
```

## Quality Checks

```bash
uv run ruff check src tests alembic
uv run pytest
```

## Deployment Notes

- Prefer webhook mode in production
- Keep `storage/` on a persistent volume
- Run `alembic upgrade head` on every deployment
- Keep `opsin`, `postgres`, and `redis` on the same Docker network as the bot
- Set a stable HTTPS webhook URL before switching from polling to webhook mode
- Do not commit the local `.env`

## Status

This repository already contains a working MVP backend and bot flow. The next major scale-up step is content growth: bulk PubChem ingestion, curated rational bank expansion, and a stronger moderation surface for reviewing generated aliases at scale.

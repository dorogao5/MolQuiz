from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Seed demo data for MolQuiz.")


@app.command()
def seed(path: Path = Path("data/demo_cards.yaml")) -> None:
    asyncio.run(_seed(path))


async def _seed(path: Path) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        entries = context.content_service.load_manual_entries(path)
        inserted = await context.content_service.seed_manual_entries(entries)
        typer.echo(f"Seeded/updated cards: {inserted}")
    finally:
        await context.close()


def main() -> None:
    app()

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Seed the full MolQuiz content bank.")


@app.command()
def seed(
    iupac_path: Path = Path("data/iupac_curated.yaml"),
    rational_path: Path = Path("data/rational_curated.yaml"),
) -> None:
    asyncio.run(_seed(iupac_path, rational_path))


async def _seed(iupac_path: Path, rational_path: Path) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        iupac_entries = context.content_service.load_manual_entries(iupac_path)
        rational_entries = context.content_service.load_manual_entries(rational_path)
        iupac_inserted = await context.content_service.seed_manual_entries(iupac_entries)
        rational_inserted = await context.content_service.seed_manual_entries(rational_entries)
        total_inserted = iupac_inserted + rational_inserted
        typer.echo(f"Seeded full content: iupac={iupac_inserted}, rational={rational_inserted}, total={total_inserted}")
    finally:
        await context.close()


def main() -> None:
    app()

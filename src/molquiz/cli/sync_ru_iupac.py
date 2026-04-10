from __future__ import annotations

import asyncio

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Synchronize stored Russian IUPAC primary names with the translator.")


@app.command()
def sync() -> None:
    asyncio.run(_sync())


async def _sync() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        summary = await context.content_service.sync_primary_ru_iupac_variants()
        typer.echo("Synchronized RU IUPAC variants:")
        typer.echo(f"  checked={summary['checked']}, updated={summary['updated']}")
    finally:
        await context.close()


def main() -> None:
    app()

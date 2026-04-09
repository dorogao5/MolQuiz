from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Apply review decisions from YAML.")


@app.command()
def apply(path: Path) -> None:
    asyncio.run(_apply(path))


async def _apply(path: Path) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        decisions = context.content_service.load_review_decisions(path)
        summary = await context.content_service.apply_review_decisions(decisions)
        typer.echo(
            (
                "Processed: {processed}, approved: {approved}, rejected: {rejected}, "
                "published toggles: {published_cards}"
            ).format(**summary)
        )
    finally:
        await context.close()


def main() -> None:
    app()

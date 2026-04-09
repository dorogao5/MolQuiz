from __future__ import annotations

import asyncio

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Recalculate card publication flags.")


@app.command()
def run(molecule_id: str | None = None) -> None:
    asyncio.run(_run(molecule_id))


async def _run(molecule_id: str | None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        changed = await context.content_service.refresh_publication_state(molecule_id=molecule_id)
        typer.echo(f"Publication state updated for {changed} cards")
    finally:
        await context.close()


def main() -> None:
    app()

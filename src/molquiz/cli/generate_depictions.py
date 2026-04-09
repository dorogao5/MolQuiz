from __future__ import annotations

import asyncio

import typer
from sqlalchemy import select

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.db.models import Molecule
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Generate depiction variants for molecules.")


@app.command()
def generate() -> None:
    asyncio.run(_generate())


async def _generate() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        async with context.session_factory() as session:
            molecules = (await session.scalars(select(Molecule))).all()
            for molecule in molecules:
                await context.content_service.ensure_depictions(session, molecule)
            await session.commit()
            typer.echo(f"Generated depictions for {len(molecules)} molecules")
    finally:
        await context.close()


def main() -> None:
    app()

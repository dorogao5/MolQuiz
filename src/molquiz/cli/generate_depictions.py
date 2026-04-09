from __future__ import annotations

import asyncio

import typer
from sqlalchemy import select
from structlog import get_logger

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.db.models import Molecule
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Generate depiction variants for molecules.")
logger = get_logger(__name__)


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
            logger.info(
                "depiction_generation_started",
                molecules_total=len(molecules),
                render_preset=context.depiction_service.render_preset,
            )
            regenerated = 0
            for index, molecule in enumerate(molecules, start=1):
                changed = await context.content_service.ensure_depictions(session, molecule)
                regenerated += int(changed)
                if index % 100 == 0:
                    logger.info(
                        "depiction_generation_progress",
                        molecules_processed=index,
                        molecules_total=len(molecules),
                        depictions_regenerated=regenerated,
                    )
            await session.commit()
            logger.info(
                "depiction_generation_finished",
                molecules_total=len(molecules),
                depictions_regenerated=regenerated,
                depictions_unchanged=len(molecules) - regenerated,
            )
            typer.echo(f"Generated depictions for {len(molecules)} molecules; regenerated {regenerated}")
    finally:
        await context.close()


def main() -> None:
    app()

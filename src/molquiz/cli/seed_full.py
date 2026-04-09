from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Seed the full MolQuiz content bank.")


@app.command()
def seed(
    iupac_path: Path = Path("data/iupac_curated.yaml"),
    rational_path: Path = Path("data/rational_curated.yaml"),
    batch_size: int = 50,
) -> None:
    asyncio.run(_seed(iupac_path, rational_path, batch_size=batch_size))


async def _seed(iupac_path: Path, rational_path: Path, *, batch_size: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        iupac_entries = context.content_service.load_manual_entries(iupac_path)
        rational_entries = context.content_service.load_manual_entries(rational_path)
        typer.echo("Start seeding:")
        typer.echo(
            f"  iupac_entries={len(iupac_entries)}, rational_entries={len(rational_entries)}, batch_size={batch_size}"
        )
        started_at = monotonic()
        iupac_inserted = await _seed_in_batches(
            context,
            label="iupac",
            entries=iupac_entries,
            batch_size=batch_size,
        )
        rational_inserted = await _seed_in_batches(
            context,
            label="rational",
            entries=rational_entries,
            batch_size=batch_size,
        )
        total_inserted = iupac_inserted + rational_inserted
        elapsed = monotonic() - started_at
        typer.echo("Seeded full content:")
        typer.echo(
            f"  iupac={iupac_inserted}, rational={rational_inserted}, total={total_inserted}, elapsed={elapsed:.1f}s"
        )
    finally:
        await context.close()


async def _seed_in_batches(context, *, label: str, entries: list, batch_size: int) -> int:
    inserted = 0
    total = len(entries)
    for offset in range(0, total, batch_size):
        batch = entries[offset : offset + batch_size]
        chunk_started = monotonic()
        inserted += await context.content_service.seed_manual_entries(batch)
        chunk_elapsed = monotonic() - chunk_started
        typer.echo(
            f"[{label}] processed {min(offset + len(batch), total)}/{total} entries, batch_elapsed={chunk_elapsed:.1f}s"
        )
    return inserted


def main() -> None:
    app()

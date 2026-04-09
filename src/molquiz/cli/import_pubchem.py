from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Import PubChem compounds by CID list.")


@app.command()
def import_cids(cid_file: Path, batch_size: int | None = None) -> None:
    content = cid_file.read_text(encoding="utf-8")
    cids = [int(line.strip()) for line in content.splitlines() if line.strip()]
    asyncio.run(_import(cids, batch_size=batch_size))


async def _import(cids: list[int], *, batch_size: int | None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        size = batch_size or settings.pubchem_batch_size
        imported = 0
        for offset in range(0, len(cids), size):
            batch = cids[offset : offset + size]
            compounds = await context.pubchem_client.fetch_properties(batch)
            imported += await context.content_service.import_pubchem_compounds(compounds)
        typer.echo(f"Imported compounds: {imported}")
    finally:
        await context.close()


def main() -> None:
    app()

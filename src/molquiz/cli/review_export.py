from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import yaml
from sqlalchemy import select

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.db.models import NamingVariant, ReviewTask, ReviewTaskStatus
from molquiz.logging import configure_logging

app = typer.Typer(add_completion=False, help="Export pending review tasks.")


@app.command()
def export(output: Path | None = None) -> None:
    asyncio.run(_export(output))


async def _export(output: Path | None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    context = await create_application_context(settings)
    try:
        async with context.session_factory() as session:
            tasks = (
                await session.scalars(select(ReviewTask).where(ReviewTask.status == ReviewTaskStatus.PENDING.value))
            ).all()
            naming_variants = (
                await session.scalars(
                    select(NamingVariant).where(
                        NamingVariant.molecule_id.in_(
                            [task.molecule_id for task in tasks if task.molecule_id is not None]
                        )
                    )
                )
            ).all()
        variants_by_molecule: dict[str, list[dict[str, str]]] = {}
        for variant in naming_variants:
            variants_by_molecule.setdefault(variant.molecule_id, []).append(
                {
                    "mode": variant.mode,
                    "locale": variant.locale,
                    "answer_text": variant.answer_text,
                    "review_status": variant.review_status,
                    "is_primary": str(variant.is_primary).lower(),
                }
            )
        output_path = output or settings.review_export_dir / "pending_review_tasks.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tasks": [
                {
                    "task_id": task.id,
                    "molecule_id": task.molecule_id,
                    "task_type": task.task_type,
                    "payload": task.payload,
                    "status": task.status,
                    "existing_variants": variants_by_molecule.get(task.molecule_id or "", []),
                    "decision_template": {
                        "task_id": task.id,
                        "action": "approve",
                        "answer_text": task.payload.get("proposed_ru") or task.payload.get("answer_text"),
                        "locale": task.payload.get("locale", "ru"),
                        "mode": (
                            "rational"
                            if task.task_type == "rational_alias_review"
                            else "iupac"
                        ),
                        "mark_primary": True,
                        "notes": "",
                    },
                }
                for task in tasks
            ]
        }
        output_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        typer.echo(f"Exported {len(tasks)} tasks to {output_path}")
    finally:
        await context.close()


def main() -> None:
    app()

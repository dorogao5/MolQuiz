from __future__ import annotations

import asyncio

from sqlalchemy import select
from structlog import get_logger

from molquiz.config import get_settings
from molquiz.container import create_application_context
from molquiz.db.models import (
    Molecule,
    NamingKind,
    NamingVariant,
    ReviewStatus,
    ReviewTask,
    ReviewTaskStatus,
    ReviewTaskType,
)
from molquiz.logging import configure_logging
from molquiz.services.normalization import build_token_signature
from molquiz.services.translator_ru import translate_iupac_en_to_ru

logger = get_logger(__name__)


async def process_once() -> bool:
    settings = get_settings()
    context = await create_application_context(settings)
    task = None
    try:
        async with context.session_factory() as session:
            task = await session.scalar(
                select(ReviewTask)
                .where(ReviewTask.status == ReviewTaskStatus.PENDING.value)
                .order_by(ReviewTask.created_at.asc())
                .limit(1)
            )
            if task is None:
                return False

            task.status = ReviewTaskStatus.PROCESSING.value
            await session.flush()

            if task.task_type == ReviewTaskType.GENERATE_DEPICTIONS.value and task.molecule_id:
                molecule = await session.get(Molecule, task.molecule_id)
                if molecule is not None:
                    await context.content_service.ensure_depictions(session, molecule)

            if task.task_type == ReviewTaskType.RU_IUPAC_TRANSLATION.value and task.molecule_id:
                en_name = task.payload.get("en_name")
                proposed_ru = task.payload.get("proposed_ru") or translate_iupac_en_to_ru(en_name)
                variant = await session.scalar(
                    select(NamingVariant).where(
                        NamingVariant.molecule_id == task.molecule_id,
                        NamingVariant.mode == "iupac",
                        NamingVariant.locale == "ru",
                        NamingVariant.answer_text == proposed_ru,
                    )
                )
                if variant is None:
                    session.add(
                        NamingVariant(
                            molecule_id=task.molecule_id,
                            mode="iupac",
                            locale="ru",
                            kind=NamingKind.CANONICAL.value,
                            answer_text=proposed_ru,
                            normalized_signature=build_token_signature(proposed_ru),
                            review_status=ReviewStatus.PENDING.value,
                            source_ref="worker:ru_translation",
                            is_primary=True,
                        )
                    )
                if context.qwen_client.enabled:
                    suggestion = await context.qwen_client.suggest_ru_aliases(
                        en_name=en_name,
                        canonical_smiles=task.payload.get("canonical_smiles", ""),
                    )
                    if suggestion is not None:
                        task.payload["qwen_suggestions"] = suggestion.suggestions
                        task.notes = suggestion.title
                        for alias in suggestion.suggestions:
                            existing_alias = await session.scalar(
                                select(NamingVariant).where(
                                    NamingVariant.molecule_id == task.molecule_id,
                                    NamingVariant.mode == "iupac",
                                    NamingVariant.locale == "ru",
                                    NamingVariant.answer_text == alias,
                                )
                            )
                            if existing_alias is None:
                                session.add(
                                    NamingVariant(
                                        molecule_id=task.molecule_id,
                                        mode="iupac",
                                        locale="ru",
                                        kind=NamingKind.ACCEPTED_ALIAS.value,
                                        answer_text=alias,
                                        normalized_signature=build_token_signature(alias),
                                        review_status=ReviewStatus.PENDING.value,
                                        source_ref="worker:qwen_suggestion",
                                        is_primary=False,
                                    )
                                )

            task.status = ReviewTaskStatus.DONE.value
            if task.molecule_id:
                await context.content_service._refresh_publication_state(
                    session,
                    molecule_id=task.molecule_id,
                )
            await session.commit()
            return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_task_failed", error=str(exc))
        if task is not None:
            async with context.session_factory() as session:
                failed_task = await session.get(ReviewTask, task.id)
                if failed_task is not None:
                    failed_task.status = ReviewTaskStatus.FAILED.value
                    failed_task.notes = str(exc)
                    await session.commit()
        return False
    finally:
        await context.close()


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.environment != "development")
    while True:
        processed = await process_once()
        if not processed:
            await asyncio.sleep(5)


def run() -> None:
    asyncio.run(_main())

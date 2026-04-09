from pathlib import Path

import pytest
from sqlalchemy import select

from molquiz.db.models import Card, Molecule, PublishStatus, ReviewTask, ReviewTaskType
from molquiz.services.content_service import ContentService, ReviewDecision
from molquiz.services.depiction import DepictionService
from molquiz.services.pubchem import PubChemCompound
from molquiz.services.qwen import QwenHeadlessClient


@pytest.mark.asyncio
async def test_pubchem_review_cycle_publishes_card_after_ru_approval(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None, None),
    )

    imported = await content_service.import_pubchem_compounds(
        [
            PubChemCompound(
                cid=1,
                iupac_name="2-methylpropane",
                canonical_smiles="CC(C)C",
                molecular_formula="C4H10",
                inchikey="TEST-INCHIKEY",
            )
        ]
    )
    assert imported == 1

    async with session_factory() as session:
        card = await session.scalar(select(Card))
        assert card is not None
        assert card.is_published is False

        molecule = await session.get(Molecule, card.molecule_id)
        assert molecule is not None
        assert molecule.publish_status == PublishStatus.REVIEW.value

        tasks = (await session.scalars(select(ReviewTask).where(ReviewTask.molecule_id == molecule.id))).all()
        ru_task = next(task for task in tasks if task.task_type == ReviewTaskType.RU_IUPAC_TRANSLATION.value)
        await content_service.ensure_depictions(session, molecule)
        await session.commit()

    summary = await content_service.apply_review_decisions(
        [
            ReviewDecision(
                task_id=ru_task.id,
                action="approve",
                answer_text="2-метилпропан",
                locale="ru",
                mode="iupac",
                mark_primary=True,
            )
        ]
    )
    assert summary["approved"] == 1

    async with session_factory() as session:
        card = await session.scalar(select(Card))
        molecule = await session.get(Molecule, card.molecule_id)
        assert card.is_published is True
        assert molecule.publish_status == PublishStatus.PUBLISHED.value

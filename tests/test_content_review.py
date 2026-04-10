from pathlib import Path

import pytest
from sqlalchemy import select

from molquiz.db.models import Card, Molecule, NamingVariant, PublishStatus, ReviewTask, ReviewTaskType
from molquiz.services.content_service import ContentService, ManualEntry, ReviewDecision
from molquiz.services.depiction import DepictionService
from molquiz.services.pubchem import PubChemCompound
from molquiz.services.qwen import QwenHeadlessClient


@pytest.mark.asyncio
async def test_pubchem_review_cycle_publishes_card_after_ru_approval(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
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


@pytest.mark.asyncio
async def test_seed_manual_entries_replaces_stale_primary_ru_variant(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    old_entry = ManualEntry(
        canonical_smiles="CCc1cccc(C)c1C",
        source_ref="test_seed",
        names={
            "iupac": {
                "en": ["1-ethyl-2,3-dimethylbenzene"],
                "ru": ["1-этил-2,3-диметилбензол"],
            }
        },
    )
    new_entry = ManualEntry(
        canonical_smiles="CCc1cccc(C)c1C",
        source_ref="test_seed",
        names={
            "iupac": {
                "en": ["1-ethyl-2,3-dimethylbenzene"],
                "ru": ["2,3-диметил-1-этилбензол"],
            }
        },
    )

    await content_service.seed_manual_entries([old_entry])
    await content_service.seed_manual_entries([new_entry])

    async with session_factory() as session:
        variants = (
            await session.scalars(
                select(NamingVariant).where(
                    NamingVariant.mode == "iupac",
                    NamingVariant.locale == "ru",
                )
            )
        ).all()

    assert [variant.answer_text for variant in variants if variant.is_primary] == ["2,3-диметил-1-этилбензол"]
    assert all(variant.answer_text != "1-этил-2,3-диметилбензол" for variant in variants)


@pytest.mark.asyncio
async def test_sync_primary_ru_iupac_variants_updates_existing_db_rows(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    await content_service.seed_manual_entries(
        [
            ManualEntry(
                canonical_smiles="CCc1cccc(C)c1C",
                source_ref="test_seed",
                names={
                    "iupac": {
                        "en": ["1-ethyl-2,3-dimethylbenzene"],
                        "ru": ["1-этил-2,3-диметилбензол"],
                    }
                },
            )
        ]
    )

    summary = await content_service.sync_primary_ru_iupac_variants()
    assert summary["updated"] == 1

    async with session_factory() as session:
        variants = (
            await session.scalars(
                select(NamingVariant).where(
                    NamingVariant.mode == "iupac",
                    NamingVariant.locale == "ru",
                )
            )
        ).all()

    assert [variant.answer_text for variant in variants if variant.is_primary] == ["2,3-диметил-1-этилбензол"]
    assert all(variant.answer_text != "1-этил-2,3-диметилбензол" for variant in variants)

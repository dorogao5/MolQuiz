import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from molquiz.db.models import DepictionVariant, Mode, UserProfile
from molquiz.services.answer_checker import AnswerChecker
from molquiz.services.content_service import ContentService
from molquiz.services.depiction import DepictionService
from molquiz.services.practice_service import PracticeService
from molquiz.services.qwen import QwenHeadlessClient
from molquiz.services.session_store import InMemorySessionStore


class NoopOpsinClient:
    async def parse_name(self, name: str):
        return None


@pytest.mark.asyncio
async def test_practice_service_issue_and_answer_card(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
        content_service,
    )

    entries = content_service.load_manual_entries(Path("data/demo_cards.yaml"))
    await content_service.seed_manual_entries(entries[:1])

    class TgUser:
        id = 101
        username = "tester"
        first_name = "Test"
        last_name = "User"

    await practice_service.ensure_user(TgUser())
    settings = await practice_service.set_mode(TgUser.id, Mode.IUPAC)
    assert settings.mode == "iupac"

    card = await practice_service.issue_card(TgUser.id)
    assert card is not None
    assert card.primary_ru == "2-метилпропан"
    assert card.image_path.exists()

    result = await practice_service.evaluate_answer(TgUser.id, "2-метилпропан")
    assert result is not None
    practice_card, outcome = result
    assert practice_card.card.mode == "iupac"
    assert outcome.accepted is True


@pytest.mark.asyncio
async def test_practice_service_regenerates_outdated_depictions(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
        content_service,
    )

    entries = content_service.load_manual_entries(Path("data/demo_cards.yaml"))
    await content_service.seed_manual_entries(entries[:1])

    class TgUser:
        id = 202
        username = "tester"
        first_name = "Test"
        last_name = "User"

    await practice_service.ensure_user(TgUser())

    async with session_factory() as session:
        depictions = (await session.scalars(select(DepictionVariant))).all()
        for depiction in depictions:
            depiction.render_preset = "house-default"
            depiction.telegram_file_id = "stale-file-id"
            depiction.is_active = True
            os.unlink(depiction.storage_path)
        await session.commit()

    card = await practice_service.issue_card(TgUser.id)
    assert card is not None
    assert card.depiction.render_preset == depiction_service.render_preset
    assert card.depiction.telegram_file_id is None
    assert card.image_path.exists()

    async with session_factory() as session:
        depictions = (await session.scalars(select(DepictionVariant))).all()
        current_active = [
            depiction
            for depiction in depictions
            if depiction.is_active and depiction.render_preset == depiction_service.render_preset
        ]
        stale_active = [
            depiction
            for depiction in depictions
            if depiction.is_active and depiction.render_preset == "house-default"
        ]

    assert len(current_active) == 1
    assert stale_active == []


@pytest.mark.asyncio
async def test_practice_service_issue_card_with_topic_filters(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
        content_service,
    )

    entries = content_service.load_manual_entries(Path("data/demo_cards.yaml"))
    await content_service.seed_manual_entries(entries)

    class TgUser:
        id = 303
        username = "tester"
        first_name = "Test"
        last_name = "User"

    await practice_service.ensure_user(TgUser())
    await practice_service.set_mode(TgUser.id, Mode.IUPAC)
    await practice_service.set_difficulty(TgUser.id, 5)
    await practice_service.toggle_topic(TgUser.id, "aromatic")
    await practice_service.toggle_topic(TgUser.id, "oxygen")

    card = await practice_service.issue_card(TgUser.id)
    assert card is not None
    assert card.primary_en == "2-[4-(2-methylpropyl)phenyl]propanoic acid"


def test_build_card_query_uses_jsonb_contains_for_postgresql() -> None:
    practice_service = PracticeService(
        session_factory=None,
        session_store=None,
        answer_checker=AnswerChecker(NoopOpsinClient()),
        content_service=None,
    )
    settings = type(
        "SettingsStub",
        (),
        {
            "mode": "iupac",
            "difficulty_min": 1,
            "difficulty_max": 5,
            "topic_tags": ["alkene", "halogen"],
        },
    )()

    query = practice_service._build_card_query(
        "user-id",
        settings,
        repeat_errors=False,
        dialect_name="postgresql",
    )
    sql = str(query.compile(dialect=postgresql.dialect()))

    assert "CAST(cards.topic_tags AS JSONB) @>" in sql


@pytest.mark.asyncio
async def test_ensure_user_repairs_missing_settings_and_stats(session_factory, tmp_path: Path) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
        content_service,
    )

    entries = content_service.load_manual_entries(Path("data/demo_cards.yaml"))
    await content_service.seed_manual_entries(entries[:1])

    async with session_factory() as session:
        session.add(
            UserProfile(
                telegram_id=404,
                username="legacy",
                first_name="Legacy",
                last_name="User",
            )
        )
        await session.commit()

    class TgUser:
        id = 404
        username = "legacy"
        first_name = "Legacy"
        last_name = "User"

    await practice_service.ensure_user(TgUser())
    settings = await practice_service.get_settings(TgUser.id)
    assert settings.mode == "iupac"

    card = await practice_service.issue_card(TgUser.id)
    assert card is not None


@pytest.mark.asyncio
async def test_rational_mode_accepts_parent_hydrocarbon_alias_and_difficulty_filters_cards(
    session_factory,
    tmp_path: Path,
) -> None:
    depiction_service = DepictionService(tmp_path / "storage")
    content_service = ContentService(
        session_factory,
        depiction_service,
        QwenHeadlessClient(None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
        content_service,
    )

    entries = [
        entry
        for entry in content_service.load_manual_entries(Path("data/rational_curated.yaml"))
        if entry.canonical_smiles in {"C=O", "CCc1ccccc1"}
    ]
    await content_service.seed_manual_entries(entries)

    class TgUser:
        id = 505
        username = "tester"
        first_name = "Test"
        last_name = "User"

    await practice_service.ensure_user(TgUser())
    await practice_service.set_mode(TgUser.id, Mode.RATIONAL)

    await practice_service.set_difficulty(TgUser.id, 4)
    hard_card = await practice_service.issue_card(TgUser.id)
    assert hard_card is not None
    assert hard_card.card.difficulty == 4
    assert hard_card.primary_ru == "метилфенилметан"

    result = await practice_service.evaluate_answer(TgUser.id, "метилфенилметан")
    assert result is not None
    _, outcome = result
    assert outcome.accepted is True

    await practice_service.set_difficulty(TgUser.id, 1)
    easy_card = await practice_service.issue_card(TgUser.id)
    assert easy_card is not None
    assert easy_card.card.difficulty == 1
    assert easy_card.primary_ru == "формальдегид"

import os
from pathlib import Path

import pytest
from sqlalchemy import select

from molquiz.db.models import DepictionVariant, Mode
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

    assert len(current_active) == 4
    assert stale_active == []

from pathlib import Path

import pytest

from molquiz.db.models import Mode
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
        QwenHeadlessClient(None, None),
    )
    practice_service = PracticeService(
        session_factory,
        InMemorySessionStore(),
        AnswerChecker(NoopOpsinClient()),
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

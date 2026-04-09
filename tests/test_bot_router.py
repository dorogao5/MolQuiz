from __future__ import annotations

from types import SimpleNamespace

import pytest

from molquiz.bot import router
from molquiz.db.models import Mode


class PracticeServiceStub:
    def __init__(self, practice_card) -> None:
        self.practice_card = practice_card
        self.calls: list[tuple[int, bool]] = []
        self.remembered: list[tuple[str, str]] = []

    async def issue_card(self, telegram_user_id: int, *, repeat_errors: bool = False):
        self.calls.append((telegram_user_id, repeat_errors))
        return self.practice_card

    async def remember_telegram_file_id(self, depiction_variant_id: str, file_id: str) -> None:
        self.remembered.append((depiction_variant_id, file_id))


@pytest.mark.asyncio
async def test_send_new_card_uses_explicit_telegram_user_id(monkeypatch) -> None:
    practice_card = SimpleNamespace(
        card=SimpleNamespace(mode=Mode.IUPAC.value, difficulty=3),
        depiction=SimpleNamespace(id="depiction-1"),
    )
    practice_service = PracticeServiceStub(practice_card)
    app_context = SimpleNamespace(practice_service=practice_service)

    sent_message = SimpleNamespace(photo=[SimpleNamespace(file_id="telegram-file-id")])

    async def fake_send_depiction(*, bot, message, practice_card, caption):
        assert bot is message.bot
        assert "Режим" in caption
        return sent_message

    monkeypatch.setattr(router, "_send_depiction", fake_send_depiction)

    message = SimpleNamespace(
        bot=object(),
        from_user=SimpleNamespace(id=999999),
        chat=SimpleNamespace(id=42),
        answer=None,
    )

    await router._send_new_card(
        app_context=app_context,
        message=message,
        telegram_user_id=123456,
        repeat_errors=False,
    )

    assert practice_service.calls == [(123456, False)]
    assert practice_service.remembered == [("depiction-1", "telegram-file-id")]

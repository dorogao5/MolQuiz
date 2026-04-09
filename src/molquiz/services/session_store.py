from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis


@dataclass(slots=True)
class ActivePracticeSession:
    telegram_user_id: int
    card_id: str
    depiction_variant_id: str
    started_at: str
    mode: str
    hint_index: int = 0
    repeat_errors: bool = False


class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[int, ActivePracticeSession] = {}

    async def get(self, telegram_user_id: int) -> ActivePracticeSession | None:
        return self._data.get(telegram_user_id)

    async def set(self, session: ActivePracticeSession) -> None:
        self._data[session.telegram_user_id] = session

    async def clear(self, telegram_user_id: int) -> None:
        self._data.pop(telegram_user_id, None)

    async def increment_hint(self, telegram_user_id: int) -> ActivePracticeSession | None:
        session = self._data.get(telegram_user_id)
        if session is None:
            return None
        session.hint_index += 1
        return session


class RedisSessionStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _key(self, telegram_user_id: int) -> str:
        return f"molquiz:session:{telegram_user_id}"

    async def get(self, telegram_user_id: int) -> ActivePracticeSession | None:
        raw = await self.redis.get(self._key(telegram_user_id))
        if raw is None:
            return None
        return ActivePracticeSession(**json.loads(raw))

    async def set(self, session: ActivePracticeSession) -> None:
        await self.redis.set(
            self._key(session.telegram_user_id),
            json.dumps(asdict(session)),
            ex=self.ttl_seconds,
        )

    async def clear(self, telegram_user_id: int) -> None:
        await self.redis.delete(self._key(telegram_user_id))

    async def increment_hint(self, telegram_user_id: int) -> ActivePracticeSession | None:
        session = await self.get(telegram_user_id)
        if session is None:
            return None
        session.hint_index += 1
        await self.set(session)
        return session


def make_active_session(
    telegram_user_id: int,
    *,
    card_id: str,
    depiction_variant_id: str,
    mode: str,
    repeat_errors: bool = False,
) -> ActivePracticeSession:
    return ActivePracticeSession(
        telegram_user_id=telegram_user_id,
        card_id=card_id,
        depiction_variant_id=depiction_variant_id,
        started_at=datetime.now(UTC).isoformat(),
        mode=mode,
        repeat_errors=repeat_errors,
    )

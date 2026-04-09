from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from molquiz.config import Settings
from molquiz.db.session import create_engine, create_schema, create_session_factory
from molquiz.services.answer_checker import AnswerChecker
from molquiz.services.content_service import ContentService
from molquiz.services.depiction import DepictionService
from molquiz.services.opsin import OpsinClient
from molquiz.services.practice_service import PracticeService
from molquiz.services.pubchem import PubChemClient
from molquiz.services.qwen import QwenHeadlessClient
from molquiz.services.session_store import InMemorySessionStore, RedisSessionStore


@dataclass(slots=True)
class ApplicationContext:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis | None
    opsin_client: OpsinClient
    pubchem_client: PubChemClient
    qwen_client: QwenHeadlessClient
    depiction_service: DepictionService
    content_service: ContentService
    practice_service: PracticeService

    async def close(self) -> None:
        await self.opsin_client.aclose()
        await self.pubchem_client.aclose()
        await self.qwen_client.aclose()
        if self.redis is not None:
            await self.redis.aclose()
        await self.engine.dispose()


async def create_application_context(settings: Settings) -> ApplicationContext:
    engine = create_engine(settings.database_url, echo=settings.debug)
    if settings.auto_create_schema:
        await create_schema(engine)
    session_factory = create_session_factory(engine)

    redis = None
    if settings.redis_url.startswith("memory://"):
        session_store = InMemorySessionStore()
    else:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        session_store = RedisSessionStore(redis, ttl_seconds=settings.session_ttl_seconds)

    opsin_client = OpsinClient(
        settings.opsin_base_url,
        timeout=settings.request_timeout_seconds,
    )
    pubchem_client = PubChemClient(
        settings.pubchem_base_url,
        timeout=settings.request_timeout_seconds,
    )
    qwen_client = QwenHeadlessClient(
        settings.qwen_command,
        timeout=settings.request_timeout_seconds,
    )
    depiction_service = DepictionService(settings.storage_dir)
    answer_checker = AnswerChecker(opsin_client)
    content_service = ContentService(session_factory, depiction_service, qwen_client)
    practice_service = PracticeService(session_factory, session_store, answer_checker)

    return ApplicationContext(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        opsin_client=opsin_client,
        pubchem_client=pubchem_client,
        qwen_client=qwen_client,
        depiction_service=depiction_service,
        content_service=content_service,
        practice_service=practice_service,
    )

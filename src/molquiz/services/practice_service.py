from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from random import choice

from aiogram.types import User as TelegramUser
from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from molquiz.db.models import (
    Attempt,
    AttemptVerdict,
    Card,
    DepictionVariant,
    Locale,
    Mode,
    Molecule,
    NamingVariant,
    UserProfile,
    UserSettings,
    UserStats,
)
from molquiz.services.answer_checker import AnswerChecker, ValidationOutcome
from molquiz.services.hints import build_hints
from molquiz.services.session_store import ActivePracticeSession, make_active_session

SUPPORTED_TOPICS = [
    ("aromatic", "Ароматика"),
    ("cyclo", "Циклы"),
    ("alkene", "Кратные связи"),
    ("oxygen", "Кислород"),
    ("nitrogen", "Азот"),
    ("halogen", "Галогены"),
]


@dataclass(slots=True)
class PracticeCard:
    card: Card
    molecule: Molecule
    depiction: DepictionVariant
    naming_variants: list[NamingVariant]
    hints: list[str]

    @property
    def primary_ru(self) -> str:
        return self._primary(Locale.RU)

    @property
    def primary_en(self) -> str:
        return self._primary(Locale.EN)

    @property
    def image_path(self) -> Path:
        return Path(self.depiction.storage_path)

    def _primary(self, locale: Locale) -> str:
        for variant in self.naming_variants:
            if variant.locale == locale.value and variant.is_primary:
                return variant.answer_text
        for variant in self.naming_variants:
            if variant.locale == locale.value:
                return variant.answer_text
        return "—"


class PracticeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        session_store,
        answer_checker: AnswerChecker,
        content_service,
    ) -> None:
        self.session_factory = session_factory
        self.session_store = session_store
        self.answer_checker = answer_checker
        self.content_service = content_service

    async def ensure_user(self, telegram_user: TelegramUser) -> UserProfile:
        async with self.session_factory() as session:
            user = await session.scalar(select(UserProfile).where(UserProfile.telegram_id == telegram_user.id))
            if user is None:
                user = UserProfile(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name,
                )
                session.add(user)
                await session.flush()
            else:
                user.username = telegram_user.username
                user.first_name = telegram_user.first_name
                user.last_name = telegram_user.last_name

            await self._ensure_user_related_rows(session, user.id)
            await session.commit()
            return user

    async def get_settings(self, telegram_user_id: int) -> UserSettings:
        async with self.session_factory() as session:
            settings = await self._get_settings_for_update(session, telegram_user_id)
            await session.commit()
            return settings

    async def set_mode(self, telegram_user_id: int, mode: Mode) -> UserSettings:
        async with self.session_factory() as session:
            settings = await self._get_settings_for_update(session, telegram_user_id)
            settings.mode = mode.value
            await session.commit()
            return settings

    async def set_difficulty(self, telegram_user_id: int, difficulty: int) -> UserSettings:
        async with self.session_factory() as session:
            settings = await self._get_settings_for_update(session, telegram_user_id)
            settings.difficulty_min = difficulty
            settings.difficulty_max = difficulty
            await session.commit()
            return settings

    async def toggle_topic(self, telegram_user_id: int, topic: str) -> UserSettings:
        async with self.session_factory() as session:
            settings = await self._get_settings_for_update(session, telegram_user_id)
            tags = set(settings.topic_tags or [])
            if topic == "all":
                settings.topic_tags = []
            elif topic in tags:
                tags.remove(topic)
                settings.topic_tags = sorted(tags)
            else:
                tags.add(topic)
                settings.topic_tags = sorted(tags)
            await session.commit()
            return settings

    async def issue_card(self, telegram_user_id: int, *, repeat_errors: bool = False) -> PracticeCard | None:
        async with self.session_factory() as session:
            settings = await self._get_settings_for_update(session, telegram_user_id)
            user = await self._get_user(session, telegram_user_id)
            query = self._build_card_query(
                user.id,
                settings,
                repeat_errors=repeat_errors,
                dialect_name=session.get_bind().dialect.name,
            )
            card = await session.scalar(query)
            if card is None:
                return None

            molecule = await session.get(Molecule, card.molecule_id)
            depictions_changed = await self.content_service.ensure_depictions(session, molecule)
            if depictions_changed:
                await session.commit()
            depictions = (
                await session.scalars(
                    select(DepictionVariant).where(
                        DepictionVariant.molecule_id == molecule.id, DepictionVariant.is_active.is_(True)
                    )
                )
            ).all()
            naming_variants = (
                await session.scalars(
                    select(NamingVariant).where(
                        NamingVariant.molecule_id == molecule.id,
                        NamingVariant.mode == card.mode,
                        NamingVariant.review_status == "approved",
                    )
                )
            ).all()
            if not depictions or not naming_variants:
                return None

            depiction = choice(depictions)
            hints = build_hints(molecule.descriptor_snapshot, molecule.molecular_formula)
            practice_card = PracticeCard(
                card=card,
                molecule=molecule,
                depiction=depiction,
                naming_variants=naming_variants,
                hints=hints,
            )
            await self.session_store.set(
                make_active_session(
                    telegram_user_id,
                    card_id=card.id,
                    depiction_variant_id=depiction.id,
                    mode=card.mode,
                    repeat_errors=repeat_errors,
                )
            )
            return practice_card

    async def get_active_card(self, telegram_user_id: int) -> PracticeCard | None:
        active_session = await self.session_store.get(telegram_user_id)
        if active_session is None:
            return None
        return await self._load_card(active_session)

    async def remember_telegram_file_id(self, depiction_variant_id: str, file_id: str) -> None:
        async with self.session_factory() as session:
            depiction = await session.get(DepictionVariant, depiction_variant_id)
            if depiction is None:
                return
            depiction.telegram_file_id = file_id
            await session.commit()

    async def reveal_answer(self, telegram_user_id: int) -> PracticeCard | None:
        practice_card = await self.get_active_card(telegram_user_id)
        await self.session_store.clear(telegram_user_id)
        return practice_card

    async def next_hint(self, telegram_user_id: int) -> str | None:
        active_session = await self.session_store.increment_hint(telegram_user_id)
        if active_session is None:
            return None
        practice_card = await self._load_card(active_session)
        if practice_card is None:
            return None
        index = min(active_session.hint_index - 1, len(practice_card.hints) - 1)
        if index < 0:
            index = 0
        return practice_card.hints[index]

    async def evaluate_answer(
        self,
        telegram_user_id: int,
        raw_answer: str,
    ) -> tuple[PracticeCard, ValidationOutcome] | None:
        active_session = await self.session_store.get(telegram_user_id)
        if active_session is None:
            return None

        practice_card = await self._load_card(active_session)
        if practice_card is None:
            return None

        started_at = datetime.fromisoformat(active_session.started_at)
        latency_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        outcome = await self.answer_checker.validate(
            mode=Mode(practice_card.card.mode),
            molecule_inchikey=practice_card.molecule.inchikey,
            naming_variants=practice_card.naming_variants,
            raw_answer=raw_answer,
        )

        async with self.session_factory() as session:
            user = await self._get_user(session, telegram_user_id)
            stats = await session.scalar(select(UserStats).where(UserStats.user_id == user.id))
            if stats is None:
                stats = UserStats(user_id=user.id)
                session.add(stats)
                await session.flush()

            session.add(
                Attempt(
                    user_id=user.id,
                    card_id=practice_card.card.id,
                    depiction_variant_id=practice_card.depiction.id,
                    answer_locale=outcome.locale.value if outcome.locale else None,
                    raw_answer=raw_answer,
                    normalized_answer=outcome.normalized_answer,
                    verdict=(AttemptVerdict.CORRECT.value if outcome.accepted else AttemptVerdict.WRONG.value),
                    error_category=outcome.error_category.value if outcome.error_category else None,
                    latency_ms=latency_ms,
                )
            )
            stats.total_attempts += 1
            stats.last_answered_at = datetime.now(UTC)
            if outcome.accepted:
                stats.correct_answers += 1
                stats.current_streak += 1
                stats.best_streak = max(stats.best_streak, stats.current_streak)
            else:
                stats.wrong_answers += 1
                stats.current_streak = 0
            await session.commit()

        if outcome.accepted:
            await self.session_store.clear(telegram_user_id)
        return practice_card, outcome

    async def get_stats(self, telegram_user_id: int) -> UserStats | None:
        async with self.session_factory() as session:
            user = await session.scalar(select(UserProfile).where(UserProfile.telegram_id == telegram_user_id))
            if user is None:
                return None
            await self._ensure_user_related_rows(session, user.id)
            await session.commit()
            return await session.scalar(select(UserStats).where(UserStats.user_id == user.id))

    def _build_card_query(
        self,
        user_id: str,
        settings: UserSettings,
        *,
        repeat_errors: bool,
        dialect_name: str,
    ) -> Select[tuple[Card]]:
        stmt = select(Card).where(
            Card.mode == settings.mode,
            Card.is_published.is_(True),
            Card.difficulty >= settings.difficulty_min,
            Card.difficulty <= settings.difficulty_max,
        )
        if settings.topic_tags:
            for tag in settings.topic_tags:
                if dialect_name == "postgresql":
                    stmt = stmt.where(cast(Card.topic_tags, JSONB).contains([tag]))
                else:
                    stmt = stmt.where(cast(Card.topic_tags, String).like(f'%"{tag}"%'))

        if repeat_errors:
            subquery = (
                select(Attempt.card_id)
                .where(Attempt.user_id == user_id, Attempt.verdict == AttemptVerdict.WRONG.value)
                .order_by(Attempt.created_at.desc())
                .limit(30)
            )
            stmt = stmt.where(Card.id.in_(subquery))

        return stmt.order_by(func.random()).limit(1)

    async def _load_card(self, active_session: ActivePracticeSession) -> PracticeCard | None:
        async with self.session_factory() as session:
            card = await session.get(Card, active_session.card_id)
            depiction = await session.get(DepictionVariant, active_session.depiction_variant_id)
            if card is None or depiction is None:
                return None
            molecule = await session.get(Molecule, card.molecule_id)
            naming_variants = (
                await session.scalars(
                    select(NamingVariant).where(
                        NamingVariant.molecule_id == card.molecule_id,
                        NamingVariant.mode == card.mode,
                        NamingVariant.review_status == "approved",
                    )
                )
            ).all()
            return PracticeCard(
                card=card,
                molecule=molecule,
                depiction=depiction,
                naming_variants=naming_variants,
                hints=build_hints(molecule.descriptor_snapshot, molecule.molecular_formula),
            )

    async def _get_user(self, session: AsyncSession, telegram_user_id: int) -> UserProfile:
        user = await session.scalar(select(UserProfile).where(UserProfile.telegram_id == telegram_user_id))
        if user is None:
            raise LookupError("User not found")
        return user

    async def _get_settings_for_update(self, session: AsyncSession, telegram_user_id: int) -> UserSettings:
        user = await self._get_user(session, telegram_user_id)
        await self._ensure_user_related_rows(session, user.id)
        settings = await session.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
        if settings is None:
            raise LookupError("User settings not found after repair")
        return settings

    async def _ensure_user_related_rows(self, session: AsyncSession, user_id: str) -> None:
        settings = await session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
        if settings is None:
            session.add(UserSettings(user_id=user_id))

        stats = await session.scalar(select(UserStats).where(UserStats.user_id == user_id))
        if stats is None:
            session.add(UserStats(user_id=user_id))

        await session.flush()

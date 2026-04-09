from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Mode(StrEnum):
    IUPAC = "iupac"
    RATIONAL = "rational"


class Locale(StrEnum):
    RU = "ru"
    EN = "en"


class NamingKind(StrEnum):
    CANONICAL = "canonical"
    ACCEPTED_ALIAS = "accepted_alias"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublishStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"


class AttemptVerdict(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"


class ErrorCategory(StrEnum):
    PARENT_CHAIN = "parent_chain"
    LOCANTS = "locants"
    SUBSTITUENT_ORDER = "substituent_order"
    MULTIPLICATIVE_PREFIX = "multiplicative_prefix"
    SUFFIX_MAIN_FUNCTION = "suffix_main_function"
    UNSUPPORTED_ALTERNATIVE_FORM = "unsupported_alternative_form"


class ReviewTaskType(StrEnum):
    RU_IUPAC_TRANSLATION = "ru_iupac_translation"
    RATIONAL_ALIAS_REVIEW = "rational_alias_review"
    OPSIN_ROUNDTRIP = "opsin_roundtrip"
    GENERATE_DEPICTIONS = "generate_depictions"


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    settings: Mapped[UserSettings] = relationship(back_populates="user", uselist=False)
    stats: Mapped[UserStats] = relationship(back_populates="user", uselist=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True)
    mode: Mapped[str] = mapped_column(String(32), default=Mode.IUPAC.value)
    difficulty_min: Mapped[int] = mapped_column(Integer, default=1)
    difficulty_max: Mapped[int] = mapped_column(Integer, default=5)
    topic_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[UserProfile] = relationship(back_populates="settings")


class Molecule(Base):
    __tablename__ = "molecules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    inchikey: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_smiles: Mapped[str] = mapped_column(Text, unique=True)
    molecular_formula: Mapped[str] = mapped_column(String(128))
    descriptor_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    publish_status: Mapped[str] = mapped_column(String(32), default=PublishStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    depictions: Mapped[list[DepictionVariant]] = relationship(back_populates="molecule")
    names: Mapped[list[NamingVariant]] = relationship(back_populates="molecule")
    cards: Mapped[list[Card]] = relationship(back_populates="molecule")


class DepictionVariant(Base):
    __tablename__ = "depiction_variants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    molecule_id: Mapped[str] = mapped_column(ForeignKey("molecules.id", ondelete="CASCADE"), index=True)
    render_preset: Mapped[str] = mapped_column(String(64), default="default")
    rotation_seed: Mapped[int] = mapped_column(Integer, default=0)
    flip_x: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_path: Mapped[str] = mapped_column(Text)
    image_hash: Mapped[str | None] = mapped_column(String(64))
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    molecule: Mapped[Molecule] = relationship(back_populates="depictions")


class NamingVariant(Base):
    __tablename__ = "naming_variants"
    __table_args__ = (
        UniqueConstraint("molecule_id", "mode", "locale", "answer_text", name="uq_naming_variant_answer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    molecule_id: Mapped[str] = mapped_column(ForeignKey("molecules.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(32))
    answer_text: Mapped[str] = mapped_column(Text)
    normalized_signature: Mapped[str] = mapped_column(Text, index=True)
    review_status: Mapped[str] = mapped_column(String(32), default=ReviewStatus.PENDING.value)
    source_ref: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    molecule: Mapped[Molecule] = relationship(back_populates="names")


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (UniqueConstraint("molecule_id", "mode", name="uq_card_per_mode"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    molecule_id: Mapped[str] = mapped_column(ForeignKey("molecules.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    topic_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    enabled_hints: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    molecule: Mapped[Molecule] = relationship(back_populates="cards")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    depiction_variant_id: Mapped[str | None] = mapped_column(ForeignKey("depiction_variants.id", ondelete="SET NULL"))
    answer_locale: Mapped[str | None] = mapped_column(String(8))
    raw_answer: Mapped[str] = mapped_column(Text)
    normalized_answer: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(32))
    error_category: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserStats(Base):
    __tablename__ = "user_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    wrong_answers: Mapped[int] = mapped_column(Integer, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[UserProfile] = relationship(back_populates="stats")


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    molecule_id: Mapped[str | None] = mapped_column(ForeignKey("molecules.id", ondelete="CASCADE"), index=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default=ReviewTaskStatus.PENDING.value, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

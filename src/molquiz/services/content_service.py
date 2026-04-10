from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog import get_logger

from molquiz.db.models import (
    Card,
    DepictionVariant,
    Locale,
    Mode,
    Molecule,
    NamingKind,
    NamingVariant,
    PublishStatus,
    ReviewStatus,
    ReviewTask,
    ReviewTaskStatus,
    ReviewTaskType,
)
from molquiz.services.depiction import DepictionService
from molquiz.services.normalization import build_token_signature
from molquiz.services.pubchem import PubChemCompound
from molquiz.services.qwen import QwenHeadlessClient
from molquiz.services.translator_ru import translate_iupac_en_to_ru

DEFAULT_HINTS = ["class", "formula", "main_chain"]
DEFAULT_VARIANTS = [(0, False)]
EXPECTED_VARIANT_COUNT = len(DEFAULT_VARIANTS)
REQUIRED_LOCALES = {Locale.RU.value, Locale.EN.value}

logger = get_logger(__name__)


def _path_exists(path: str) -> bool:
    return Path(path).exists()


@dataclass(slots=True)
class ManualEntry:
    canonical_smiles: str
    names: dict[str, dict[str, list[str]]]
    difficulty: int | None = None
    topic_tags: list[str] | None = None
    source_ref: str | None = None


@dataclass(slots=True)
class ReviewDecision:
    task_id: str
    action: str
    answer_text: str | None = None
    locale: str | None = None
    mode: str | None = None
    mark_primary: bool = True
    notes: str | None = None


class ContentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        depiction_service: DepictionService,
        qwen_client: QwenHeadlessClient,
    ) -> None:
        self.session_factory = session_factory
        self.depiction_service = depiction_service
        self.qwen_client = qwen_client

    def load_manual_entries(self, path: Path) -> list[ManualEntry]:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries: list[ManualEntry] = []
        for item in payload.get("entries", []):
            entries.append(
                ManualEntry(
                    canonical_smiles=item["canonical_smiles"],
                    names=item["names"],
                    difficulty=item.get("difficulty"),
                    topic_tags=item.get("topic_tags"),
                    source_ref=item.get("source_ref"),
                )
            )
        return entries

    def load_review_decisions(self, path: Path) -> list[ReviewDecision]:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        decisions: list[ReviewDecision] = []
        for item in payload.get("tasks", []):
            decisions.append(
                ReviewDecision(
                    task_id=item["task_id"],
                    action=item["action"],
                    answer_text=item.get("answer_text"),
                    locale=item.get("locale"),
                    mode=item.get("mode"),
                    mark_primary=item.get("mark_primary", True),
                    notes=item.get("notes"),
                )
            )
        return decisions

    async def seed_manual_entries(self, entries: list[ManualEntry]) -> int:
        created_cards = 0
        async with self.session_factory() as session:
            for entry in entries:
                molecule = await self._upsert_molecule(
                    session,
                    canonical_smiles=entry.canonical_smiles,
                    molecular_formula=None,
                    inchikey=None,
                    provenance={"source": entry.source_ref or "manual_seed"},
                )
                descriptors = molecule.descriptor_snapshot
                difficulty = entry.difficulty or int(descriptors.get("difficulty", 1))
                topic_tags = entry.topic_tags or descriptors.get("topic_tags") or []

                for mode_key, locale_payload in entry.names.items():
                    mode = Mode(mode_key)
                    for locale_key, aliases in locale_payload.items():
                        locale = Locale(locale_key)
                        for index, alias in enumerate(aliases):
                            kind = NamingKind.CANONICAL if index == 0 else NamingKind.ACCEPTED_ALIAS
                            variant = await self._upsert_naming_variant(
                                session,
                                molecule_id=molecule.id,
                                mode=mode,
                                locale=locale,
                                answer_text=alias,
                                kind=kind,
                                review_status=ReviewStatus.APPROVED,
                                source_ref=entry.source_ref or "manual_seed",
                                is_primary=index == 0,
                                replace_existing_primary=index == 0,
                            )
                            session.add(variant)

                    await self._upsert_card(
                        session,
                        molecule_id=molecule.id,
                        mode=mode,
                        difficulty=difficulty,
                        topic_tags=topic_tags,
                        is_published=True,
                        provenance={"source": entry.source_ref or "manual_seed"},
                    )
                    created_cards += 1

                await self.ensure_depictions(session, molecule)
                await self._refresh_publication_state(session, molecule_id=molecule.id)

            await session.commit()
        return created_cards

    async def import_pubchem_compounds(self, compounds: list[PubChemCompound]) -> int:
        imported = 0
        async with self.session_factory() as session:
            for compound in compounds:
                molecule = await self._upsert_molecule(
                    session,
                    canonical_smiles=compound.canonical_smiles,
                    molecular_formula=compound.molecular_formula,
                    inchikey=compound.inchikey,
                    provenance={"source": "pubchem", "cid": compound.cid},
                )
                en_variant = await self._upsert_naming_variant(
                    session,
                    molecule_id=molecule.id,
                    mode=Mode.IUPAC,
                    locale=Locale.EN,
                    answer_text=compound.iupac_name,
                    kind=NamingKind.CANONICAL,
                    review_status=ReviewStatus.APPROVED,
                    source_ref=f"pubchem:cid:{compound.cid}",
                    is_primary=True,
                    replace_existing_primary=True,
                )
                session.add(en_variant)

                ru_alias = translate_iupac_en_to_ru(compound.iupac_name)
                ru_variant = await self._upsert_naming_variant(
                    session,
                    molecule_id=molecule.id,
                    mode=Mode.IUPAC,
                    locale=Locale.RU,
                    answer_text=ru_alias,
                    kind=NamingKind.CANONICAL,
                    review_status=ReviewStatus.PENDING,
                    source_ref=f"rule_based:pubchem:cid:{compound.cid}",
                    is_primary=True,
                    replace_existing_primary=True,
                )
                session.add(ru_variant)
                await self._queue_review_task(
                    session,
                    molecule_id=molecule.id,
                    task_type=ReviewTaskType.RU_IUPAC_TRANSLATION,
                    payload={
                        "en_name": compound.iupac_name,
                        "proposed_ru": ru_alias,
                        "canonical_smiles": molecule.canonical_smiles,
                    },
                )
                await self._queue_review_task(
                    session,
                    molecule_id=molecule.id,
                    task_type=ReviewTaskType.GENERATE_DEPICTIONS,
                    payload={"canonical_smiles": molecule.canonical_smiles},
                )

                await self._upsert_card(
                    session,
                    molecule_id=molecule.id,
                    mode=Mode.IUPAC,
                    difficulty=int(molecule.descriptor_snapshot.get("difficulty", 1)),
                    topic_tags=molecule.descriptor_snapshot.get("topic_tags") or [],
                    is_published=False,
                    provenance={"source": "pubchem", "cid": compound.cid},
                )
                await self._refresh_publication_state(session, molecule_id=molecule.id)
                imported += 1

            await session.commit()
        return imported

    async def sync_primary_ru_iupac_variants(self) -> dict[str, int]:
        summary = {"checked": 0, "updated": 0}
        affected_molecules: set[str] = set()

        async with self.session_factory() as session:
            en_variants = (
                await session.scalars(
                    select(NamingVariant).where(
                        NamingVariant.mode == Mode.IUPAC.value,
                        NamingVariant.locale == Locale.EN.value,
                        NamingVariant.is_primary.is_(True),
                    )
                )
            ).all()

            for en_variant in en_variants:
                expected_ru = translate_iupac_en_to_ru(en_variant.answer_text)
                summary["checked"] += 1

                ru_primary = await session.scalar(
                    select(NamingVariant).where(
                        NamingVariant.molecule_id == en_variant.molecule_id,
                        NamingVariant.mode == Mode.IUPAC.value,
                        NamingVariant.locale == Locale.RU.value,
                        NamingVariant.is_primary.is_(True),
                    )
                )
                if ru_primary is not None and ru_primary.answer_text == expected_ru:
                    continue

                await self._upsert_naming_variant(
                    session,
                    molecule_id=en_variant.molecule_id,
                    mode=Mode.IUPAC,
                    locale=Locale.RU,
                    answer_text=expected_ru,
                    kind=NamingKind.CANONICAL,
                    review_status=ReviewStatus.APPROVED,
                    source_ref="sync:ru_iupac",
                    is_primary=True,
                    replace_existing_primary=True,
                )
                summary["updated"] += 1
                affected_molecules.add(en_variant.molecule_id)

            for molecule_id in affected_molecules:
                await self._refresh_publication_state(session, molecule_id=molecule_id)

            await session.commit()

        return summary

    async def apply_review_decisions(self, decisions: list[ReviewDecision]) -> dict[str, int]:
        summary = {"processed": 0, "approved": 0, "rejected": 0, "published_cards": 0}
        affected_molecules: set[str] = set()

        async with self.session_factory() as session:
            for decision in decisions:
                task = await session.get(ReviewTask, decision.task_id)
                if task is None:
                    raise LookupError(f"Review task not found: {decision.task_id}")

                action = decision.action.lower().strip()
                if action == "approve":
                    await self._approve_review_task(session, task, decision)
                    summary["approved"] += 1
                elif action == "reject":
                    await self._reject_review_task(session, task, decision)
                    summary["rejected"] += 1
                else:
                    raise ValueError(f"Unsupported review action: {decision.action}")

                if decision.notes:
                    task.notes = decision.notes
                task.status = ReviewTaskStatus.DONE.value
                summary["processed"] += 1
                if task.molecule_id:
                    affected_molecules.add(task.molecule_id)

            for molecule_id in affected_molecules:
                summary["published_cards"] += await self._refresh_publication_state(
                    session,
                    molecule_id=molecule_id,
                )

            await session.commit()

        return summary

    async def refresh_publication_state(self, molecule_id: str | None = None) -> int:
        async with self.session_factory() as session:
            changed = await self._refresh_publication_state(session, molecule_id=molecule_id)
            await session.commit()
            return changed

    async def ensure_depictions(self, session: AsyncSession, molecule: Molecule) -> bool:
        depictions = (
            await session.scalars(select(DepictionVariant).where(DepictionVariant.molecule_id == molecule.id))
        ).all()
        active_current = {
            (depiction.rotation_seed, depiction.flip_x): depiction
            for depiction in depictions
            if depiction.is_active
            and depiction.render_preset == self.depiction_service.render_preset
            and _path_exists(depiction.storage_path)
        }
        if len(active_current) == EXPECTED_VARIANT_COUNT and all(
            variant in active_current for variant in DEFAULT_VARIANTS
        ):
            return False

        current_depictions = {
            (depiction.rotation_seed, depiction.flip_x): depiction
            for depiction in depictions
            if depiction.render_preset == self.depiction_service.render_preset
        }
        for depiction in depictions:
            depiction.is_active = False

        for rotation, flip_x in DEFAULT_VARIANTS:
            artifact = self.depiction_service.build_artifact(molecule.canonical_smiles)
            path = self.depiction_service.persist_artifact(
                molecule.id,
                artifact,
                variant_label=f"rot{rotation}_flip{int(flip_x)}",
            )
            depiction = current_depictions.get((rotation, flip_x))
            if depiction is None:
                session.add(
                    DepictionVariant(
                        molecule_id=molecule.id,
                        render_preset=self.depiction_service.render_preset,
                        rotation_seed=rotation,
                        flip_x=flip_x,
                        storage_path=str(path),
                        image_hash=artifact.image_hash,
                        telegram_file_id=None,
                        is_active=True,
                    )
                )
                continue

            depiction.render_preset = self.depiction_service.render_preset
            depiction.storage_path = str(path)
            depiction.image_hash = artifact.image_hash
            depiction.telegram_file_id = None
            depiction.is_active = True

        await session.flush()
        logger.info(
            "depictions_regenerated",
            molecule_id=molecule.id,
            canonical_smiles=molecule.canonical_smiles,
            render_preset=self.depiction_service.render_preset,
            active_variants=EXPECTED_VARIANT_COUNT,
            previous_variants=len(depictions),
        )
        return True

    async def _refresh_publication_state(self, session: AsyncSession, *, molecule_id: str | None = None) -> int:
        cards_stmt = select(Card)
        if molecule_id:
            cards_stmt = cards_stmt.where(Card.molecule_id == molecule_id)
        cards = (await session.scalars(cards_stmt)).all()

        changed = 0
        affected_molecules = {card.molecule_id for card in cards}

        for card in cards:
            approved_locales = set(
                (
                    await session.scalars(
                        select(NamingVariant.locale).where(
                            NamingVariant.molecule_id == card.molecule_id,
                            NamingVariant.mode == card.mode,
                            NamingVariant.review_status == ReviewStatus.APPROVED.value,
                        )
                    )
                ).all()
            )
            has_depiction = bool(
                await session.scalar(
                    select(DepictionVariant.id).where(
                        DepictionVariant.molecule_id == card.molecule_id,
                        DepictionVariant.is_active.is_(True),
                    )
                )
            )
            should_publish = REQUIRED_LOCALES.issubset(approved_locales) and has_depiction
            if card.is_published != should_publish:
                card.is_published = should_publish
                changed += 1

        for affected_molecule_id in affected_molecules:
            molecule = await session.get(Molecule, affected_molecule_id)
            if molecule is None:
                continue
            molecule_cards = (await session.scalars(select(Card).where(Card.molecule_id == affected_molecule_id))).all()
            if not molecule_cards:
                molecule.publish_status = PublishStatus.DRAFT.value
                continue
            if all(card.is_published for card in molecule_cards):
                molecule.publish_status = PublishStatus.PUBLISHED.value
            else:
                molecule.publish_status = PublishStatus.REVIEW.value

        return changed

    async def _upsert_molecule(
        self,
        session: AsyncSession,
        *,
        canonical_smiles: str,
        molecular_formula: str | None,
        inchikey: str | None,
        provenance: dict[str, Any],
    ) -> Molecule:
        formula, descriptors = self.depiction_service.compute_descriptor_snapshot(canonical_smiles)
        resolved_formula = molecular_formula or formula

        molecule = None
        if inchikey:
            molecule = await session.scalar(select(Molecule).where(Molecule.inchikey == inchikey))
        if molecule is None:
            molecule = await session.scalar(select(Molecule).where(Molecule.canonical_smiles == canonical_smiles))

        if molecule is None:
            from rdkit import Chem

            rdkit_molecule = Chem.MolFromSmiles(canonical_smiles)
            if rdkit_molecule is None:
                raise ValueError(f"Invalid SMILES during ingest: {canonical_smiles}")
            computed_inchikey = Chem.inchi.MolToInchiKey(rdkit_molecule)
            molecule = Molecule(
                canonical_smiles=canonical_smiles,
                molecular_formula=resolved_formula,
                inchikey=inchikey or computed_inchikey,
                descriptor_snapshot=descriptors,
                provenance=provenance,
                publish_status=PublishStatus.DRAFT.value,
            )
            session.add(molecule)
            await session.flush()
            return molecule

        molecule.molecular_formula = resolved_formula
        molecule.descriptor_snapshot = descriptors
        molecule.provenance = provenance
        return molecule

    async def _upsert_naming_variant(
        self,
        session: AsyncSession,
        *,
        molecule_id: str,
        mode: Mode,
        locale: Locale,
        answer_text: str,
        kind: NamingKind,
        review_status: ReviewStatus,
        source_ref: str,
        is_primary: bool,
        replace_existing_primary: bool = False,
    ) -> NamingVariant:
        existing = await session.scalar(
            select(NamingVariant).where(
                NamingVariant.molecule_id == molecule_id,
                NamingVariant.mode == mode.value,
                NamingVariant.locale == locale.value,
                NamingVariant.answer_text == answer_text,
            )
        )
        if existing:
            existing.normalized_signature = build_token_signature(answer_text)
            existing.review_status = review_status.value
            existing.kind = kind.value
            existing.source_ref = source_ref
            existing.is_primary = is_primary
            if is_primary:
                await self._clear_primary_variant(
                    session,
                    molecule_id=molecule_id,
                    mode=mode,
                    locale=locale,
                    keep_variant_id=existing.id,
                    reject_demoted=replace_existing_primary,
                )
            return existing

        if replace_existing_primary and is_primary and kind is NamingKind.CANONICAL:
            existing_primary = await session.scalar(
                select(NamingVariant)
                .where(
                    NamingVariant.molecule_id == molecule_id,
                    NamingVariant.mode == mode.value,
                    NamingVariant.locale == locale.value,
                    NamingVariant.is_primary.is_(True),
                )
                .order_by(NamingVariant.created_at.asc())
            )
            if existing_primary is not None:
                existing_primary.answer_text = answer_text
                existing_primary.normalized_signature = build_token_signature(answer_text)
                existing_primary.review_status = review_status.value
                existing_primary.kind = kind.value
                existing_primary.source_ref = source_ref
                existing_primary.is_primary = True
                await self._clear_primary_variant(
                    session,
                    molecule_id=molecule_id,
                    mode=mode,
                    locale=locale,
                    keep_variant_id=existing_primary.id,
                    reject_demoted=True,
                )
                return existing_primary

        if is_primary:
            await self._clear_primary_variant(
                session,
                molecule_id=molecule_id,
                mode=mode,
                locale=locale,
                reject_demoted=replace_existing_primary,
            )

        variant = NamingVariant(
            molecule_id=molecule_id,
            mode=mode.value,
            locale=locale.value,
            kind=kind.value,
            answer_text=answer_text,
            normalized_signature=build_token_signature(answer_text),
            review_status=review_status.value,
            source_ref=source_ref,
            is_primary=is_primary,
        )
        session.add(variant)
        return variant

    async def _approve_review_task(
        self,
        session: AsyncSession,
        task: ReviewTask,
        decision: ReviewDecision,
    ) -> None:
        if task.molecule_id is None:
            raise ValueError(f"Review task {task.id} is missing molecule_id")
        mode, locale, suggested_answer = self._resolve_review_target(task, decision)
        answer_text = decision.answer_text or suggested_answer
        if answer_text is None:
            raise ValueError(f"Review task {task.id} does not have a proposed answer")

        if decision.mark_primary:
            await self._clear_primary_variant(
                session,
                molecule_id=task.molecule_id,
                mode=mode,
                locale=locale,
            )

        source_ref = f"review:{task.task_type}:{task.id}"
        await self._upsert_naming_variant(
            session,
            molecule_id=task.molecule_id,
            mode=mode,
            locale=locale,
            answer_text=answer_text,
            kind=NamingKind.CANONICAL if decision.mark_primary else NamingKind.ACCEPTED_ALIAS,
            review_status=ReviewStatus.APPROVED,
            source_ref=source_ref,
            is_primary=decision.mark_primary,
        )

    async def _reject_review_task(
        self,
        session: AsyncSession,
        task: ReviewTask,
        decision: ReviewDecision,
    ) -> None:
        if task.molecule_id is None:
            return
        mode, locale, suggested_answer = self._resolve_review_target(task, decision)
        answer_text = decision.answer_text or suggested_answer
        if answer_text is None:
            return

        variant = await session.scalar(
            select(NamingVariant).where(
                NamingVariant.molecule_id == task.molecule_id,
                NamingVariant.mode == mode.value,
                NamingVariant.locale == locale.value,
                NamingVariant.answer_text == answer_text,
            )
        )
        if variant is not None:
            variant.review_status = ReviewStatus.REJECTED.value
            variant.is_primary = False

    def _resolve_review_target(
        self,
        task: ReviewTask,
        decision: ReviewDecision,
    ) -> tuple[Mode, Locale, str | None]:
        if decision.mode:
            mode = Mode(decision.mode)
        elif task.task_type == ReviewTaskType.RATIONAL_ALIAS_REVIEW.value:
            mode = Mode.RATIONAL
        else:
            mode = Mode.IUPAC

        if decision.locale:
            locale = Locale(decision.locale)
        elif task.task_type == ReviewTaskType.RU_IUPAC_TRANSLATION.value:
            locale = Locale.RU
        else:
            locale = Locale(task.payload.get("locale", Locale.RU.value))

        suggested_answer = (
            task.payload.get("accepted_answer") or task.payload.get("proposed_ru") or task.payload.get("answer_text")
        )
        return mode, locale, suggested_answer

    async def _clear_primary_variant(
        self,
        session: AsyncSession,
        *,
        molecule_id: str | None,
        mode: Mode,
        locale: Locale,
        keep_variant_id: str | None = None,
        reject_demoted: bool = False,
    ) -> None:
        if molecule_id is None:
            return
        variants = (
            await session.scalars(
                select(NamingVariant).where(
                    NamingVariant.molecule_id == molecule_id,
                    NamingVariant.mode == mode.value,
                    NamingVariant.locale == locale.value,
                    NamingVariant.is_primary.is_(True),
                )
            )
        ).all()
        for variant in variants:
            if keep_variant_id is not None and variant.id == keep_variant_id:
                continue
            variant.is_primary = False
            if reject_demoted:
                variant.review_status = ReviewStatus.REJECTED.value
                variant.kind = NamingKind.ACCEPTED_ALIAS.value
            elif variant.review_status == ReviewStatus.APPROVED.value:
                variant.kind = NamingKind.ACCEPTED_ALIAS.value

    async def _upsert_card(
        self,
        session: AsyncSession,
        *,
        molecule_id: str,
        mode: Mode,
        difficulty: int,
        topic_tags: list[str],
        is_published: bool,
        provenance: dict[str, Any],
    ) -> Card:
        existing = await session.scalar(select(Card).where(Card.molecule_id == molecule_id, Card.mode == mode.value))
        if existing:
            existing.difficulty = difficulty
            existing.topic_tags = sorted(set(topic_tags))
            existing.is_published = is_published
            existing.enabled_hints = DEFAULT_HINTS
            existing.provenance = provenance
            return existing

        card = Card(
            molecule_id=molecule_id,
            mode=mode.value,
            topic_tags=sorted(set(topic_tags)),
            difficulty=difficulty,
            enabled_hints=DEFAULT_HINTS,
            is_published=is_published,
            provenance=provenance,
        )
        session.add(card)
        return card

    async def _queue_review_task(
        self,
        session: AsyncSession,
        *,
        molecule_id: str,
        task_type: ReviewTaskType,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            ReviewTask(
                molecule_id=molecule_id,
                task_type=task_type.value,
                payload=payload,
                status=ReviewTaskStatus.PENDING.value,
            )
        )

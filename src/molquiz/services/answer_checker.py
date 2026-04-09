from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from molquiz.db.models import ErrorCategory, Locale, Mode, NamingVariant
from molquiz.services.normalization import normalize_answer, tokenize_answer
from molquiz.services.opsin import OpsinClient

KNOWN_MULTIPLIERS = {"di", "tri", "tetra", "penta", "ди", "три", "тетра", "пента"}
KNOWN_SUFFIXES = {
    "ane",
    "ene",
    "yne",
    "ol",
    "one",
    "al",
    "amine",
    "ан",
    "ен",
    "ин",
    "ол",
    "он",
    "аль",
    "амин",
}
KNOWN_ROOTS = {
    "meth",
    "eth",
    "prop",
    "but",
    "pent",
    "hex",
    "hept",
    "oct",
    "non",
    "dec",
    "мет",
    "эт",
    "проп",
    "бут",
    "пент",
    "гекс",
    "гепт",
    "окт",
    "нон",
    "дек",
}


@dataclass(slots=True)
class ValidationOutcome:
    accepted: bool
    normalized_answer: str
    signature: str
    locale: Locale | None
    matched_variant_id: str | None = None
    error_category: ErrorCategory | None = None
    explanation: str | None = None


class AnswerChecker:
    def __init__(self, opsin_client: OpsinClient) -> None:
        self.opsin_client = opsin_client

    async def validate(
        self,
        *,
        mode: Mode,
        molecule_inchikey: str,
        naming_variants: list[NamingVariant],
        raw_answer: str,
    ) -> ValidationOutcome:
        normalized = normalize_answer(raw_answer)
        approved = [variant for variant in naming_variants if variant.review_status == "approved"]

        for variant in approved:
            if normalized.signature == variant.normalized_signature:
                return ValidationOutcome(
                    accepted=True,
                    normalized_answer=normalized.normalized,
                    signature=normalized.signature,
                    locale=Locale(variant.locale),
                    matched_variant_id=variant.id,
                    explanation="Точное совпадение с проверенным алиасом.",
                )

        if mode is Mode.IUPAC and normalized.locale_hint in {Locale.EN, None}:
            opsin_result = await self.opsin_client.parse_name(raw_answer)
            if opsin_result and opsin_result.stdinchikey == molecule_inchikey:
                return ValidationOutcome(
                    accepted=True,
                    normalized_answer=normalized.normalized,
                    signature=normalized.signature,
                    locale=Locale.EN,
                    explanation="Ответ принят по совпадению структуры через OPSIN.",
                )

        canonical = self._pick_canonical_variant(approved, normalized.locale_hint)
        category = self._classify_error(
            normalized.signature,
            canonical.normalized_signature if canonical else "",
        )
        return ValidationOutcome(
            accepted=False,
            normalized_answer=normalized.normalized,
            signature=normalized.signature,
            locale=normalized.locale_hint,
            error_category=category,
            explanation=self._error_explanation(category),
        )

    def _pick_canonical_variant(
        self,
        naming_variants: list[NamingVariant],
        locale_hint: Locale | None,
    ) -> NamingVariant | None:
        if locale_hint:
            for variant in naming_variants:
                if variant.is_primary and variant.locale == locale_hint.value:
                    return variant
        for variant in naming_variants:
            if variant.is_primary:
                return variant
        return naming_variants[0] if naming_variants else None

    def _classify_error(self, candidate_signature: str, canonical_signature: str) -> ErrorCategory:
        candidate_tokens = tokenize_answer(candidate_signature.replace("|", " "))
        canonical_tokens = tokenize_answer(canonical_signature.replace("|", " "))

        candidate_words = [token for token in candidate_tokens if token.isalpha()]
        canonical_words = [token for token in canonical_tokens if token.isalpha()]
        candidate_numbers = [token for token in candidate_tokens if token.isdigit()]
        canonical_numbers = [token for token in canonical_tokens if token.isdigit()]

        if candidate_words == canonical_words and candidate_numbers != canonical_numbers:
            return ErrorCategory.LOCANTS

        if sorted(candidate_words) == sorted(canonical_words) and candidate_words != canonical_words:
            return ErrorCategory.SUBSTITUENT_ORDER

        if any(token in KNOWN_MULTIPLIERS for token in candidate_words + canonical_words):
            if set(candidate_words) != set(canonical_words):
                return ErrorCategory.MULTIPLICATIVE_PREFIX

        if any(token in KNOWN_SUFFIXES for token in candidate_words + canonical_words):
            if candidate_words[-1:] != canonical_words[-1:]:
                return ErrorCategory.SUFFIX_MAIN_FUNCTION

        if any(token in KNOWN_ROOTS for token in candidate_words + canonical_words):
            matcher = SequenceMatcher(a=" ".join(candidate_words), b=" ".join(canonical_words))
            if matcher.ratio() < 0.6:
                return ErrorCategory.PARENT_CHAIN

        return ErrorCategory.UNSUPPORTED_ALTERNATIVE_FORM

    def _error_explanation(self, category: ErrorCategory) -> str:
        explanations = {
            ErrorCategory.LOCANTS: "Похоже, ошибка в нумерации локантов.",
            ErrorCategory.SUBSTITUENT_ORDER: "Похоже, нарушен порядок заместителей в названии.",
            ErrorCategory.MULTIPLICATIVE_PREFIX: "Похоже, ошибка в кратной приставке.",
            ErrorCategory.SUFFIX_MAIN_FUNCTION: ("Похоже, выбрана неверная главная функция или суффикс."),
            ErrorCategory.PARENT_CHAIN: "Похоже, неверно выбрана или названа главная цепь.",
            ErrorCategory.UNSUPPORTED_ALTERNATIVE_FORM: ("Ответ не совпал с проверенными формами названия."),
        }
        return explanations[category]

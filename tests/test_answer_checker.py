from types import SimpleNamespace

import pytest

from molquiz.db.models import ErrorCategory, Locale, Mode, NamingVariant
from molquiz.services.answer_checker import AnswerChecker
from molquiz.services.normalization import build_token_signature


class FakeOpsinClient:
    async def parse_name(self, name: str):
        if name == "2-methylpropane":
            return SimpleNamespace(stdinchikey="MATCH")
        return None


@pytest.mark.asyncio
async def test_answer_checker_accepts_exact_alias() -> None:
    checker = AnswerChecker(FakeOpsinClient())
    outcome = await checker.validate(
        mode=Mode.IUPAC,
        molecule_inchikey="NOPE",
        naming_variants=[
            NamingVariant(
                id="1",
                molecule_id="m1",
                mode="iupac",
                locale="ru",
                kind="canonical",
                answer_text="2-метилпропан",
                normalized_signature=build_token_signature("2-метилпропан"),
                review_status="approved",
                source_ref="test",
                is_primary=True,
            )
        ],
        raw_answer="2-метилпропан",
    )
    assert outcome.accepted is True
    assert outcome.locale == Locale.RU


@pytest.mark.asyncio
async def test_answer_checker_accepts_opsin_match() -> None:
    checker = AnswerChecker(FakeOpsinClient())
    outcome = await checker.validate(
        mode=Mode.IUPAC,
        molecule_inchikey="MATCH",
        naming_variants=[],
        raw_answer="2-methylpropane",
    )
    assert outcome.accepted is True
    assert outcome.locale == Locale.EN


@pytest.mark.asyncio
async def test_answer_checker_classifies_locant_error() -> None:
    checker = AnswerChecker(FakeOpsinClient())
    outcome = await checker.validate(
        mode=Mode.IUPAC,
        molecule_inchikey="NOPE",
        naming_variants=[
            NamingVariant(
                id="1",
                molecule_id="m1",
                mode="iupac",
                locale="en",
                kind="canonical",
                answer_text="2-methylpropane",
                normalized_signature=build_token_signature("2-methylpropane"),
                review_status="approved",
                source_ref="test",
                is_primary=True,
            )
        ],
        raw_answer="3-methylpropane",
    )
    assert outcome.accepted is False
    assert outcome.error_category == ErrorCategory.LOCANTS

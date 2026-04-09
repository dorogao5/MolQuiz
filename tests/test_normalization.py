from molquiz.db.models import Locale
from molquiz.services.normalization import build_token_signature, normalize_answer


def test_normalize_answer_cleans_spacing_and_dashes() -> None:
    normalized = normalize_answer("  2 – methyl propane  ")
    assert normalized.normalized == "2-methyl propane"
    assert normalized.locale_hint == Locale.EN


def test_signature_handles_latin_cyrillic_lookalikes() -> None:
    left = build_token_signature("cyclohexane")
    right = build_token_signature("сyclohexane")
    assert left == right

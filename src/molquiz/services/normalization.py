from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from molquiz.db.models import Locale

_DASHES = re.compile(r"[‐‑‒–—−]+")
_SPACES = re.compile(r"\s+")
_SEPARATOR_SPACES = re.compile(r"\s*([,()\[\]-])\s*")
_CYRILLIC_RE = re.compile(r"[а-яё]")
_LATIN_RE = re.compile(r"[a-z]")
_TOKEN_RE = re.compile(r"\d+|[a-zа-яё]+|[(),\[\]-]")

_LOOKALIKE_MAP = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "ё": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "к": "k",
        "м": "m",
        "т": "t",
        "в": "b",
        "н": "h",
        "А": "a",
        "В": "b",
        "Е": "e",
        "К": "k",
        "М": "m",
        "Н": "h",
        "О": "o",
        "Р": "p",
        "С": "c",
        "Т": "t",
        "У": "y",
        "Х": "x",
    }
)


@dataclass(slots=True)
class NormalizedAnswer:
    normalized: str
    signature: str
    locale_hint: Locale | None


def detect_locale(text: str) -> Locale | None:
    has_cyrillic = bool(_CYRILLIC_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    if has_cyrillic and not has_latin:
        return Locale.RU
    if has_latin and not has_cyrillic:
        return Locale.EN
    return None


def normalize_answer_text(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", text).strip().lower()
    cleaned = cleaned.replace(";", ",")
    cleaned = _DASHES.sub("-", cleaned)
    cleaned = _SEPARATOR_SPACES.sub(r"\1", cleaned)
    cleaned = _SPACES.sub(" ", cleaned)
    return cleaned.strip()


def tokenize_answer(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def build_token_signature(text: str) -> str:
    normalized = normalize_answer_text(text)
    collapsed = normalized.translate(_LOOKALIKE_MAP)
    tokens = tokenize_answer(collapsed)
    return "|".join(tokens)


def normalize_answer(text: str) -> NormalizedAnswer:
    normalized = normalize_answer_text(text)
    return NormalizedAnswer(
        normalized=normalized,
        signature=build_token_signature(normalized),
        locale_hint=detect_locale(normalized),
    )

from __future__ import annotations

import re

_PHRASE_REPLACEMENTS: list[tuple[str, str]] = [
    ("benzoic acid", "бензойная кислота"),
    ("benzaldehyde", "бензальдегид"),
    ("benzonitrile", "бензонитрил"),
    ("benzene", "бензол"),
    ("phenol", "фенол"),
    ("aniline", "анилин"),
    ("oic acid", "овая кислота"),
    ("carboxylic acid", "карбоновая кислота"),
]

_TOKEN_REPLACEMENTS: list[tuple[str, str]] = [
    ("cyclo", "цикло"),
    ("methoxy", "метокси"),
    ("ethoxy", "этокси"),
    ("propoxy", "пропокси"),
    ("butoxy", "бутокси"),
    ("hydroxy", "гидрокси"),
    ("amino", "амино"),
    ("nitro", "нитро"),
    ("fluoro", "фторо"),
    ("chloro", "хлоро"),
    ("bromo", "бромо"),
    ("iodo", "йодо"),
    ("phenyl", "фенил"),
    ("methyl", "метил"),
    ("ethyl", "этил"),
    ("propyl", "пропил"),
    ("butyl", "бутил"),
    ("pentyl", "пентил"),
    ("hexyl", "гексил"),
    ("heptyl", "гептил"),
    ("octyl", "октил"),
    ("nonyl", "нонил"),
    ("decyl", "децил"),
    ("trimethyl", "триметил"),
    ("dimethyl", "диметил"),
    ("triethyl", "триэтил"),
    ("diethyl", "диэтил"),
    ("tripropyl", "трипропил"),
    ("dipropyl", "дипропил"),
    ("tetra", "тетра"),
    ("tri", "три"),
    ("di", "ди"),
    ("methane", "метан"),
    ("ethane", "этан"),
    ("propane", "пропан"),
    ("butane", "бутан"),
    ("pentane", "пентан"),
    ("hexane", "гексан"),
    ("heptane", "гептан"),
    ("octane", "октан"),
    ("nonane", "нонан"),
    ("decane", "декан"),
    ("methan", "метан"),
    ("ethan", "этан"),
    ("propan", "пропан"),
    ("butan", "бутан"),
    ("pentan", "пентан"),
    ("hexan", "гексан"),
    ("heptan", "гептан"),
    ("octan", "октан"),
    ("nonan", "нонан"),
    ("decan", "декан"),
    ("meth", "мет"),
    ("eth", "эт"),
    ("prop", "проп"),
    ("but", "бут"),
    ("pent", "пент"),
    ("hex", "гекс"),
    ("hept", "гепт"),
    ("oct", "окт"),
    ("non", "нон"),
    ("dec", "дек"),
    ("nitrile", "нитрил"),
    ("amide", "амид"),
    ("amine", "амин"),
    ("oate", "оат"),
    ("ate", "ат"),
    ("yne", "ин"),
    ("ene", "ен"),
    ("one", "он"),
    ("ol", "ол"),
    ("al", "аль"),
]

_SPACING_RE = re.compile(r"\s+")
_LOCANT_RE = re.compile(r"^\d+(?:,\d+)*$")
_SORT_MULTIPLIERS = ("тетра", "три", "ди")
_BASE_SUBSTITUENT_PREFIXES = (
    "метокси",
    "этокси",
    "пропокси",
    "бутокси",
    "гидрокси",
    "амино",
    "нитро",
    "фторо",
    "хлоро",
    "бромо",
    "йодо",
    "фенил",
    "метил",
    "этил",
    "пропил",
    "бутил",
    "пентил",
    "гексил",
    "гептил",
    "октил",
    "нонил",
    "децил",
)
_MULTIPLIER_PREFIXES = ("ди", "три", "тетра")
_COMPOSITE_LEAD_PREFIXES = (
    "гидрокси",
    "амино",
    "нитро",
    "фторо",
    "хлоро",
    "бромо",
    "йодо",
    "метокси",
    "этокси",
    "пропокси",
    "бутокси",
    "метил",
    "этил",
    "пропил",
    "бутил",
    "фенил",
)
_COMPOSITE_TAIL_PREFIXES = ("амино", "метил", "этил", "пропил", "бутил")
_CYCLO_SUBSTITUENT_PREFIXES = tuple(
    f"цикло{prefix}"
    for prefix in ("метил", "этил", "пропил", "бутил", "пентил", "гексил", "гептил", "октил")
)
_SUBSTITUENT_PREFIXES = tuple(
    sorted(
        {
            *_BASE_SUBSTITUENT_PREFIXES,
            *_CYCLO_SUBSTITUENT_PREFIXES,
            *(
                f"{multiplier}{prefix}"
                for multiplier in _MULTIPLIER_PREFIXES
                for prefix in _BASE_SUBSTITUENT_PREFIXES
            ),
            *(
                f"{lead}{tail}"
                for lead in _COMPOSITE_LEAD_PREFIXES
                for tail in _COMPOSITE_TAIL_PREFIXES
            ),
            *(
                f"{multiplier}{lead}{tail}"
                for multiplier in _MULTIPLIER_PREFIXES
                for lead in _COMPOSITE_LEAD_PREFIXES
                for tail in _COMPOSITE_TAIL_PREFIXES
            ),
        },
        key=len,
        reverse=True,
    )
)


def _split_top_level_hyphenated(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0

    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1

        if char == "-" and depth == 0:
            parts.append("".join(current))
            current = []
            continue

        current.append(char)

    parts.append("".join(current))
    return parts


def _extract_parenthesized_prefix(part: str) -> tuple[str, str] | None:
    if not part.startswith("("):
        return None

    depth = 0
    for index, char in enumerate(part):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return part[: index + 1], part[index + 1 :]
    return None


def _extract_substituent_prefix(part: str) -> tuple[str, str] | None:
    parenthesized = _extract_parenthesized_prefix(part)
    if parenthesized is not None:
        return parenthesized

    for prefix in _SUBSTITUENT_PREFIXES:
        if part.startswith(prefix):
            return prefix, part[len(prefix) :]
    return None


def _sort_key(substituent: str) -> str:
    sample = substituent.strip("()")
    sample = re.sub(r"^\d+(?:,\d+)*-", "", sample)
    sample = re.sub(r"[^а-яё-]", "", sample.lower())
    for prefix in _SORT_MULTIPLIERS:
        if sample.startswith(prefix) and len(sample) > len(prefix):
            sample = sample[len(prefix) :]
            break
    return sample.replace("ё", "е")


def _reorder_ru_substituents(name: str) -> str:
    parts = _split_top_level_hyphenated(name)
    if len(parts) < 4:
        return name

    substituents: list[tuple[str, str]] = []
    index = 0
    parent_tail = ""

    while index + 1 < len(parts):
        locant = parts[index]
        if not _LOCANT_RE.fullmatch(locant):
            break

        extracted = _extract_substituent_prefix(parts[index + 1])
        if extracted is None:
            break

        substituent, remainder = extracted
        substituents.append((locant, substituent))
        index += 2

        if remainder:
            parent_tail = remainder
            if index < len(parts):
                parent_tail = f"{parent_tail}-{'-'.join(parts[index:])}"
            break

    if len(substituents) < 2 or not parent_tail:
        return name

    ordered = sorted(substituents, key=lambda item: (_sort_key(item[1]), item[0]))
    prefix = "-".join(f"{locant}-{substituent}" for locant, substituent in ordered[:-1])
    tail = f"{ordered[-1][0]}-{ordered[-1][1]}{parent_tail}"
    return f"{prefix}-{tail}" if prefix else tail


def translate_iupac_en_to_ru(name: str) -> str:
    translated = name.lower().strip()

    for source, target in _PHRASE_REPLACEMENTS:
        translated = translated.replace(source, target)

    for source, target in sorted(_TOKEN_REPLACEMENTS, key=lambda item: len(item[0]), reverse=True):
        translated = translated.replace(source, target)

    translated = _SPACING_RE.sub(" ", translated).strip()
    return _reorder_ru_substituents(translated)


def looks_like_supported_ru_iupac(name: str) -> bool:
    translated = translate_iupac_en_to_ru(name)
    return not bool(re.search(r"[a-z]", translated))

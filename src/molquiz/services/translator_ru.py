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


def translate_iupac_en_to_ru(name: str) -> str:
    translated = name.lower().strip()

    for source, target in _PHRASE_REPLACEMENTS:
        translated = translated.replace(source, target)

    for source, target in sorted(_TOKEN_REPLACEMENTS, key=lambda item: len(item[0]), reverse=True):
        translated = translated.replace(source, target)

    translated = _SPACING_RE.sub(" ", translated).strip()
    return translated


def looks_like_supported_ru_iupac(name: str) -> bool:
    translated = translate_iupac_en_to_ru(name)
    return not bool(re.search(r"[a-z]", translated))

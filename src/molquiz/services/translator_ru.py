from __future__ import annotations

import re

_PHRASE_REPLACEMENTS: list[tuple[str, str]] = [
    ("benzoic acid", "бензойная кислота"),
    ("oic acid", "овая кислота"),
    ("carboxylic acid", "карбоновая кислота"),
]

_TOKEN_REPLACEMENTS: list[tuple[str, str]] = [
    ("methoxy", "метокси"),
    ("ethoxy", "этокси"),
    ("propoxy", "пропокси"),
    ("hydroxy", "гидрокси"),
    ("amino", "амино"),
    ("nitro", "нитро"),
    ("chloro", "хлоро"),
    ("bromo", "бромо"),
    ("fluoro", "фторо"),
    ("iodo", "йодо"),
    ("phenyl", "фенил"),
    ("benz", "бенз"),
    ("cyclo", "цикло"),
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
    ("ane", "ан"),
    ("ene", "ен"),
    ("yne", "ин"),
    ("ol", "ол"),
    ("one", "он"),
    ("al", "аль"),
    ("amine", "амин"),
    ("amide", "амид"),
    ("ate", "ат"),
]

_DIGIT_SPACING = re.compile(r"\s+")


def translate_iupac_en_to_ru(name: str) -> str:
    translated = name.lower()
    for source, target in _PHRASE_REPLACEMENTS:
        translated = translated.replace(source, target)

    tokens = re.split(r"([0-9,\-()\[\] ])", translated)
    converted: list[str] = []
    for token in tokens:
        if not token or token.isspace():
            converted.append(token)
            continue
        if token.isdigit() or all(ch in ",-()[]" for ch in token):
            converted.append(token)
            continue

        current = token
        for source, target in _TOKEN_REPLACEMENTS:
            current = current.replace(source, target)
        converted.append(current)

    result = "".join(converted)
    result = _DIGIT_SPACING.sub(" ", result).strip()
    return result

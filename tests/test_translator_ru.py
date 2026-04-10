from molquiz.services.translator_ru import looks_like_supported_ru_iupac, translate_iupac_en_to_ru


def test_translate_iupac_en_to_ru_for_simple_name() -> None:
    assert translate_iupac_en_to_ru("2-methylpropane") == "2-метилпропан"


def test_translate_keeps_common_functional_fragments() -> None:
    translated = translate_iupac_en_to_ru("2-methylpropan-1-ol")
    assert "метил" in translated
    assert translated.endswith("ол")


def test_translate_acid_and_aromatic_name() -> None:
    assert translate_iupac_en_to_ru("3-methylbutanoic acid") == "3-метилбутановая кислота"
    assert translate_iupac_en_to_ru("1-ethyl-3-methylbenzene") == "3-метил-1-этилбензол"


def test_translate_reorders_substituents_for_ru_alphabet() -> None:
    assert translate_iupac_en_to_ru("2-ethyl-4-methylpentan-1-ol") == "4-метил-2-этилпентан-1-ол"


def test_supported_ru_iupac_filter_rejects_untranslated_fragments() -> None:
    assert looks_like_supported_ru_iupac("2-methylpropane") is True
    assert looks_like_supported_ru_iupac("9-ethylpurin-6-amine") is False

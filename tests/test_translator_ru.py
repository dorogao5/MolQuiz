from molquiz.services.translator_ru import translate_iupac_en_to_ru


def test_translate_iupac_en_to_ru_for_simple_name() -> None:
    assert translate_iupac_en_to_ru("2-methylpropane") == "2-метилпропан"


def test_translate_keeps_common_functional_fragments() -> None:
    translated = translate_iupac_en_to_ru("2-methylpropan-1-ol")
    assert "метил" in translated
    assert translated.endswith("ол")

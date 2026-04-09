import json

from molquiz.services.qwen import QwenHeadlessClient


def test_qwen_client_parses_direct_json_payload() -> None:
    client = QwenHeadlessClient(None)
    suggestion = client._parse_output(
        '{"title":"aliases","suggestions":["2-метилпропан","изобутан"]}'
    )

    assert suggestion is not None
    assert suggestion.title == "aliases"
    assert suggestion.suggestions == ["2-метилпропан", "изобутан"]


def test_qwen_client_parses_qwen_json_output_wrapper() -> None:
    client = QwenHeadlessClient(None)
    raw = json.dumps(
        [
            {"type": "message", "role": "assistant", "result": '{"title":"aliases","suggestions":["изобутан"]}'}
        ]
    )

    suggestion = client._parse_output(raw)

    assert suggestion is not None
    assert suggestion.title == "aliases"
    assert suggestion.suggestions == ["изобутан"]


def test_qwen_client_falls_back_to_plain_text_lines() -> None:
    client = QwenHeadlessClient(None)
    suggestion = client._parse_output("- изобутан\n- 2-метилпропан\n")

    assert suggestion is not None
    assert suggestion.title == "qwen_aliases"
    assert suggestion.suggestions == ["изобутан", "2-метилпропан"]

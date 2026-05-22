"""extract_json must survive whatever shape the model emits."""

import pytest

from aegis.utils.json_io import extract_json


@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Here you go:\n\n{"a": 1}\n\nLet me know!', {"a": 1}),
        ("  \n[1, 2, 3]", [1, 2, 3]),
        ('```\n{"x": [1, 2]}\n```', {"x": [1, 2]}),
        ("not json at all", None),
        ("", None),
    ],
)
def test_extract(text, expected):
    assert extract_json(text) == expected


def test_handles_nested_braces():
    s = 'prefix {"outer": {"inner": [1, 2, {"k": "v"}]}, "n": 5} suffix'
    assert extract_json(s) == {"outer": {"inner": [1, 2, {"k": "v"}]}, "n": 5}


def test_handles_strings_with_braces():
    s = '{"text": "a {brace} in a string", "ok": true}'
    assert extract_json(s) == {"text": "a {brace} in a string", "ok": True}

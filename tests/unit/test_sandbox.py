"""Sandbox security and load-harness tests.

The sandbox is the security-critical piece. These tests are deliberately
adversarial — every "bad" snippet must raise SandboxError, and every "good"
snippet must load and round-trip an output value.
"""

from __future__ import annotations

import pytest

from aegis.synthesize.sandbox import SandboxError, load_harness, validate_source

GOOD_MIN = """\
from pydantic import BaseModel, Field

class Output(BaseModel):
    value: int = Field(ge=0)

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    return []
"""

GOOD_WITH_VERIFIER = """\
import re
from pydantic import BaseModel, Field

class Output(BaseModel):
    url: str = Field(min_length=1)

ALLOWED_TOOLS: list[str] = ["fetch_url"]

def verify(output: Output) -> list[str]:
    if not re.match(r"https?://", output.url):
        return ["malformed url"]
    return []
"""

BAD_OS = """\
import os
class Output: pass
def verify(o): return []
ALLOWED_TOOLS = []
"""

BAD_EVAL = """\
class Output: pass
ALLOWED_TOOLS = []
def verify(o):
    return eval("[]")
"""

BAD_DUNDER = """\
class Output: pass
ALLOWED_TOOLS = []
def verify(o):
    return o.__class__.__bases__
"""

BAD_GETATTR = """\
class Output: pass
ALLOWED_TOOLS = []
def verify(o):
    return getattr(o, "__class__")
"""

BAD_SUBPROCESS_IMPORT = """\
import subprocess
class Output: pass
ALLOWED_TOOLS = []
def verify(o): return []
"""

BAD_NO_OUTPUT = """\
ALLOWED_TOOLS = []
def verify(o): return []
"""

BAD_NO_VERIFY = """\
from pydantic import BaseModel
class Output(BaseModel):
    x: int = 0
ALLOWED_TOOLS = []
"""


class TestValidateSource:
    def test_minimal_ok(self):
        validate_source(GOOD_MIN)

    def test_with_verifier_ok(self):
        validate_source(GOOD_WITH_VERIFIER)

    @pytest.mark.parametrize(
        "src",
        [BAD_OS, BAD_EVAL, BAD_DUNDER, BAD_GETATTR, BAD_SUBPROCESS_IMPORT],
        ids=["os", "eval", "dunder", "getattr", "subprocess"],
    )
    def test_rejects_dangerous(self, src: str):
        with pytest.raises(SandboxError):
            validate_source(src)


class TestLoadHarness:
    def test_loads_good_module(self):
        h = load_harness(GOOD_MIN)
        assert h.allowed_tools == []
        assert callable(h.verify_fn)
        out = h.validate_output({"value": 7})
        assert h.verify_fn(out) == []

    def test_loads_with_url_verifier(self):
        h = load_harness(GOOD_WITH_VERIFIER)
        out = h.validate_output({"url": "https://example.com/x"})
        assert h.verify_fn(out) == []
        bad = h.validate_output({"url": "not-a-url"})
        assert h.verify_fn(bad) == ["malformed url"]

    def test_rejects_missing_output(self):
        with pytest.raises(SandboxError, match="Output"):
            load_harness(BAD_NO_OUTPUT)

    def test_rejects_missing_verify(self):
        with pytest.raises(SandboxError, match="verify"):
            load_harness(BAD_NO_VERIFY)

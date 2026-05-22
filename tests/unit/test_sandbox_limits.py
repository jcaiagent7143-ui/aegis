"""Wall-clock and memory limits on the sandboxed verify() execution."""

from __future__ import annotations

import sys
import time

import pytest

from aegis.synthesize.sandbox import SandboxTimeout, load_harness, run_with_limits

SLOW_HARNESS = """\
from pydantic import BaseModel

class Output(BaseModel):
    value: int = 0

ALLOWED_TOOLS: list[str] = []

def verify(output: Output) -> list[str]:
    # Tight CPU loop — should be killed by the wall-clock timer
    i = 0
    while True:
        i += 1
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only timer")
def test_run_with_limits_enforces_timeout():
    def slow():
        for _ in range(10_000_000_000):
            pass

    with pytest.raises(SandboxTimeout):
        run_with_limits(slow, timeout_s=0.2, memory_mb=None)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only timer")
def test_call_verify_times_out_on_infinite_loop():
    h = load_harness(SLOW_HARNESS)
    out = h.output_model.model_validate({"value": 1})
    with pytest.raises(SandboxTimeout):
        h.call_verify(out, timeout_s=0.2, memory_mb=None)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only timer")
def test_run_with_limits_returns_normal_results():
    start = time.perf_counter()
    result = run_with_limits(lambda: sum(range(100)), timeout_s=1.0, memory_mb=None)
    assert result == 4950
    assert time.perf_counter() - start < 0.5


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only timer")
def test_run_with_limits_restores_handler():
    import signal

    before = signal.getsignal(signal.SIGALRM)
    run_with_limits(lambda: 1, timeout_s=0.5, memory_mb=None)
    after = signal.getsignal(signal.SIGALRM)
    assert before == after

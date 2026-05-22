# What is a dynamic harness?

## Definition

A **harness** is the runtime scaffolding around an LLM that turns it into a useful agent. Concretely, a harness usually defines:

- the **tool registry** the model may call,
- the **output schema** it must conform to,
- **input/argument validators** for tool calls,
- **per-step verifiers** that re-check intermediate results,
- a **retry or repair policy** for malformed outputs,
- a **sandbox** for any code the model produces or executes.

A **static harness** is what every agent framework today gives you: you author all of this once, hardcoded, and it applies to every task the agent runs.

A **dynamic harness** is generated per-task, based on what the goal actually requires. The agent reasons about *what could go wrong on this specific goal*, then emits a tailored harness designed to catch those failures.

## Why it matters

Consider two goals:

| Goal | What can go wrong |
|---|---|
| *"Summarize this PDF"* | Schema drift, leaked reasoning. Low stakes. |
| *"Refactor `auth.py` to async"* | Breaking change, untested edit, syntax errors, hidden behavior change. High stakes. |

A static harness either:

- under-protects the second goal (a fast, light harness for everything), or
- over-protects the first (heavyweight verification for a one-line task).

A dynamic harness reads the goal, picks the right defenses, and stops there.

## What Aegis emits

For a citation-heavy research goal, the synthesized harness looks like:

```python
from pydantic import BaseModel, Field
from aegis.tools import web_search, fetch_url

class Citation(BaseModel):
    title: str
    url: str = Field(pattern=r"https?://.+")

class Output(BaseModel):
    citations: list[Citation] = Field(min_length=3, max_length=5)
    summary: str

ALLOWED_TOOLS = [web_search, fetch_url]   # no shell, no code-exec

def verify(output: Output) -> list[str]:
    failures = []
    for c in output.citations:
        if tool("fetch_url", url=c.url)["status_code"] != 200:
            failures.append(f"{c.title}: URL does not resolve")
    return failures
```

For a CSV arithmetic goal, it looks completely different:

```python
from pydantic import BaseModel, Field
from typing import Literal

class Output(BaseModel):
    product: str
    revenue: float = Field(ge=0)
    method: Literal["sum", "max"]

ALLOWED_TOOLS = ["read_file", "run_python_snippet"]

def verify(output: Output) -> list[str]:
    csv = tool("read_file", path="sales.csv")
    recomputed = tool("run_python_snippet", code=f"""
import csv, io
rows = list(csv.DictReader(io.StringIO({csv!r})))
result = max(rows, key=lambda r: float(r["revenue"]))["product"]
""")
    return [] if recomputed == output.product else [f"recompute disagrees: {recomputed}"]
```

Same framework, two very different generated harnesses — because the failure modes are different.

## Caveats and bounds

- Aegis isn't magic. It can only catch failures it knows how to verify. The risk catalog grows over time and via community contributions.
- The synthesized verifier is itself written by an LLM, so it can have bugs. The sandbox prevents catastrophic ones; the test suite catches the rest.
- Dynamic harnesses cost extra tokens at the front of every run (analyze + assess + synthesize). The memory cache amortizes this for repeated/similar goals.

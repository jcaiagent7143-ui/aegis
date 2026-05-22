# Aegis

**Dynamic, on-the-fly generated harnesses for AI agents.**

The agent designs its own guardrails before executing the task.

```python
import asyncio
from aegis import Aegis

async def main():
    aegis = Aegis()  # auto-detects provider from env
    result = await aegis.run("Find 3 OSS agent frameworks and verify each URL")
    print(result.value)              # the answer
    print(result.harness_code)       # the Python Aegis generated
    print(result.audit.risks)        # what could have gone wrong

asyncio.run(main())
```

## Why Aegis

Every agent framework today makes you hand-write the harness: tool list, output schema, validators, retry policy, sandbox rules. That harness is static — it applies the same guardrails to "summarize this PDF" as to "execute trades on my brokerage account."

Aegis flips this. Give it a goal. It:

1. **Analyzes** the goal and infers the expected output shape.
2. **Assesses** failure modes against a catalog of ~30 known risks (citation hallucination, arithmetic drift, prompt injection from fetched content, …).
3. **Synthesizes** real Python code — Pydantic schemas, tool guards, verifiers — as a custom runtime harness for *this* task.
4. **Executes** the agent inside that harness, sandboxed and audited.
5. **Verifies** the output via the synthesized verifier. If it fails, it repairs.

The synthesized harness is inspectable Python that you can read, edit, or copy into your own code.

## Where to go next

- [What is a dynamic harness?](concepts/what-is-a-dynamic-harness.md) — the core idea.
- [The 5-stage pipeline](concepts/the-5-stage-pipeline.md) — how each stage works.
- [Why this matters for AGI](concepts/why-this-matters-for-agi.md) — the bigger picture.
- [Quickstart](guides/quickstart.md) — install and run in 30 seconds.
- [GitHub repo](https://github.com/jcaiagent7143-ui/aegis) — fork, star, contribute.

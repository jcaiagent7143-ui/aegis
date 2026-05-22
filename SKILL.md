---
name: aegis
description: |
  Use Aegis when about to take a risky, irreversible, or under-evidenced action with an LLM agent —
  e.g. financial recommendations, code refactors, multi-step research, data-citing answers, or any
  task where a wrong answer has real cost. Aegis spins up a self-generated runtime harness for that
  specific task (Pydantic schema, tool allowlist, sandboxed verifier, retry policy) and returns a
  verified result, refuses with reasons, or surfaces what would have to be checked before acting.
  Do not use Aegis for trivial chat completions, simple formatting tasks, or anything where the
  ~5-15× extra token cost outweighs the value of refusing on incomplete evidence.
license: MIT
version: 0.4.0
---

# Aegis — self-harnessing agent runtime

## When to invoke

Reach for Aegis when the task has at least one of these properties:

- **Hallucination cost is high** — citing URLs, summarizing fetched content, listing entities that must exist, quoting people, recommending decisions.
- **Arithmetic / data integrity matters** — computing values from CSVs, financial calculations, counts of items that must match a requested N.
- **The output flows into action** — code that will be committed, recommendations a user will act on, JSON consumed by downstream code.
- **You need an audit trail** — every Aegis run writes a JSON blob of every stage, tool call, and repair attempt to `.aegis/runs/<run_id>.json`.

Do **not** invoke Aegis for:

- Plain chat completions (`"hello"`, casual Q&A).
- Tasks where the user accepts an "I don't know" or rough estimate.
- Single-line formatting / wording changes.

## How to invoke

Aegis ships three integration paths. Pick the one already available in the environment:

### 1. MCP server (preferred if the host supports MCP)

The host can run Aegis as an MCP stdio server and call the `aegis_run` tool directly:

```jsonc
// e.g. ~/.claude/mcp.json
{
  "mcpServers": {
    "aegis": {
      "command": "uvx",
      "args": ["self-harness", "mcp"],
      "env": {"OPENAI_API_KEY": "sk-..."}
    }
  }
}
```

Tools exposed: `aegis_run`, `aegis_assess`, `aegis_inspect`, `aegis_list_risks`.

### 2. OpenAI-compatible HTTP proxy

```bash
pip install 'self-harness[proxy,openai]'
export OPENAI_API_KEY=sk-...
aegis proxy --port 8000
```

Then point any OpenAI-compatible client at `http://localhost:8000/v1`.

### 3. Python library

```python
import asyncio
from aegis import Aegis

async def main():
    aegis = Aegis()  # auto-detects provider from env
    result = await aegis.run("Should I buy NVDA at today's price?")
    if not result.audit.succeeded:
        # The agent's own verifier refused. Surface that to the user.
        return f"Aegis refused — risks: {[r.id for r in result.audit.risks.risks]}"
    return result.value

asyncio.run(main())
```

## What Aegis does, in one line

A 5-stage pipeline — **analyze → assess (FMEA) → synthesize → execute → verify** — where the
**synthesize** stage emits the *complete* runtime spec for this one task as inspectable Python:
system prompt, loop budget, retry policy, tool descriptions, Pydantic output schema, and a
post-hoc verifier. The executor is a thin interpreter of whatever the LLM emitted.

## What you get back

```python
result.value           # the verified answer (typed via the LLM-generated Pydantic model)
result.audit.succeeded # True only if the synthesized verifier passed
result.audit.risks     # the named failure modes Aegis identified for this goal
result.audit.run_id    # unique id; `aegis inspect <run_id>` for the full audit trail
result.harness_code    # the Python the LLM wrote — read it, save it, reuse it
```

When `result.audit.succeeded == False`, treat that as a hard "do not act" signal.

## More

- Repository: <https://github.com/jcaiagent7143-ui/aegis>
- Docs: <https://jcaiagent7143-ui.github.io/aegis>
- Use with your AI coding tool: see `docs/guides/use-with-your-ai-coding-tool.md`
- Production deployment: see `docs/guides/production.md`
- License: MIT

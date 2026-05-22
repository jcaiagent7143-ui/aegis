# Quickstart

## Install

```bash
pip install aegis-harness[all]
```

The `[all]` extra pulls in every provider (Anthropic, OpenAI, Ollama, LiteLLM), plus the web demo and TUI. If you want a leaner install:

```bash
pip install aegis-harness                  # core only (works with Mock provider)
pip install aegis-harness[anthropic]       # + Anthropic
pip install aegis-harness[openai]          # + OpenAI
pip install aegis-harness[web]             # + FastAPI demo
```

## Set a provider

Aegis picks the first configured provider in the order: Anthropic → OpenAI → Ollama → Mock.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
# or run a local Ollama server (default localhost:11434)
```

If no provider is configured, Aegis falls back to the **Mock** provider so the package always runs out of the box for exploration.

## CLI

```bash
aegis run "Find 3 OSS LLM agent frameworks and verify each URL"
```

This will:

1. Analyze the goal.
2. Identify failure modes (citation hallucination, truncated list, …).
3. Generate a tailored harness — printed for you to read.
4. Execute the agent inside it.
5. Verify the result.

Other commands:

```bash
aegis inspect <run-id>      # Pretty-print a past audit trail
aegis replay <run-id>       # Re-execute against a saved harness
aegis cache list            # See learned harnesses
aegis cache show <hash>     # Inspect a cached harness
aegis serve                 # Start the web demo on :8000
aegis bench --quick         # Run a 5-task benchmark smoke test
```

## Python

```python
import asyncio
from aegis import Aegis

async def main():
    aegis = Aegis()
    result = await aegis.run("What is the highest-revenue product in sales.csv?")
    print(result.value)
    print(result.harness_code)

asyncio.run(main())
```

## Picking a provider explicitly

```python
from aegis import Aegis
from aegis.providers import Anthropic, OpenAI, Ollama, LiteLLM

Aegis(provider=Anthropic())                          # Claude (default)
Aegis(provider=OpenAI())                             # GPT
Aegis(provider=Ollama(model="llama3.1:70b"))         # local, free
Aegis(provider=LiteLLM(model="bedrock/claude-3"))    # 100+ providers
```

## Where Aegis stores state

By default, audit trails and the harness cache live in `.aegis/` in your current directory:

```
.aegis/
├── runs/
│   └── run_<id>.json     # one per run
└── harnesses/
    ├── index.json
    └── <hash>.json       # one per cached harness
```

Override with `Aegis(cache_dir="/some/path")` or `aegis run --cache-dir /some/path`.

## Next

- [The 5-stage pipeline](../concepts/the-5-stage-pipeline.md)
- [Custom validators](custom-validators.md)
- [Self-hosting with Ollama](self-hosting-with-ollama.md)

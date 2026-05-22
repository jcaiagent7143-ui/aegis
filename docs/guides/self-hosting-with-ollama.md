# Self-hosting with Ollama

Run the entire Aegis stack locally — no API keys, no per-token billing, no data leaving your laptop.

## Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

## Pull a model

A 7B-class model will work for simple tasks, but synthesis quality is meaningfully better with a 70B+ model.

```bash
ollama pull llama3.1            # 8B, fast
ollama pull llama3.1:70b        # bigger, better synthesis
ollama pull qwen2.5-coder:32b   # excellent at code synthesis
```

## Start the server

```bash
ollama serve     # listens on http://localhost:11434
```

## Run Aegis against it

```python
from aegis import Aegis
from aegis.providers import Ollama

aegis = Aegis(provider=Ollama(model="llama3.1:70b"))
result = await aegis.run("Compute the sum of the first 50 positive integers.")
```

Or via the CLI:

```bash
# Auto-detection: Aegis sees Ollama is running and uses it
aegis run "..."

# Or be explicit:
OLLAMA_HOST=http://localhost:11434 aegis run "..."
```

## Tips for local-only operation

- **Synthesis quality matters.** Use the largest model your machine can hold. The synthesizer's job is to write Python — small models will produce harnesses that fail sandbox validation, triggering the deterministic fallback.
- **The harness cache helps a lot.** Local inference is slow; reusing a past harness saves the three most expensive stages.
- **The Mock provider is always there.** If you just want to demo Aegis without any model running, leave the env vars unset and Aegis will use `Mock` — full pipeline, scripted responses, no network.

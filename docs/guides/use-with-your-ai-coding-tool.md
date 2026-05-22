# Use Aegis with your AI coding tool

The fastest way to add Aegis to your existing AI coding workflow — no Python, no rewrites. Pick the integration that matches your tool.

> ⚠️ **Don't `pip install aegis-harness`** — that's a different project on PyPI (apiad/aegis). Our package is `self-harness`.

| Your tool | Best integration | Setup time |
|---|---|---|
| Claude Code | MCP server | 30 seconds |
| Cursor | MCP server OR OpenAI proxy | 30 seconds |
| Cline | MCP server | 30 seconds |
| Continue.dev | MCP server | 30 seconds |
| Windsurf | MCP server | 30 seconds |
| **OpenAI Codex CLI** | OpenAI proxy | 1 minute |
| **Gemini CLI** | OpenAI proxy *or* MCP (if your build supports it) | 1 minute |
| Aider | OpenAI proxy | 1 minute |
| Open WebUI | OpenAI proxy | 1 minute |
| GPT-Pilot / anything OpenAI-compatible | OpenAI proxy | 1 minute |

---

## Option A — MCP server (recommended)

Aegis runs as a Model Context Protocol stdio server. Your AI assistant spawns it and gains four new tools the LLM can call: `aegis_run`, `aegis_assess`, `aegis_inspect`, `aegis_list_risks`.

**Install once:**

```bash
# Zero-install via uvx (recommended for MCP — no venv to manage):
uvx --from "self-harness[mcp,openai,anthropic]" aegis mcp --help

# Or install into your venv:
pip install "self-harness[mcp,openai,anthropic]"
aegis mcp --help
```

Set your provider key (in your shell, for testing):
```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...
# or
export GOOGLE_API_KEY=...
```

> 🚨 **CRITICAL: when you configure `aegis mcp` in your AI tool's MCP config
> below, you MUST also include the API key in the config's `env` block.**
> MCP subprocesses DO NOT inherit your shell's environment variables. If
> `env` is empty or missing the key, Aegis falls back to its Mock provider
> and returns placeholder text (`"[mock] ..."`) — a silent failure mode
> verified in external testing. This trips up every first-time integrator.

Then configure your tool:

### Claude Code

Add to `~/.claude/mcp.json` (create if missing):

```json
{
  "mcpServers": {
    "aegis": {
      "command": "uvx",
      "args": ["--from", "self-harness[mcp,openai]", "aegis", "mcp"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "AEGIS_MODEL": "gpt-5.4-nano-2026-03-17"
      }
    }
  }
}
```

> **Note**: `uvx` spawns the server in a fresh ephemeral venv with the
> right extras every time — no `pip install` step needed. If you'd rather
> install Aegis into your own venv, swap `command`/`args` for
> `"command": "aegis", "args": ["mcp"]` after `pip install "self-harness[mcp,openai]"`.

Restart Claude Code. It now sees `aegis_run`, `aegis_assess`, `aegis_inspect`, `aegis_list_risks` and can invoke them whenever it's about to do something risky.

### Cursor

Cursor → Settings → MCP → Add new MCP server:

- **Name:** `aegis`
- **Command:** `uvx`
- **Args:** `["--from", "self-harness[mcp,openai]", "aegis", "mcp"]`
- **Env:** `OPENAI_API_KEY=sk-...` ← **must be set here, NOT just in your shell**

### Cline (VS Code extension)

Open the Cline panel → ⚙ → MCP Servers → Edit JSON:

```json
{
  "mcpServers": {
    "aegis": {
      "command": "uvx",
      "args": ["--from", "self-harness[mcp,openai]", "aegis", "mcp"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "AEGIS_MODEL": "gpt-5.4-nano-2026-03-17"
      }
    }
  }
}
```

### Continue.dev

Add to `~/.continue/config.json` under `experimental.modelContextProtocolServer`:

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": "stdio",
        "command": "uvx",
        "args": ["--from", "self-harness[mcp,openai]", "aegis", "mcp"],
        "env": {"OPENAI_API_KEY": "${OPENAI_API_KEY}"}
      }
    ]
  }
}
```

### Windsurf

Windsurf → Settings → MCP → Add Server → paste:

```json
{
  "aegis": {
    "command": "uvx",
    "args": ["--from", "self-harness[mcp,openai]", "aegis", "mcp"],
    "env": {"OPENAI_API_KEY": "${OPENAI_API_KEY}"}
  }
}
```

### What you should see

After restarting your tool, ask:
> *Use the aegis_list_risks tool to show me what failure modes you can defend against.*

If the tool returns the 30+ risk catalog as JSON, you're wired up. Try:

> *Use aegis_run to compute 17.5% of 240 with the result verified.*

The assistant will call `aegis_run`, which spins up the full 5-stage pipeline. You'll get back the answer plus the generated harness code.

---

## Option B — OpenAI-compatible HTTP proxy

For any tool that speaks the OpenAI API (`/v1/chat/completions`). The proxy intercepts every chat request, runs it through Aegis, and returns the OpenAI shape back.

```bash
pip install "self-harness[proxy,openai]"
export OPENAI_API_KEY=sk-...
export AEGIS_MODEL=gpt-5.4-nano-2026-03-17

aegis proxy --port 8000
```

You should see:
```
aegis proxy · mode=aegis
  base URL → http://localhost:8000/v1
  docs     → http://localhost:8000/api/docs
```

Now in your tool, change one setting:

| Tool | Setting |
|---|---|
| **Cursor** | Settings → Models → "OpenAI" → Base URL: `http://localhost:8000/v1` |
| **OpenAI Codex CLI** | `export OPENAI_API_BASE=http://localhost:8000/v1` then run `codex` as normal |
| **Gemini CLI** | `export OPENAI_BASE_URL=http://localhost:8000/v1` (Gemini CLI v0.5+ honors OpenAI-compatible endpoints in compat mode) |
| **Continue.dev** | `~/.continue/config.json` → `apiBase: "http://localhost:8000/v1"` |
| **Aider** | `aider --openai-api-base http://localhost:8000/v1 --model aegis` |
| **Open WebUI** | Settings → Connections → OpenAI API → URL: `http://localhost:8000/v1` |
| **GPT-Pilot / others** | `OPENAI_API_BASE=http://localhost:8000/v1` |

Every request your tool sends now goes through Aegis. You can verify with:

```bash
curl http://localhost:8000/health
```

### Special case: Gemini CLI

Gemini CLI ships its own MCP support. The cleanest path is the proxy above
(uses Gemini CLI's OpenAI-compatible mode and routes through Aegis). If your
Gemini CLI build supports user-defined MCP servers, you can also add Aegis
as an MCP server directly:

```jsonc
// ~/.gemini/mcp.json (consult `gemini config --help` for exact path)
{
  "mcpServers": {
    "aegis": {
      "command": "uvx",
      "args": ["--from", "self-harness[mcp,gemini]", "aegis", "mcp"],
      "env": {"GOOGLE_API_KEY": "${GOOGLE_API_KEY}"}
    }
  }
}
```

In this configuration, when Gemini CLI is about to do something risky, its
planner can call `aegis_run` to get a verified result back — even though the
outer LLM is Gemini and the Aegis-internal LLM is also Gemini (or whatever
provider you set in env). Two LLM calls, both Gemini, totally fine.

### Special case: OpenAI Codex CLI

As of recent versions Codex CLI doesn't expose user-configurable MCP
servers, but it speaks the OpenAI HTTP API directly. The proxy is the
right path:

```bash
# Terminal 1
aegis proxy --port 8000

# Terminal 2 — point Codex at the proxy
export OPENAI_API_BASE=http://localhost:8000/v1
codex "refactor src/auth.py to use async-await"
```

Every Codex completion now flows through Aegis. Codex still thinks it's
talking to OpenAI; it gets schema-validated, verified outputs back.

### Per-request mode override

If a request shouldn't go through Aegis (e.g. you want raw chat for a simple prompt), set the `X-Aegis-Mode: passthrough` header. The default is `aegis`.

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "X-Aegis-Mode: passthrough" \
  -H "Content-Type: application/json" \
  -d '{"model": "aegis", "messages": [{"role":"user","content":"hello"}]}'
```

### What you get in the response

Aegis adds a non-standard `aegis` field to the response body containing the run id, success status, identified risks, repair count, harness code, and tool-call log. Compliant OpenAI clients ignore the extra field; observability-aware tools can use it.

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "model": "gpt-5.4-nano-2026-03-17",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {...},
  "aegis": {
    "run_id": "run_a1b2c3",
    "succeeded": true,
    "risks": ["citation-hallucination", "arithmetic-drift"],
    "repairs": 0,
    "harness_code": "...full Python source...",
    "tool_calls": [{"name": "fetch_url", "ok": true}]
  }
}
```

---

## Option C — Both

You can run both at once. MCP for the AI assistants that support it (richer integration), proxy for everything else (broader coverage). They share the same harness cache so a harness learned in one shows up in the other:

```bash
# Terminal 1
aegis mcp

# Terminal 2
aegis proxy --port 8000
```

---

## Troubleshooting

**`uvx: command not found`** — install `uv` first: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

**MCP server starts but the tool can't see it** — restart the AI tool fully. Most MCP clients only read the config at launch.

**Aegis returns `"value": "[mock] ..."` even though I set my API key** — this is the #1 MCP gotcha. MCP subprocesses don't inherit your shell environment. Your `OPENAI_API_KEY` (or any provider key) MUST be set inside the `"env": {}` block of your tool's MCP config — not just in your `.zshrc` / `.bashrc`. If `env` is missing or doesn't include the key, Aegis silently uses its Mock provider and produces placeholder text. Verify with: `aegis_list_risks` will work either way; `aegis_run` returning a value starting with `[mock]` is the smoking gun.

**`aegis_run` returns `succeeded: false` with `tool_calls: []`** — the synthesized harness was too strict for the model to satisfy with the tools available. This is correct behavior — Aegis refused to ship an unverified answer rather than hallucinate. Check `failure_diagnostics` in the response for hints. For research-style tasks where the built-in `web_search` (DuckDuckGo scrape) returns poor results, register a stronger search tool — Tavily, Perplexity, Brave, etc. See `docs/guides/adding-tools.md`.

**`pip install self-harness[mcp]` complains about Python version** — Aegis needs Python 3.11+. Use `pyenv install 3.12 && pyenv shell 3.12`.

**On macOS, you see `ModuleNotFoundError: aegis` after install** — Python 3.13 + Homebrew on macOS sometimes marks editable-install `.pth` files as "hidden" via filesystem flags, breaking `import aegis`. Fix: `chflags -R nohidden ~/.local/share/uv/venvs/`. Or use `pip install` instead of editable install.

**Proxy returns 502/upstream errors** — check that `OPENAI_API_KEY` (or the matching `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY`) is set in the same shell where you ran `aegis proxy`. The env var must be visible to the proxy process, not just your tool's process.

**Aegis runs are too slow** — set `AEGIS_MODEL` to a smaller model for the synthesize stages: `gpt-4o-mini`, `claude-haiku-3-5`, `gemini-2.0-flash`. The synthesize stage benefits from quality; the others can use a cheap model.

---

## See also

- [The 5-stage pipeline](../concepts/the-5-stage-pipeline.md) — what Aegis actually does on every call.
- [Custom validators](custom-validators.md) — add your own risk-catalog entries.
- [Adding tools](adding-tools.md) — register your domain APIs as Aegis tools.
- [Self-hosting with Ollama](self-hosting-with-ollama.md) — run the whole stack locally, no API keys.

# Contributing to Aegis

Thanks for considering it. Aegis is meant to be **the** canonical OSS reference implementation of self-harnessing agents, so the bar is high but the surface is small (~3k LOC) — there is room for you.

## Setting up

```bash
git clone https://github.com/jcaiagent7143-ui/aegis
cd aegis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all,dev,docs]"
pytest                              # ~0.1s, no network
ruff check . && mypy src/aegis      # lint + typecheck
```

## What we want

In rough order of how much we'd love the PR:

### 🥇 Risk-catalog entries

Open `src/aegis/assess/risk_catalog.py` and add a `CatalogEntry` for any failure mode you've actually seen agents make in production. Include:

- a stable `id` (kebab-case),
- a one-sentence `description`,
- realistic `trigger_keywords`,
- one or more concrete `defense_hints`.

We aim for ~100 entries over time. Each one makes every Aegis user safer.

### 🥈 Cookbook examples

Add a runnable `examples/NN_<domain>.py` showing Aegis on a domain we haven't covered (security, finance, biology, education, …). Keep them under 80 lines.

### 🥈 Provider adapters

Want Aegis on Vertex, Bedrock, Together, Groq, Mistral? Implement the `Provider` protocol in `src/aegis/providers/<name>.py`, register it in `auto_provider()`, add a test using `respx` or `vcr`.

### 🥉 Benchmark tasks

Each task in `benchmarks/tasks/` exercises a named risk. Add tasks for under-tested risks (we especially need: `pii-leak`, `prompt-injection-fetched`, `silent-tool-failure`).

### 🛠 Bug fixes / docs

Any bug fix is welcome. Match the existing test style; if it's a behavior bug, add a regression test that fails before your fix.

## House style

- **Ruff + mypy strict.** PRs that break either fail CI.
- **No comments that restate the code.** Comments explain *why*, not *what*.
- **No new top-level deps** without discussion — Aegis aims to stay light.
- **One PR, one concern.** Squashing during merge is fine.

## Reporting issues

Good bug reports include:

- The goal text.
- The provider you were using.
- The full audit JSON (`.aegis/runs/<run_id>.json`).

The audit blob is usually enough for us to reproduce without your API keys.

## Code of Conduct

Be kind, assume good faith, and don't be a jerk. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

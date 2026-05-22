# Launch checklist — Aegis v0.4.0

Everything below is something only you can do (auth, accounts). I've prepared
the repo so each step is a copy-paste.

## 1 · Push to GitHub (5 minutes)

```bash
cd /Users/loongnianchew/Desktop/claude/harness

# If gh CLI isn't authenticated yet
gh auth login --hostname github.com --git-protocol https --web

# Create the public repo + push the v0.4.0 commit
gh repo create loongnianchew/aegis \
  --public \
  --description "Dynamic, on-the-fly generated harnesses for AI agents. The LLM designs its own runtime per task — no developer hand-authoring." \
  --homepage "https://loongnianchew.github.io/aegis" \
  --source=. \
  --remote=origin \
  --push

# Tag the release
git tag -a v0.4.0 -m "v0.4.0 — first public release"
git push origin v0.4.0
```

After push:

```bash
# Add the topics so the repo appears in relevant GitHub feeds
gh repo edit loongnianchew/aegis --add-topic ai,agent,llm,claude,openai,gemini,mcp,model-context-protocol,guardrails,sandbox,agi,self-harnessing,python
```

Visit https://github.com/loongnianchew/aegis to confirm it's live.

## 2 · Set up PyPI publishing (10 minutes, one-time)

The release workflow uses **PyPI Trusted Publishing** (no API token in GitHub
secrets needed). One-time setup:

1. Create a PyPI account if you don't have one: https://pypi.org/account/register/
2. Visit https://pypi.org/manage/account/publishing/ → "Add a new pending publisher"
3. Fill in:
   * **PyPI Project Name:** `aegis-harness`
   * **Owner:**             `loongnianchew`
   * **Repository name:**   `aegis`
   * **Workflow name:**     `release.yml`
   * **Environment name:**  `pypi`
4. In your GitHub repo: Settings → Environments → New environment → name it `pypi`.
   Add an environment protection rule "Required reviewers: loongnianchew" so
   nobody else can trigger a publish.

Now any `git push origin vX.Y.Z` tag triggers a PyPI publish automatically.

## 3 · Enable GitHub Pages for docs (2 minutes)

1. In repo Settings → Pages → Build and deployment source: "GitHub Actions"
2. The `.github/workflows/docs.yml` workflow auto-runs on any push to `main`
   that touches `docs/` or `mkdocs.yml`.

After the first run, your docs site goes live at
**https://loongnianchew.github.io/aegis**.

## 4 · Rotate the OpenAI API key (CRITICAL — 1 minute)

You pasted `sk-proj-Qc41jh...` in the chat transcript multiple times. Treat
it as compromised:

1. https://platform.openai.com/api-keys
2. Find the key → "Revoke"
3. Create a new key. Save it in `~/.zshrc` or your secrets manager — never
   in a chat transcript again.

## 5 · Validate the live path against the real LLM (5 minutes)

```bash
cd /Users/loongnianchew/Desktop/claude/harness
source .venv/bin/activate
chflags -R nohidden .venv     # macOS quirk

export OPENAI_API_KEY=<your fresh key>
export AEGIS_MODEL=gpt-5.4-nano-2026-03-17

python scripts/run_live.py
```

Should output 7 sections of ✓ with green markers. If anything ✗, paste the
output and we iterate.

## 6 · Announce (when you're ready)

### Hacker News (Show HN)

Title:
> Show HN: Aegis — the LLM writes its own agent harness per task, no hand-authoring

Body (first comment):
> Today, every agent framework — OpenClaw, Hermes, LangChain, etc. — makes
> you hand-author the harness. The 2027 prediction is agents that design
> their own. Aegis is the open-source 2026 implementation: drop into Claude
> Code / Cursor / Codex / any MCP or OpenAI-compatible tool, and your agent
> gains a per-task self-generated runtime (system prompt, schema, verifier,
> retry policy — all written by the LLM, validated by a sandbox, executed
> by a thin interpreter). MIT licensed, 75 unit tests, real-LLM tested
> against gpt-5.4-nano. Repo: https://github.com/loongnianchew/aegis.
> Feedback welcome.

### Twitter/X

> The thing we'll all use in 2027:
>
> Instead of you writing the agent harness, the LLM writes one — per task,
> in Python, with its own system prompt + schema + verifier + retry policy.
>
> Released today as @aegisharness, MIT licensed, plugs into Claude Code,
> Cursor, Codex, anything OpenAI-compatible.
>
> https://github.com/loongnianchew/aegis

### Reddit (/r/LocalLLaMA, /r/MachineLearning, /r/Python)

Same as above, but lead with "Open-source: I built …" and link to the
README's "What the LLM actually writes" section.

## 7 · Iterate (weeks 1-4)

Expect issues for:
* New risk-catalog entries from users' production failures
* Provider quirks against models I didn't test (Anthropic, Gemini, Ollama
  variants)
* Tool-call format edge cases
* The macOS hidden-`.pth` quirk

Each one is a small PR. The architecture is set. Keep shipping.

## Known caveats to lead with in the README's "Status" line (already there)

* v0.4 is beta — public API may change before 1.0
* Live-tested only against OpenAI gpt-5.4-nano; Anthropic + Gemini adapters
  ship but unverified against real APIs
* Real benchmark numbers vs static-harness frameworks: not yet collected
  (run `python -m benchmarks.run` with a real key + commit the JSON)
* Hero GIF: the SVG diagram covers it for v0.4; record an actual asciinema
  cast before v1.0

These don't block launch — they're the natural backlog for v0.5.

# Changelog

All notable changes to Aegis are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] — 2026-05-23

Triggered by an external review that mis-identified `pypi.org/project/aegis-harness/`
(Alejandro Piad's TUI orchestrator) as our codebase — and was right to. Our
v0.4.0/v0.4.1 SKILL.md/README directed users to that name, so the confusion
was structurally our fault. This release closes the loop on two fronts:

### Added
- **Anti-confusion banner** at the top of README + SKILL.md naming the
  collision explicitly (`apiad/aegis` is a different project) and pointing
  at the correct git-based install command.
- **Git-based install commands everywhere** as the recommended path until
  `self-harness` is published on PyPI. Each occurrence shows both the
  current (git+https) and post-publish (`pip install self-harness`) form so
  the docs survive the publication moment without further edits.
- **OpenAI Codex CLI** + **Gemini CLI** entries in the integration table
  and dedicated sections in `docs/guides/use-with-your-ai-coding-tool.md`
  showing the exact env-var + base-URL setup for each. Codex uses the
  proxy; Gemini CLI gets both proxy and direct-MCP recipes.
- **Incremental audit-trail persistence** (`Pipeline(audit_path=...)`).
  The 5-stage pipeline now writes the audit JSON to disk after every
  stage via an atomic ``.partial → rename`` write, so a process crash or
  kill mid-pipeline leaves a recoverable trail showing exactly which
  stages completed. `Aegis.run()` enables this by default, pointing at
  `cache_dir/runs/_in_flight.json` during execution and finalizing to
  `cache_dir/runs/<run_id>.json` on completion. Closes criticism #7 of
  the external review.
- New test module `tests/unit/test_incremental_persistence.py` (3 tests):
  happy path stage-by-stage, mid-pipeline crash recovery, persistence
  failure must not break the pipeline.

### Changed
- MCP-config examples for Claude Code etc. use `"command": "aegis"` rather
  than `"command": "uvx"` while we're on the git-install path — uvx requires
  PyPI to fetch from. Switch back to uvx once publication is live.
- README badge bumped to 0.4.2.

### Notes for the external reviewer
- Items #1–#6 and #8 of the v0.4.0 review described `pypi.org/project/aegis-harness/`
  (apiad/aegis), not this project. Different author, different repo,
  different architecture. Worth re-running the review against the actual
  codebase via the git-install command above.
- Item #7 (state durability) is fixed in this release.
- Item #9 (skill/docs/package mismatch) was the root cause of the entire
  confusion and is closed by the rename + git-install messaging + banner.

### Tests
- **78 unit tests** (was 75), all passing.

---

## [0.4.1] — 2026-05-22

Bug-fix release surfaced by an external-developer test of the v0.4.0 GitHub
release. Two real issues caught and fixed; functionality unchanged.

### Breaking
- **PyPI distribution renamed `aegis-harness` → `self-harness`.** The old name
  was already owned by an unrelated project on PyPI (Alejandro Piad's TUI
  meta-harness — different project, coincidentally also at v0.4.0).
  Publishing under `aegis-harness` would have failed with a name conflict;
  users following the v0.4.0 README would have installed someone else's
  package. The Python import path is unchanged:

      pip install self-harness                # was: pip install aegis-harness
      from aegis import Aegis                 # unchanged

  Every doc, install command, MCP config example, and provider error
  message has been updated.

### Fixed
- **Rich tag parser was eating `[proxy]` / `[mcp]` / `[web]` in error
  messages.** Running `aegis proxy` without the proxy extras installed
  printed `Install proxy extras: pip install 'aegis-harness'` — the
  `[proxy]` portion was silently stripped because Rich treats brackets
  as style tags. All three "install the extras" hints now escape the
  brackets so users see the correct command.
- User-Agent header in `web_search` and `fetch_url` tools updated from the
  placeholder `github.com/aegis-harness` to the real repo URL.
- A LAUNCH.md filesystem path was accidentally rewritten during an earlier
  global username find-replace; restored.

### Migration notes for v0.4.0 users
If you installed via `pip install aegis-harness` against v0.4.0 docs:

    pip uninstall aegis-harness
    pip install self-harness          # or for everything: pip install 'self-harness[all]'

GitHub repo URL is unchanged: <https://github.com/jcaiagent7143-ui/aegis>

---

## [0.4.0] — 2026-05-22

The "any AI tool can use Aegis" release. Two new distribution surfaces mean
developers using Claude Code, Cursor, Cline, Continue, Windsurf, Aider, or
anything OpenAI-compatible can plug Aegis in without writing Python.

### Added — MCP server
- `aegis mcp` — Aegis as a Model Context Protocol stdio server. Any
  MCP-compatible AI assistant can spawn it and call its four tools:
  `aegis_run`, `aegis_assess`, `aegis_inspect`, `aegis_list_risks`.
- New module `aegis.mcp` (entry point `aegis.mcp.server.run`).
- Install: `pip install 'self-harness[mcp]'` or `uvx self-harness mcp`.

### Added — OpenAI-compatible HTTP proxy
- `aegis proxy --port 8000` — exposes `/v1/chat/completions`, `/v1/models`,
  `/health`. Aegis runs every request through the 5-stage pipeline by default
  and returns the OpenAI response shape with an extra `aegis` field carrying
  the audit metadata.
- Per-request mode override via `X-Aegis-Mode: aegis|passthrough` header.
- Streaming (SSE) supported.
- New module `aegis.proxy`. Install: `pip install 'self-harness[proxy]'`.

### Added — guide
- `docs/guides/use-with-your-ai-coding-tool.md` — copy-paste configs for
  Claude Code, Cursor, Cline, Continue, Windsurf (MCP) and Aider, Open WebUI,
  GPT-Pilot (proxy).

### Fixed
- **Sandbox limits in background threads.** `run_with_limits` previously
  crashed when called from a non-main thread (FastAPI/uvicorn workers,
  asyncio thread pools, celery) because `signal.signal()` only works in the
  main thread. Now falls back to no enforcement with a stderr warning,
  matching the Windows behavior. The proxy and any other multi-threaded
  caller now works without surprise.

### Tests
- **75 unit tests** (was 58). New modules:
  - `test_mcp_server.py` — handler unit tests + tool-registration shape.
  - `test_proxy_app.py` — FastAPI TestClient tests covering basic completion,
    multimodal content, mode-header override, streaming, error paths.

---

## [0.3.0] — 2026-05-22

The "fully dynamic harness" release. The LLM now writes the *entire* agent runtime
per task — not just safety code.

### Breaking
- `Pipeline(max_repairs=...)` default changed from `1` to `None`. `None` means
  "use whatever the synthesized harness declared as `MAX_REPAIRS`." Pass an int
  to force a global ceiling.
- `Aegis(max_repairs=...)` default likewise `None`. Existing callers that explicitly
  passed an int keep their behavior; callers relying on the implicit `1` will now
  see the harness's value used instead (usually 1 or 2 — varies per task).

### Added — the v0.3 harness contract
The synthesized harness module may now define (in addition to the required
`Output` / `ALLOWED_TOOLS` / `verify`):

- `SYSTEM_PROMPT: str` — the system message for the execute stage, written
  per-task by the LLM. Default falls back to a generic message.
- `MAX_STEPS: int` — loop budget (1..50, default 8).
- `MAX_REPAIRS: int` — post-verify retry budget (0..5, default 1).
- `MAX_TOKENS_PER_TURN: int` — per-turn token budget (64..16384, default 2048).
- `TEMPERATURE: float` — sampling temperature (0.0..2.0, default 0.0).
- `TOOL_OVERRIDES: dict[str, str]` — per-task re-wording of tool descriptions
  (the agent sees these, not the generic registration descriptions).
- `def repair_feedback(failures, output) -> str` — custom message fed back to
  the model on verify failure. Default is a generic message.

All optional. Each is bounds-clamped on load; wrong types silently fall back to
defaults. The executor honors every field — no more hardcoded loop config.

### Added — Gemini provider
- `aegis.providers.Gemini` — Google Gemini adapter using the official
  `google-genai` SDK. Maps Aegis's internal Message shape onto Gemini's
  Content/Part/FunctionResponse model. Install with
  `pip install self-harness[gemini]`. Auto-detected via `GOOGLE_API_KEY` /
  `GEMINI_API_KEY` env vars.

### Changed
- Synthesize prompt rewritten to teach the LLM the full v0.3 contract with
  worked example and explicit hard rules. Real-LLM testing showed this reduces
  first-attempt sandbox-load failures meaningfully.
- Fallback Jinja template emits the full contract too (with `SYSTEM_PROMPT`,
  `MAX_STEPS`, `MAX_REPAIRS`, `repair_feedback`).
- `render_fallback()` sizes `MAX_STEPS` and `MAX_REPAIRS` to the risk profile
  weight — high-risk goals get more steps and more repairs.

### Fixed (carried from 0.2.x development)
- Synthesize retry loop now exercises `load_harness()` not just `validate_source()`,
  so pydantic schema errors (e.g. leading-underscore field names) trigger a retry
  with corrective feedback instead of crashing later.
- Pipeline gracefully falls back to the deterministic template when
  `load_harness()` fails after all generator retries.
- Pydantic v2 forward-ref resolution: `Output.model_rebuild(_types_namespace=…)`
  called after exec so `Any`, `Literal`, custom types resolve against the
  harness's own namespace (synthetic `__module__` isn't in `sys.modules`).

### Tests
- **58 unit tests** (was 50). New module `test_harness_contract_v03.py` covers
  defaults, bounds clamping, type coercion, and pipeline honoring harness-emitted
  `MAX_REPAIRS`.

---

## [0.2.0] — 2026-05-22

### Fixed (correctness)
- **Multi-turn tool calls now work against real LLMs.** v0.1 appended an assistant
  message without the `tool_calls` field, which caused OpenAI to reject the very
  next request with `400: messages with role 'tool' must be a response to a preceeding
  message with 'tool_calls'`. Anthropic had the symmetric bug in its content-block
  shape. The internal `Message` type now carries a `tool_calls` list and
  `Message.tool_result(...)` factory, and the two adapters serialize correctly.
- OpenAI adapter switched from `max_tokens` to `max_completion_tokens`, which is
  required by the gpt-5 / o-series models and accepted by gpt-4o.
- Web demo: the `_suppress` context manager (which silently dropped exceptions
  from `await ws.close()`) replaced with `contextlib.suppress`. Cleanup logic
  now runs in `finally`.

### Added
- **Sandbox wall-clock + memory limits.** `verify()` runs under `signal.ITIMER_REAL`
  for sub-second timeout and `resource.setrlimit(RLIMIT_AS)` for a memory cap.
  POSIX only; Windows falls back to plain execution with a warning. New
  `SandboxTimeout` exception, and `HarnessModule.call_verify(timeout_s, memory_mb)`.
- **Streaming for the OpenAI provider** — `Provider.stream()` yields `("delta", str)`
  events as tokens arrive, finishing with `("done", Completion)`. Web demo
  ready to consume (UI hookup planned for v0.3).
- **Retry + rate-limit handling** in both Anthropic and OpenAI adapters
  (exponential backoff: 1s → 2s → 4s → 8s → 16s, max 3 retries by default).
- **VCR-recorded integration tests** scaffold (`tests/integration/`) with
  cassette redaction of `Authorization` / `x-api-key` / cookies.
- **Live-validation script** (`scripts/run_live.py`) — single command, 7 checks,
  exits non-zero on any failure. Use this to gate releases.
- Tests for multi-turn Message serialization (both OpenAI and Anthropic
  shapes) and sandbox limit enforcement. **48 unit tests** total (was 36).

### Changed
- Synthesize-stage system prompt tightened: explicit allowlist of imports,
  explicit forbidden constructs, required interface contract spelled out,
  example shape provided. Goal is to make first-attempt sandbox-valid
  generation reliable.
- `Provider` protocol unchanged; new helpers `to_openai_dicts(...)` and
  `to_anthropic(...)` in `providers.base` for the serialization layer.

### Security notes
- The sandbox is appropriate for trusted local execution. **It is not a
  multi-tenant security boundary.** For untrusted goals, run Aegis inside a
  process sandbox (firejail, Docker, gVisor).

---

## [0.1.0] — 2026-05-22

Initial release. 5-stage pipeline, 30-entry risk catalog, four provider
adapters (Anthropic, OpenAI, Ollama, LiteLLM, Mock), CLI, FastAPI web demo,
mkdocs site, MIT license. Verified end-to-end against the Mock provider only.
Known caveats addressed in 0.2.0.

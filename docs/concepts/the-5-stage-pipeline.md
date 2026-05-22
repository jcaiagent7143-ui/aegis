# The 5-stage pipeline

Every Aegis run goes through five stages. Each stage produces a structured artifact recorded in the audit trail.

```
                ┌──────────────────┐
   Your goal ──▶│ 1. ANALYZE       │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ 2. ASSESS (FMEA) │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ 3. SYNTHESIZE    │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ 4. EXECUTE       │
                └────────┬─────────┘
                         ▼
                ┌──────────────────┐
                │ 5. VERIFY        │  (→ repair loop on failure)
                └────────┬─────────┘
                         ▼
                Result + audit + harness
```

## 1. Analyze

**Input:** the user goal (free text).
**Output:** a structured decomposition — summary, deliverable, likely tools, open questions, output-shape hint.

The model is asked to produce a tiny JSON object describing the task. This becomes the prior for every later stage.

[Source: `src/aegis/analyze/decomposer.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/analyze/decomposer.py)

## 2. Assess (FMEA)

**Input:** goal + decomposition + risk catalog (~30 named failure modes).
**Output:** a `RiskProfile` — list of `Risk` objects with severity, rationale, and defense hints.

FMEA stands for *Failure Mode and Effects Analysis*, borrowed from aerospace and medical-device engineering. We ask the model to enumerate which catalog entries apply to this goal. We then merge in keyword-triggered risks so common patterns are never missed.

[Source: `src/aegis/assess/fmea.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/assess/fmea.py) · [Catalog: `src/aegis/assess/risk_catalog.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/assess/risk_catalog.py)

## 3. Synthesize

**Input:** decomposition + risk profile + tool catalog.
**Output:** a complete Python module source for the harness.

This is the heart of Aegis. The model emits Python code that defines:

- `class Output(BaseModel)` — the output schema.
- `ALLOWED_TOOLS: list[str]` — tools the agent may call during execution.
- `def verify(output) -> list[str]` — post-hoc verifier returning failure messages.

The source is then AST-validated and exec'd in a restricted sandbox. On parse/sandbox failure, the synthesizer gets one repair attempt; on second failure, Aegis falls back to a deterministic Jinja template.

[Source: `src/aegis/synthesize/generator.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/synthesize/generator.py) · [Sandbox: `src/aegis/synthesize/sandbox.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/synthesize/sandbox.py)

## 4. Execute

**Input:** loaded harness + goal.
**Output:** a validated `Output` instance + a full tool-call log.

A standard agent loop. The system prompt embeds the goal, the allowed-tool list, and the `Output` JSON-schema. The agent calls tools (only those in `ALLOWED_TOOLS`), eventually returns a JSON answer, and we coerce it into the `Output` Pydantic model.

[Source: `src/aegis/execute/runner.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/execute/runner.py)

## 5. Verify

**Input:** validated `Output` + the synthesized `verify()` function.
**Output:** a list of failure strings (empty = pass).

The synthesized verifier runs locally — it can call the same tools the agent used, but in a controlled way (deterministic, post-hoc, not adversarial). On failure, the pipeline runs one repair iteration: the goal is rewritten to include the failure messages, and execute + verify rerun.

[Source: `src/aegis/verify/verifier.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/verify/verifier.py)

## Cache fast-path

If the harness cache (`memory/harness_cache.py`) finds a past harness whose goal is sufficiently similar (Jaccard trigram > 0.45), stages 1-3 are skipped and the cached harness is reused. The audit trail marks this with a `cache_hit` stage.

## What's in the audit trail

Every run produces a JSON audit:

```json
{
  "run_id": "run_a1b2c3d4e5f6",
  "goal": "...",
  "provider": "anthropic",
  "stages": [
    {"name": "analyze", "ok": true, "tokens_in": 412, "tokens_out": 78, "duration_ms": 980, "output": {...}},
    {"name": "assess",  "ok": true, "tokens_in": 1820, "tokens_out": 290, "duration_ms": 1840, "output": {...}},
    {"name": "synthesize", "ok": true, ...},
    {"name": "execute", "ok": true, ...},
    {"name": "verify", "ok": true, "output": {"passed": true, "failures": []}}
  ],
  "risks": {...},
  "harness_code": "...",
  "tool_calls": [...],
  "repairs": 0,
  "succeeded": true
}
```

Use `aegis inspect <run_id>` to pretty-print one.

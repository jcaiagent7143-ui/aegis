# Aegis benchmarks

A small but honest benchmark suite comparing three execution modes on the same set of agent tasks:

1. **`raw`** — direct LLM call with the task as a single prompt. No tools, no schema, no verification.
2. **`fixed`** — a hand-authored, one-size-fits-all harness: Pydantic output model, built-in tools, generic verifier.
3. **`aegis`** — the full 5-stage Aegis pipeline. Per-task synthesized harness.

## Methodology

- Each task lives in `tasks/` as a Python module exposing `goal`, `expected`, and a `check(output) -> bool`.
- For each (task × mode) we record: `passed`, `tokens`, `latency_ms`, `tool_calls`, `n_repairs`.
- Results write to `results/YYYY-MM-DD.json`.

## Running

```bash
# Smoke test (5 tasks):
python -m benchmarks.run --quick

# Full sweep:
python -m benchmarks.run

# Specific provider:
AEGIS_PROVIDER=openai python -m benchmarks.run
```

Results from the last full sweep are committed to `results/`. To regenerate the headline numbers in the README, run the full sweep against Claude on the default model and copy the summary into the README's benchmarks section.

## Adding tasks

A good benchmark task:

- Has a single verifiable answer (numeric, URL list, JSON shape).
- Exercises at least one named failure mode (citation-hallucination, arithmetic-drift, …).
- Doesn't require >20 tool calls or >30s end-to-end.

Drop a new module in `tasks/`; the runner auto-discovers it.

# Reference

Full API reference lives in the source. The most-touched modules:

| Module | Purpose |
|---|---|
| [`aegis.Aegis`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/core/aegis.py) | The facade — `await aegis.run(goal)` |
| [`aegis.core.pipeline.Pipeline`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/core/pipeline.py) | The 5-stage orchestrator |
| [`aegis.providers.base.Provider`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/providers/base.py) | Protocol every LLM adapter implements |
| [`aegis.synthesize.sandbox`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/synthesize/sandbox.py) | AST validation + restricted exec |
| [`aegis.assess.risk_catalog.CATALOG`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/assess/risk_catalog.py) | The named failure modes |
| [`aegis.execute.tool_registry.tool`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/execute/tool_registry.py) | Decorator for new tools |
| [`aegis.memory.harness_cache.HarnessCache`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/memory/harness_cache.py) | Embedding-keyed cache |

## The Risk Catalog (built-in)

| id | level | description |
|---|---|---|
| `citation-hallucination` | HIGH | Model fabricates URLs or sources |
| `entity-fabrication` | HIGH | Model invents people/companies that don't exist |
| `quotation-paraphrase` | MEDIUM | Claims a quote but paraphrases or invents |
| `arithmetic-drift` | HIGH | Number doesn't add up under recomputation |
| `off-by-one` | MEDIUM | Count or range is off by one |
| `unit-confusion` | MEDIUM | Mixes units (USD vs USDM, kg vs lb) |
| `date-drift` | MEDIUM | Wrong year/version |
| `stale-knowledge` | HIGH | Time-sensitive answer from training cutoff |
| `overscoped-tools` | HIGH | More powerful tools than the task needs |
| `prompt-injection-fetched` | HIGH | Fetched content contains hijack instructions |
| `path-traversal` | HIGH | File access escapes workspace |
| `destructive-shell` | CRITICAL | Generated command is destructive |
| `schema-drift` | MEDIUM | Output doesn't match expected shape |
| `truncated-list` | MEDIUM | List has wrong number of items |
| `leaked-reasoning` | LOW | Scratchpad ends up in output |
| `untested-edit` | HIGH | Code change ships without tests |
| `syntax-error` | HIGH | Generated code fails to parse |
| `import-fabrication` | MEDIUM | Imports non-existent packages |
| `api-fabrication` | HIGH | Calls non-existent API methods |
| `infinite-loop` | MEDIUM | Agent never terminates |
| `lost-goal` | MEDIUM | Agent drifts from original goal |
| `silent-tool-failure` | HIGH | Tool errored, model continued |
| `ranking-ambiguity` | MEDIUM | "Top X" without a metric |
| `overconfident-uncertainty` | MEDIUM | Commits when evidence is weak |
| `implicit-assumption` | LOW | Unstated assumption changes answer |
| `pii-leak` | HIGH | PII patterns in output |
| `secret-leak` | CRITICAL | API-key-like strings in output |
| `nondeterministic-tool` | LOW | Randomness without a seed |
| `encoding-bug` | LOW | Quote/escape issues |
| `markdown-injection` | LOW | Rendered markdown executes unexpectedly |
| `locale-confusion` | LOW | Number/date format mismatch |

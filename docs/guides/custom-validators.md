# Custom validators

Aegis ships with a risk catalog of ~30 named failure modes. Each entry tells the synthesizer how to defend against that risk. For domain-specific validation, you have three increasingly powerful options.

## Option 1 — Add an entry to the risk catalog

The cleanest path. Open [`src/aegis/assess/risk_catalog.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/src/aegis/assess/risk_catalog.py) and add a `CatalogEntry`:

```python
CatalogEntry(
    id="sql-injection-pattern",
    name="SQL injection in generated query",
    description="Generated SQL string contains user input concatenated without parameterization.",
    typical_level=RiskLevel.HIGH,
    trigger_keywords=("sql", "query", "database", "select", "insert"),
    defense_hints=(
        "require all parameters as a separate dict",
        "verifier rejects strings containing '; drop' or '-- '",
    ),
    schema_hint='params: dict[str, Any] = Field(default_factory=dict)',
    verifier_hint="assert ';' not in output.query.lower()",
)
```

PRs welcome.

## Option 2 — Inject custom tools

Tools are decorated functions. Register your own and the synthesizer can use them in `verify()`:

```python
from aegis.execute.tool_registry import default_registry, tool

@tool(
    name="check_sql_syntax",
    description="Parse a SQL string and return list of syntax errors.",
    parameters={"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]},
)
def check_sql_syntax(sql: str) -> list[str]:
    ...

registry = default_registry()
registry.register(check_sql_syntax)

aegis = Aegis(tools=registry)
```

The synthesizer sees your tool in the catalog and can emit `tool("check_sql_syntax", sql=output.query)` inside its generated `verify()`.

## Option 3 — Subclass Pipeline

For full control, subclass `Pipeline` and override any stage. Useful if you want, say, a deterministic non-LLM synthesizer for a specific domain.

```python
from aegis.core.pipeline import Pipeline

class MyPipeline(Pipeline):
    async def execute(self, goal):
        # custom logic
        ...
```

## When in doubt

Open an issue on GitHub describing the failure mode you want to defend against. We'd rather grow the catalog than have everyone fork it.

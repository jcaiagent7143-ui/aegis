"""The Aegis risk catalog — a curated library of named failure modes.

Each entry pairs a failure mode with concrete defense hints that bias the
synthesizer toward known-good guardrails. The FMEA stage selects a subset
of these based on goal text + provider reasoning.

Contributions welcome: every new failure mode observed in production should
end up here. See CONTRIBUTING.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.core.risk import RiskLevel


@dataclass(frozen=True)
class CatalogEntry:
    """A named, well-understood failure mode."""

    id: str
    name: str
    description: str
    typical_level: RiskLevel
    trigger_keywords: tuple[str, ...] = field(default_factory=tuple)
    defense_hints: tuple[str, ...] = field(default_factory=tuple)
    schema_hint: str = ""
    verifier_hint: str = ""

    def to_prompt_block(self) -> str:
        lines = [
            f"- id: {self.id}",
            f"  name: {self.name}",
            f"  description: {self.description}",
            f"  typical_level: {self.typical_level.value}",
            f"  defenses: {'; '.join(self.defense_hints) or '(generic)'}",
        ]
        return "\n".join(lines)


# Hand-curated catalog. Each entry is a real, observed agent failure mode.
CATALOG: tuple[CatalogEntry, ...] = (
    # ─── Hallucination / fabrication ──────────────────────────────────────
    CatalogEntry(
        id="citation-hallucination",
        name="Citation hallucination",
        description="Model fabricates URLs, DOIs, or sources that don't exist.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("cite", "source", "url", "research", "find", "list", "paper"),
        defense_hints=(
            "regex-constrain URL fields",
            "add post-hoc verifier that HTTP-fetches each cited URL",
            "require model to copy-paste verbatim quotes",
        ),
        schema_hint="url: HttpUrl = Field(pattern=r'https?://...')",
        verifier_hint="for c in output.citations: assert fetch_url(c.url).status_code == 200",
    ),
    CatalogEntry(
        id="entity-fabrication",
        name="Entity fabrication",
        description="Model invents people, companies, or products that don't exist.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("who is", "named", "company called", "startup", "person"),
        defense_hints=(
            "require an identifying URL or canonical id per entity",
            "verify via a name→ID lookup tool",
        ),
        schema_hint="entity_id: str = Field(min_length=1)",
        verifier_hint="verify entity_id resolves via a lookup tool",
    ),
    CatalogEntry(
        id="quotation-paraphrase",
        name="Quotation paraphrase",
        description="Model claims a quote but actually paraphrases or invents it.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("quote", "said", "stated", "according to"),
        defense_hints=(
            "require the source URL/page and exact span",
            "fuzzy-match the quote against the fetched source",
        ),
        verifier_hint="check substring match (case-insensitive) against fetched source",
    ),
    # ─── Arithmetic / data integrity ─────────────────────────────────────
    CatalogEntry(
        id="arithmetic-drift",
        name="Arithmetic drift",
        description="Model produces a number that doesn't add up under recomputation.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("sum", "total", "average", "compute", "count", "csv", "calculate"),
        defense_hints=(
            "recompute the answer in Python from the raw data",
            "bound numeric fields with reasonable min/max",
            "require the model to show its working",
        ),
        schema_hint="value: float = Field(ge=..., le=...)",
        verifier_hint="recompute from source; assert math.isclose(model_value, recomputed)",
    ),
    CatalogEntry(
        id="off-by-one",
        name="Off-by-one in counts/ranges",
        description="Counts of items, slices, or date ranges are off by one.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("count", "first n", "last n", "top", "between"),
        defense_hints=(
            "require start and end indices to be explicit and inclusive/exclusive declared",
            "post-hoc count the returned items vs requested",
        ),
        verifier_hint="assert len(output.items) == output.requested_n",
    ),
    CatalogEntry(
        id="unit-confusion",
        name="Unit confusion",
        description="Mixes units (USD vs USDM, kg vs lb, MB vs GB).",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("dollars", "size", "weight", "distance", "currency"),
        defense_hints=(
            "include a unit field on every numeric output",
            "validate unit is in an allowlist",
        ),
        schema_hint='unit: Literal["USD", "EUR", "..."] = "USD"',
    ),
    # ─── Time / date / freshness ─────────────────────────────────────────
    CatalogEntry(
        id="date-drift",
        name="Date or version drift",
        description="Uses outdated or wrong year/version (e.g. confuses 2024 with 2026).",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("current", "latest", "this year", "recent", "version"),
        defense_hints=(
            "inject today's date into the system prompt",
            "require year/version to be explicit and validated",
        ),
        schema_hint="year: int = Field(ge=2020, le=2030)",
    ),
    CatalogEntry(
        id="stale-knowledge",
        name="Stale training-cutoff knowledge",
        description="Model relies on training data for time-sensitive answers.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("today", "current", "latest", "now"),
        defense_hints=(
            "force at least one web_search call before answering",
            "require sources dated after a minimum date",
        ),
    ),
    # ─── Tool / sandbox safety ───────────────────────────────────────────
    CatalogEntry(
        id="overscoped-tools",
        name="Over-scoped tool allowlist",
        description="Giving the agent more powerful tools than it needs (e.g. shell for a read-only task).",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("summarize", "describe", "read", "look up"),
        defense_hints=(
            "deny run_shell / run_python unless the goal needs execution",
            "deny write_file unless the goal requires producing artifacts",
        ),
    ),
    CatalogEntry(
        id="prompt-injection-fetched",
        name="Prompt injection from fetched content",
        description="HTML/text fetched from the web contains instructions that hijack the agent.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("fetch", "web", "url", "scrape", "summarize page"),
        defense_hints=(
            "wrap fetched content in <untrusted>...</untrusted> tags",
            "strip script/style blocks before passing to the model",
            "post-hoc verifier checks output for injected commands (e.g. 'ignore previous')",
        ),
        verifier_hint="assert 'ignore previous' not in str(output).lower()",
    ),
    CatalogEntry(
        id="path-traversal",
        name="Path traversal",
        description="Model writes/reads files outside the intended directory.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("write", "save", "create file", "edit file"),
        defense_hints=(
            "constrain paths to a workspace root",
            "reject any path containing '..' or starting with '/'",
        ),
        verifier_hint="assert os.path.commonpath([path, WORKSPACE]) == WORKSPACE",
    ),
    CatalogEntry(
        id="destructive-shell",
        name="Destructive shell command",
        description="Generated code or tool call performs rm/drop/delete operations.",
        typical_level=RiskLevel.CRITICAL,
        trigger_keywords=("delete", "remove", "drop", "reset"),
        defense_hints=(
            "deny run_shell entirely",
            "require dry-run mode for destructive actions",
        ),
    ),
    # ─── Output shape / structure ────────────────────────────────────────
    CatalogEntry(
        id="schema-drift",
        name="Output schema drift",
        description="Model returns text/markdown when JSON was expected, or wrong keys.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=(),
        defense_hints=(
            "always wrap final answer in a Pydantic model",
            "request json_only=True from the provider",
            "use response_format=Output",
        ),
    ),
    CatalogEntry(
        id="truncated-list",
        name="Truncated or padded list",
        description="Asked for N items, returns fewer (or invents extras).",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("top", "list of", "n=", "give me"),
        defense_hints=("Field(min_length=n, max_length=n) on the list",),
    ),
    CatalogEntry(
        id="leaked-reasoning",
        name="Reasoning leaked into output",
        description="Model includes scratchpad / 'let me think' text in final answer.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=(),
        defense_hints=(
            "JSON mode forces structured output",
            "verifier rejects markdown fences in value fields",
        ),
    ),
    # ─── Code-task specific ──────────────────────────────────────────────
    CatalogEntry(
        id="untested-edit",
        name="Untested code edit",
        description="Code change ships without running the existing test suite.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("refactor", "edit", "modify", "rewrite", "fix bug"),
        defense_hints=(
            "verifier runs `pytest` (or the project's configured test command)",
            "AST-diff: ensure no exported symbols accidentally removed",
        ),
        verifier_hint="subprocess.run(['pytest', '-x'], check=True)",
    ),
    CatalogEntry(
        id="syntax-error",
        name="Syntactic invalidity of generated code",
        description="Generated Python/JS fails to parse.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("code", "write", "generate", "function"),
        defense_hints=("verifier calls ast.parse (Python) or @babel/parser (JS) on output",),
        verifier_hint="ast.parse(output.code)",
    ),
    CatalogEntry(
        id="import-fabrication",
        name="Imports of non-existent packages",
        description="Generated code imports libraries that aren't installed or don't exist.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("code", "script", "use library"),
        defense_hints=("verifier dry-runs `python -c 'import X'` for each imported package",),
    ),
    CatalogEntry(
        id="api-fabrication",
        name="Fabricated API or method name",
        description="Calls a method on a real library that the library doesn't actually have.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("library", "sdk", "api", "framework"),
        defense_hints=(
            "verifier executes the snippet in a sandbox and checks for AttributeError",
            "require documentation URL for any non-stdlib API call",
        ),
    ),
    # ─── Multi-step / planning ───────────────────────────────────────────
    CatalogEntry(
        id="infinite-loop",
        name="Infinite agent loop",
        description="Agent keeps calling the same tool, never terminates.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=(),
        defense_hints=(
            "cap max_steps in the executor",
            "detect repeated identical tool calls and break",
        ),
    ),
    CatalogEntry(
        id="lost-goal",
        name="Lost goal during long trajectory",
        description="Agent drifts from the original goal across many steps.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("plan", "multi-step", "first then", "after that"),
        defense_hints=(
            "repeat the goal in the system prompt at each step",
            "verifier checks final answer addresses the original question",
        ),
    ),
    CatalogEntry(
        id="silent-tool-failure",
        name="Silent tool failure",
        description="Tool returns an error/None, model continues as if it succeeded.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=(),
        defense_hints=(
            "wrap tools to raise on non-2xx / error responses",
            "verifier inspects audit trail for unhandled tool errors",
        ),
    ),
    # ─── Ambiguity / framing ─────────────────────────────────────────────
    CatalogEntry(
        id="ranking-ambiguity",
        name="Ambiguous ranking criterion",
        description='"Top X" or "best Y" without a stated metric — model picks arbitrarily.',
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=("top", "best", "rank", "leading"),
        defense_hints=(
            "require the model to declare its ranking_criterion in the output",
            "include the criterion in the verifier",
        ),
        schema_hint="ranking_criterion: str = Field(min_length=1)",
    ),
    CatalogEntry(
        id="overconfident-uncertainty",
        name="Overconfidence under uncertainty",
        description="Model commits to a single answer when the evidence is weak.",
        typical_level=RiskLevel.MEDIUM,
        trigger_keywords=(),
        defense_hints=(
            "require a `confidence: Literal['low','medium','high']` field",
            "require a `caveats: list[str]` field",
        ),
    ),
    CatalogEntry(
        id="implicit-assumption",
        name="Unstated assumptions",
        description="Answer depends on an assumption the user didn't make.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=(),
        defense_hints=("require assumptions to be enumerated as a field",),
    ),
    # ─── PII / safety ────────────────────────────────────────────────────
    CatalogEntry(
        id="pii-leak",
        name="PII leak in output",
        description="Output contains email/phone/SSN-like patterns that shouldn't be there.",
        typical_level=RiskLevel.HIGH,
        trigger_keywords=("user", "personal", "private", "customer"),
        defense_hints=("verifier regex-scans output for PII patterns",),
    ),
    CatalogEntry(
        id="secret-leak",
        name="Secret leak in output",
        description="Output contains API-key-like or token-like strings.",
        typical_level=RiskLevel.CRITICAL,
        trigger_keywords=(),
        defense_hints=("verifier regex-scans for AKIA / sk- / Bearer patterns",),
    ),
    # ─── Determinism / reproducibility ───────────────────────────────────
    CatalogEntry(
        id="nondeterministic-tool",
        name="Non-deterministic tool used at high temperature",
        description="Tool involving randomness used without seed.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=("random", "sample"),
        defense_hints=("inject a seed; pin temperature low for the synthesizer",),
    ),
    # ─── Format / encoding ───────────────────────────────────────────────
    CatalogEntry(
        id="encoding-bug",
        name="Encoding / escaping bug",
        description="Smart quotes, mojibake, or unescaped chars break downstream consumers.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=("json", "csv", "sql"),
        defense_hints=("verifier round-trips through json.loads / csv.reader",),
    ),
    CatalogEntry(
        id="markdown-injection",
        name="Markdown injection",
        description="Output contains markdown that, when rendered, executes links/images unexpectedly.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=(),
        defense_hints=("escape angle brackets and image links if rendered to HTML",),
    ),
    CatalogEntry(
        id="locale-confusion",
        name="Locale / number-format confusion",
        description="Decimal separator (',' vs '.') or date format (MM/DD vs DD/MM) mismatches.",
        typical_level=RiskLevel.LOW,
        trigger_keywords=("date", "currency", "number"),
        defense_hints=("require ISO 8601 dates and canonical number format",),
    ),
)


_BY_ID: dict[str, CatalogEntry] = {e.id: e for e in CATALOG}


def lookup(risk_id: str) -> CatalogEntry | None:
    return _BY_ID.get(risk_id)


def keyword_filter(goal: str) -> list[CatalogEntry]:
    """Cheap pre-filter: catalog entries whose trigger keywords appear in the goal."""
    g = goal.lower()
    hits: list[CatalogEntry] = []
    for entry in CATALOG:
        if not entry.trigger_keywords:
            continue
        if any(k in g for k in entry.trigger_keywords):
            hits.append(entry)
    return hits


def catalog_summary_for_prompt(max_entries: int = 30) -> str:
    """Compact summary suitable for inclusion in the FMEA prompt."""
    chunks = [e.to_prompt_block() for e in CATALOG[:max_entries]]
    return "\n\n".join(chunks)

"""Aegis CLI entrypoint: `aegis run|inspect|replay|cache|serve|bench`."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from aegis import Aegis

app = typer.Typer(
    name="aegis",
    help="Dynamic, on-the-fly generated harnesses for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
cache_app = typer.Typer(help="Manage the harness cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

console = Console()


def _aegis(cache_dir: Path) -> Aegis:
    return Aegis(cache_dir=cache_dir)


# ── run ─────────────────────────────────────────────────────────────────


@app.command("run")
def run_cmd(
    goal: str = typer.Argument(..., help="What you want the agent to do."),
    show_harness: bool = typer.Option(True, help="Print the generated harness source."),
    show_audit: bool = typer.Option(False, help="Print the full audit trail."),
    cache_dir: Path = typer.Option(Path(".aegis"), help="Directory for cache and run logs."),
) -> None:
    """Synthesize a harness for the goal and execute it."""
    aegis = _aegis(cache_dir)

    with console.status("[bold cyan]running Aegis pipeline...", spinner="dots"):
        result = asyncio.run(aegis.run(goal))

    _render_result(result, show_harness=show_harness, show_audit=show_audit)
    if not result.audit.succeeded:
        raise typer.Exit(code=1)


# ── inspect ─────────────────────────────────────────────────────────────


@app.command("inspect")
def inspect_cmd(
    run_id: str = typer.Argument(..., help="Run id returned by `aegis run`."),
    cache_dir: Path = typer.Option(Path(".aegis"), help="Directory for cache and run logs."),
) -> None:
    """Pretty-print a saved audit trail."""
    aegis = _aegis(cache_dir)
    try:
        result = aegis.inspect(run_id)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    _render_result(result, show_harness=True, show_audit=True)


# ── replay ──────────────────────────────────────────────────────────────


@app.command("replay")
def replay_cmd(
    run_id: str = typer.Argument(...),
    cache_dir: Path = typer.Option(Path(".aegis")),
) -> None:
    """Re-execute a goal against a saved harness."""
    aegis = _aegis(cache_dir)
    result = asyncio.run(aegis.replay(run_id))
    _render_result(result, show_harness=False, show_audit=False)


# ── cache ───────────────────────────────────────────────────────────────


@cache_app.command("list")
def cache_list(cache_dir: Path = typer.Option(Path(".aegis"))) -> None:
    aegis = _aegis(cache_dir)
    items = aegis.cache.list()
    if not items:
        console.print("[dim]Cache is empty.[/dim]")
        return
    table = Table(title=f"Cached harnesses ({len(items)})")
    table.add_column("hash", style="cyan")
    table.add_column("hits", justify="right")
    table.add_column("created", style="dim")
    table.add_column("goal")
    for c in items:
        table.add_row(c.hash, str(c.hits), c.created_at[:19], c.goal[:80])
    console.print(table)


@cache_app.command("show")
def cache_show(
    hash: str,
    cache_dir: Path = typer.Option(Path(".aegis")),
) -> None:
    aegis = _aegis(cache_dir)
    entry = aegis.cache.get(hash)
    if not entry:
        console.print(f"[red]No cached harness with hash {hash}[/red]")
        raise typer.Exit(code=2)
    console.print(Panel(f"[bold]Goal:[/bold] {entry.goal}"))
    console.print(Panel.fit(_syntax(entry.harness_code), title="Harness source"))


@cache_app.command("clear")
def cache_clear(cache_dir: Path = typer.Option(Path(".aegis"))) -> None:
    aegis = _aegis(cache_dir)
    n = aegis.cache.clear()
    console.print(f"Removed {n} cache file(s).")


# ── serve ───────────────────────────────────────────────────────────────


@app.command("serve")
def serve_cmd(
    host: str = "127.0.0.1",
    port: int = 8000,
    cache_dir: Path = typer.Option(Path(".aegis")),
) -> None:
    """Start the FastAPI web demo."""
    try:
        import uvicorn

        from aegis.web.app import build_app
    except ImportError as e:
        # Escape the brackets in `[web]` so Rich's tag parser doesn't strip them.
        console.print(r"[red]Install web extras: pip install 'self-harness\[web]'[/red]")
        raise typer.Exit(code=2) from e

    web_app = build_app(cache_dir=cache_dir)
    uvicorn.run(web_app, host=host, port=port, log_level="info")


# ── mcp (MCP server for Claude Code / Cursor / Cline / Continue / Windsurf) ──


@app.command("mcp")
def mcp_cmd() -> None:
    """Run Aegis as a Model Context Protocol (stdio) server.

    Any MCP client (Claude Code, Cursor, Cline, Continue, Windsurf, ...) can
    spawn this process and call its four tools: aegis_run, aegis_assess,
    aegis_inspect, aegis_list_risks. The client's LLM then has Aegis as a
    safety tool it can invoke before taking risky actions.

    Typical config (e.g. ~/.claude/mcp.json):

        {
          "mcpServers": {
            "aegis": {"command": "uvx", "args": ["self-harness", "mcp"]}
          }
        }
    """
    try:
        from aegis.mcp import run_stdio
    except ImportError as e:
        console.print(r"[red]Install MCP extras: pip install 'self-harness\[mcp]'[/red]")
        raise typer.Exit(code=2) from e
    run_stdio()


# ── proxy (OpenAI-compatible HTTP proxy) ────────────────────────────────


@app.command("proxy")
def proxy_cmd(
    host: str = "127.0.0.1",
    port: int = 8000,
    cache_dir: Path = typer.Option(Path(".aegis")),
    mode: str = typer.Option(
        "aegis",
        help="Default mode: 'aegis' wraps every request in the pipeline; "
        "'passthrough' just forwards. Per-request override via the X-Aegis-Mode header.",
    ),
) -> None:
    """Run Aegis as an OpenAI-compatible /v1/chat/completions proxy.

    Plug this URL into any tool that speaks OpenAI's API:

        Base URL: http://localhost:8000/v1
        API key:  anything (the proxy uses your real key from env)

    Works with Cursor, Continue, Aider, Open WebUI, GPT-Pilot, etc.
    """
    try:
        import uvicorn

        from aegis.proxy import build_app
    except ImportError as e:
        console.print(r"[red]Install proxy extras: pip install 'self-harness\[proxy]'[/red]")
        raise typer.Exit(code=2) from e

    if mode not in ("aegis", "passthrough"):
        console.print("[red]--mode must be aegis or passthrough[/red]")
        raise typer.Exit(code=2)

    proxy_app = build_app(cache_dir=cache_dir, default_mode=mode)  # type: ignore[arg-type]
    console.rule(f"[bold cyan]aegis proxy[/bold cyan] · mode={mode}")
    console.print(f"  base URL → [green]http://{host}:{port}/v1[/green]")
    console.print(f"  docs     → http://{host}:{port}/api/docs")
    uvicorn.run(proxy_app, host=host, port=port, log_level="info")


# ── bench ───────────────────────────────────────────────────────────────


@app.command("bench")
def bench_cmd(
    quick: bool = typer.Option(False, help="Run only 5 tasks for a smoke test."),
    out: Path | None = typer.Option(None, help="Output JSON path."),
) -> None:
    """Run the Aegis benchmark suite."""
    try:
        from benchmarks.run import run as bench_run  # type: ignore[import-not-found]
    except ImportError:
        # Fallback: shell out to the script
        import subprocess

        cmd = [sys.executable, "-m", "benchmarks.run"]
        if quick:
            cmd.append("--quick")
        if out:
            cmd += ["--out", str(out)]
        subprocess.run(cmd, check=False)
        return

    asyncio.run(bench_run(quick=quick, out=out))


# ── version ─────────────────────────────────────────────────────────────


@app.command("version")
def version_cmd() -> None:
    from aegis import __version__

    console.print(f"aegis {__version__}")


# ── rendering helpers ────────────────────────────────────────────────────


def _render_result(result, *, show_harness: bool, show_audit: bool) -> None:
    audit = result.audit

    status = "[green]✓ SUCCESS[/green]" if audit.succeeded else "[red]✗ FAILED[/red]"
    badges = []
    if result.cached:
        badges.append("[cyan]CACHED[/cyan]")
    if audit.repairs:
        badges.append(f"[yellow]{audit.repairs} repair(s)[/yellow]")
    badge_str = " ".join(badges)

    console.rule(f"[bold]aegis run[/bold] · {status} {badge_str}")
    console.print(f"[dim]run_id:[/dim] {audit.run_id}    [dim]provider:[/dim] {audit.provider}")
    console.print(
        f"[dim]tokens:[/dim] {audit.total_tokens}    [dim]duration:[/dim] {audit.total_duration_ms:.0f}ms"
    )

    # Risk summary
    if audit.risks.risks:
        table = Table(title="Identified risks", show_lines=False)
        table.add_column("level", style="bold")
        table.add_column("id", style="cyan")
        table.add_column("rationale")
        for r in audit.risks.risks:
            color = {
                "LOW": "green",
                "MEDIUM": "yellow",
                "HIGH": "red",
                "CRITICAL": "red on white",
            }.get(r.level.value, "white")
            table.add_row(f"[{color}]{r.level.value}[/{color}]", r.id, r.rationale[:80])
        console.print(table)

    if show_harness and audit.harness_code:
        console.print(Panel.fit(_syntax(audit.harness_code), title="Generated harness"))

    # Final value
    try:
        rendered = json.dumps(result.value, indent=2, default=str)
        console.print(Panel(_syntax(rendered, lexer="json"), title="Result"))
    except (TypeError, ValueError):
        console.print(Panel(str(result.value), title="Result"))

    if show_audit:
        console.print(
            Panel(_syntax(audit.model_dump_json(indent=2), lexer="json"), title="Audit trail")
        )


def _syntax(code: str, *, lexer: str = "python") -> Syntax:
    return Syntax(code, lexer, theme="ansi_dark", line_numbers=False, word_wrap=True)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

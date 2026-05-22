"""FastAPI demo server — the three-pane "watch a harness get built" UI.

Streams pipeline events to the browser over WebSocket. Each stage emits
``stage_start`` and ``stage_done`` events; errors are surfaced as ``error``
events and the websocket is closed cleanly.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from aegis import Aegis
from aegis.core.goal import Goal

WEB_DIR = Path(__file__).parent


def build_app(*, cache_dir: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="Aegis demo", docs_url="/api/docs")
    aegis = Aegis(cache_dir=cache_dir or ".aegis")

    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "templates" / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "provider": aegis.provider.name,
            "model": getattr(aegis.provider, "model", ""),
        }

    @app.get("/api/risks")
    def list_risks() -> dict[str, list[dict[str, str]]]:
        from aegis.assess.risk_catalog import CATALOG

        return {
            "risks": [
                {
                    "id": e.id,
                    "name": e.name,
                    "description": e.description,
                    "level": e.typical_level.value,
                }
                for e in CATALOG
            ]
        }

    @app.websocket("/api/run")
    async def run_ws(ws: WebSocket) -> None:
        await ws.accept()
        try:
            raw = await ws.receive_text()
            payload = json.loads(raw or "{}")
            goal = (payload.get("goal") or "").strip()
            if not goal:
                await ws.send_json({"event": "error", "message": "empty goal"})
                return
            await _stream_pipeline(aegis, Goal(description=goal), ws)
        except WebSocketDisconnect:
            return
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    return app


async def _stream_pipeline(aegis: Aegis, goal: Goal, ws: WebSocket) -> None:
    """Run the pipeline and emit per-stage events to the websocket."""
    from aegis.analyze import analyze
    from aegis.assess import assess
    from aegis.core.result import AuditTrail
    from aegis.execute import execute
    from aegis.synthesize import load_harness, synthesize
    from aegis.synthesize.sandbox import SandboxError
    from aegis.verify import verify as verify_stage

    audit = AuditTrail(goal=goal.description, provider=aegis.provider.name)
    await ws.send_json({"event": "start", "run_id": audit.run_id, "goal": goal.description})

    try:
        # 1 — analyze
        await ws.send_json({"event": "stage_start", "name": "analyze"})
        decomposition, ti, to = await analyze(goal, aegis.provider)
        audit.stages.append(_record("analyze", decomposition, ti, to))
        await ws.send_json({"event": "stage_done", "name": "analyze", "data": decomposition})

        # 2 — assess
        await ws.send_json({"event": "stage_start", "name": "assess"})
        risks, ti, to = await assess(goal, decomposition, aegis.provider)
        audit.stages.append(_record("assess", {"profile": risks.model_dump()}, ti, to))
        audit.risks = risks
        await ws.send_json({"event": "stage_done", "name": "assess", "data": risks.model_dump()})

        # 3 — synthesize
        await ws.send_json({"event": "stage_start", "name": "synthesize"})
        catalog = aegis.tools.catalog_for_prompt()
        source, ti, to = await synthesize(goal, decomposition, risks, catalog, aegis.provider)
        audit.stages.append(_record("synthesize", {"source": source}, ti, to))
        audit.harness_code = source
        await ws.send_json(
            {"event": "stage_done", "name": "synthesize", "data": {"source": source}}
        )

        # 4 — execute
        await ws.send_json({"event": "stage_start", "name": "execute"})
        harness = load_harness(
            source,
            tool_callable=lambda name, **kw: aegis.tools.get(name).fn(**kw),
        )
        value, tool_log, ti, to = await execute(goal, harness, aegis.provider, aegis.tools)
        audit.stages.append(_record("execute", {"value": value, "tool_calls": tool_log}, ti, to))
        audit.tool_calls.extend(tool_log)
        await ws.send_json(
            {
                "event": "stage_done",
                "name": "execute",
                "data": {"value": value, "tool_calls": tool_log},
            }
        )

        # 5 — verify
        await ws.send_json({"event": "stage_start", "name": "verify"})
        failures = verify_stage(value, harness, aegis.tools)
        audit.stages.append(_record("verify", {"failures": failures}, 0, 0, ok=not failures))
        audit.succeeded = not failures
        await ws.send_json(
            {
                "event": "stage_done",
                "name": "verify",
                "data": {"passed": not failures, "failures": failures},
            }
        )

        await ws.send_json(
            {
                "event": "done",
                "ok": audit.succeeded,
                "tokens": audit.total_tokens,
                "duration_ms": audit.total_duration_ms,
                "run_id": audit.run_id,
            }
        )
    except SandboxError as e:
        await ws.send_json({"event": "error", "message": str(e), "type": "SandboxError"})
    except Exception as e:
        await ws.send_json({"event": "error", "message": str(e), "type": type(e).__name__})
    finally:
        with contextlib.suppress(Exception):
            audit.save(Path(aegis.cache_dir) / "runs" / f"{audit.run_id}.json")


def _record(name: str, output: dict[str, Any], ti: int, to: int, *, ok: bool = True):
    from aegis.core.result import StageRecord

    s = StageRecord(name=name, tokens_in=ti, tokens_out=to, output=output)
    s.mark_finished(ok=ok)
    return s

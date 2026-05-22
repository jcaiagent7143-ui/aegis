# Production deployment

Aegis is designed to drop into existing services. This page is the operator's checklist.

## TL;DR

```bash
pip install 'aegis-harness[anthropic,openai,gemini,proxy]'
export ANTHROPIC_API_KEY=sk-ant-...     # or OPENAI_API_KEY / GOOGLE_API_KEY
export AEGIS_WORKSPACE=/srv/aegis/work   # constrains file tools
export AEGIS_CACHE_DIR=/var/lib/aegis    # persistent cache + runs
aegis proxy --host 0.0.0.0 --port 8000
```

That's it. Aegis now sits in front of every chat-completion request to that port.

## Choose your integration

| Surface | Use when |
|---|---|
| **Python library** (`from aegis import Aegis`) | Your service is in Python and you want fine control. |
| **CLI** (`aegis run "..."`) | Cron jobs, shell scripts, one-off ops tasks. |
| **MCP server** (`aegis mcp`) | Engineers using Claude Code / Cursor / Cline / Continue / Windsurf in their dev loop. |
| **HTTP proxy** (`aegis proxy`) | Any service or tool that already speaks OpenAI's `/v1/chat/completions` shape. |

The proxy and the library share the same cache and audit trail, so devs running the proxy locally see the same harness reuse as your prod service.

## Deployment patterns

### 1. Sidecar (recommended for most services)

```yaml
# docker-compose.yml
services:
  api:
    image: my-company/api:latest
    environment:
      - OPENAI_API_BASE=http://aegis:8000/v1   # point your app at the sidecar
      - OPENAI_API_KEY=ignored                  # proxy uses its own key from env

  aegis:
    image: aegis-harness:0.4.0
    command: ["aegis", "proxy", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - AEGIS_WORKSPACE=/work
      - AEGIS_CACHE_DIR=/var/lib/aegis
    volumes:
      - aegis_cache:/var/lib/aegis
      - aegis_work:/work
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s

volumes:
  aegis_cache:
  aegis_work:
```

Pros: zero application code changes; observability via the proxy logs.

### 2. Library (Python services)

```python
from aegis import Aegis
from aegis.providers import Anthropic

aegis = Aegis(provider=Anthropic(), tools=my_tool_registry, cache_dir="/var/lib/aegis")

@app.post("/agent")
async def handler(req):
    result = await aegis.run(req.json()["goal"], user_id=req.user.id)
    if not result.audit.succeeded:
        return {"status": "refused", "run_id": result.audit.run_id,
                "risks": [r.id for r in result.audit.risks.risks]}
    return {"status": "ok", "value": result.value, "run_id": result.audit.run_id}
```

Pros: typed return values, direct access to the audit object, full control over tool registration.

### 3. Kubernetes deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: aegis }
spec:
  replicas: 3
  selector: { matchLabels: { app: aegis } }
  template:
    metadata: { labels: { app: aegis } }
    spec:
      containers:
        - name: aegis
          image: ghcr.io/loongnianchew/aegis:0.4.0
          args: ["proxy", "--host", "0.0.0.0", "--port", "8000"]
          env:
            - { name: ANTHROPIC_API_KEY, valueFrom: { secretKeyRef: { name: llm-keys, key: anthropic } } }
            - { name: AEGIS_CACHE_DIR,   value: /cache }
          volumeMounts:
            - { name: cache, mountPath: /cache }
          readinessProbe: { httpGet: { path: /health, port: 8000 } }
          resources:
            requests: { cpu: 250m, memory: 512Mi }
            limits:   { cpu: 1,    memory: 2Gi   }
      volumes:
        - name: cache
          persistentVolumeClaim: { claimName: aegis-cache }
```

## Operational concerns

### Observability

Every run writes a JSON audit blob to `$AEGIS_CACHE_DIR/runs/<run_id>.json` containing every stage, every tool call, every repair attempt, every token count. Tail the directory or stream to your log aggregator:

```bash
# Stream new runs to stdout in JSON-lines format
tail -F $AEGIS_CACHE_DIR/runs/*.json | jq -c .
```

For structured logging integration, wrap `Aegis.run()` in your service's logger:

```python
result = await aegis.run(goal)
logger.info("aegis_run",
            run_id=result.audit.run_id,
            succeeded=result.audit.succeeded,
            tokens=result.audit.total_tokens,
            duration_ms=result.audit.total_duration_ms,
            repairs=result.audit.repairs,
            risks=[r.id for r in result.audit.risks.risks])
```

### Rate limits & retries

Built-in: each provider adapter retries on 429 / 5xx with exponential backoff (1s → 2s → 4s → 8s → 16s, max 3 retries). For tighter control, set `max_retries=` on the provider:

```python
Aegis(provider=OpenAI(max_retries=5))
```

### Cost control

* **Set `AEGIS_MODEL`** to a cheap model — `gpt-4o-mini`, `claude-haiku-3-5`, `gemini-2.0-flash`. The synthesize stage benefits from quality but is amortized by the harness cache.
* **Tune `MAX_REPAIRS`** if your tasks consistently fail verification — each repair is another execute pass.
* **Pre-warm the cache** at deploy time with your common goal templates so production traffic hits cached harnesses (faster + cheaper).

### Sandbox & security

The in-process sandbox stops the obvious foot-guns (file I/O outside the workspace, shell access, network requests from generated code). It is **not** a hardened security boundary suitable for multi-tenant exposure. For untrusted goals, wrap Aegis in an additional isolation layer (Docker, firejail, gVisor, Firecracker, …).

See [SECURITY.md](https://github.com/loongnianchew/aegis/blob/main/SECURITY.md) for the full threat model and disclosure process.

### Failure modes & circuit-breaking

When `result.audit.succeeded == False`, the verifier rejected the answer. In production:

```python
result = await aegis.run(goal)
if not result.audit.succeeded:
    # The agent's own verifier said "don't ship this." DON'T ship it.
    metrics.incr("aegis.refused", tags={"risks": result.audit.risks.summary()["max_level"]})
    return error_response(reason="answer did not pass verification",
                          run_id=result.audit.run_id)
```

Treating `succeeded=False` as a hard fail is the correct default. Override only when you have a fallback that's actually safer than rejecting.

### Live-test before each release

```bash
# In CI, before promoting a build:
RUN_LIVE_TESTS=1 OPENAI_API_KEY=$OPENAI_KEY \
    pytest tests/integration -v
```

The integration tests use VCR cassettes for replay in CI; record fresh ones before tagging a release if any provider's API has changed.

### Health endpoints

* `GET /health` — proxy health
* `GET /v1/models` — what model is configured

For deeper checks, hit the proxy with a known-good goal and assert `aegis.succeeded == true` in the response.

## Common questions

**Q: Can I run Aegis behind a load balancer?**
Yes — each request is stateless from the proxy's POV. Cache and runs live on shared storage; lookup is read-mostly.

**Q: Does the harness cache shard well?**
Embedding lookup is in-process. For >10K cached harnesses, switch to a Redis backend (planned for v0.5; today, mount the cache dir on a shared volume).

**Q: How do I update the risk catalog without forking?**
Subclass `Pipeline` and override `_load_catalog()`, or contribute the entry upstream — most domain risks are useful across companies.

**Q: Does Aegis ever modify the model's training data / fine-tune?**
No. Aegis only runs inference against the configured model. It never sends training requests, never collects user data centrally, never phones home.

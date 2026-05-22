// Aegis demo client — connects to /api/run over WebSocket, renders the 5 stages live.

const form = document.getElementById("goal-form");
const goalInput = document.getElementById("goal");
const goBtn = document.getElementById("go");
const status = document.getElementById("status");

const analysis = document.getElementById("analysis-content");
const harness = document.getElementById("harness-content");
const exec = document.getElementById("exec-content");

document.querySelectorAll(".example").forEach((b) => {
  b.addEventListener("click", () => {
    goalInput.value = b.dataset.goal;
    goalInput.focus();
  });
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const goal = goalInput.value.trim();
  if (!goal) return;
  reset();
  setStatus("connecting…", "busy");
  goBtn.disabled = true;

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/run`);

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({ goal }));
    setStatus("running…", "busy");
  });

  ws.addEventListener("message", (m) => handleEvent(JSON.parse(m.data)));

  ws.addEventListener("error", () => {
    setStatus("error", "error");
    goBtn.disabled = false;
  });

  ws.addEventListener("close", () => {
    goBtn.disabled = false;
  });
});

function reset() {
  analysis.innerHTML = `<div id="stages"></div><div id="risks"></div>`;
  harness.textContent = "// waiting for synthesis…";
  exec.innerHTML = `<div id="tools"></div><div id="result"></div>`;
}

function handleEvent(e) {
  switch (e.event) {
    case "start":
      addStage("analyze", "busy");
      break;
    case "stage_start":
      addStage(e.name, "busy");
      break;
    case "stage_done":
      addStage(e.name, "done");
      renderStage(e.name, e.data);
      break;
    case "done":
      setStatus(
        e.ok ? `✓ ok · ${e.tokens} tok · ${e.duration_ms.toFixed(0)}ms` : `✗ failed`,
        e.ok ? "ok" : "error"
      );
      break;
    case "error":
      setStatus(`error: ${e.message}`, "error");
      break;
  }
}

function addStage(name, state) {
  const stages = document.getElementById("stages");
  if (!stages) return;
  let pill = stages.querySelector(`[data-stage="${name}"]`);
  if (!pill) {
    pill = document.createElement("span");
    pill.className = "stage-pill";
    pill.dataset.stage = name;
    pill.innerHTML = `<span class="dot"></span>${name}`;
    stages.appendChild(pill);
  }
  pill.classList.remove("busy", "done", "err");
  pill.classList.add(state);
  if (state === "busy") pill.querySelector(".dot")?.replaceWith(spinner());
  else if (state === "done") pill.querySelector(".dot, .spinner")?.replaceWith(dot("✓"));
}

function spinner() {
  const s = document.createElement("span");
  s.className = "spinner";
  return s;
}
function dot(t) {
  const s = document.createElement("span");
  s.textContent = t;
  return s;
}

function renderStage(name, data) {
  if (name === "analyze") {
    const el = document.getElementById("stages");
    const block = document.createElement("div");
    block.style.marginTop = "10px";
    block.style.fontSize = "12px";
    block.style.color = "var(--muted)";
    block.innerHTML = `<div><b>Deliverable:</b> ${escape(data.deliverable || "")}</div>
                       <div><b>Output shape:</b> ${escape(data.output_schema_hint || "")}</div>
                       <div><b>Likely tools:</b> ${(data.needed_tools || []).map(escape).join(", ") || "—"}</div>`;
    el.appendChild(block);
  } else if (name === "assess") {
    const risks = document.getElementById("risks");
    risks.innerHTML = "<h4 style='margin:14px 0 8px;font-size:13px;color:var(--muted);'>Identified risks</h4>";
    (data.risks || []).forEach((r) => {
      const div = document.createElement("div");
      div.className = "risk";
      div.innerHTML = `<div class="row">
        <span class="level ${r.level}">${r.level}</span>
        <span class="id">${escape(r.id)}</span>
      </div>
      <div class="rationale">${escape(r.rationale || "")}</div>`;
      risks.appendChild(div);
    });
  } else if (name === "synthesize") {
    harness.textContent = data.source || "(empty)";
    if (window.hljs) window.hljs.highlightElement(harness);
  } else if (name === "execute") {
    const tools = document.getElementById("tools");
    tools.innerHTML = "";
    (data.tool_calls || []).forEach((tc) => {
      const div = document.createElement("div");
      div.className = "tool-call";
      div.innerHTML = `<span class="name">${escape(tc.name)}</span>(<span class="args">${escape(JSON.stringify(tc.arguments))}</span>) → ${tc.ok ? "✓" : "✗"}`;
      tools.appendChild(div);
    });
    const result = document.getElementById("result");
    result.innerHTML = `<div class="value"><h4 style="margin:10px 0 6px;font-size:13px;color:var(--muted);">Candidate answer</h4><pre>${escape(JSON.stringify(data.value, null, 2))}</pre></div>`;
  } else if (name === "verify") {
    const result = document.getElementById("result");
    const verdict = document.createElement("div");
    verdict.className = "verdict " + (data.passed ? "ok" : "fail");
    verdict.textContent = data.passed
      ? "✓ verifier passed — answer is safe to return"
      : "✗ verifier failed: " + (data.failures || []).join("; ");
    result.appendChild(verdict);
  }
}

function setStatus(text, cls) {
  status.textContent = text;
  status.className = cls || "";
}

function escape(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

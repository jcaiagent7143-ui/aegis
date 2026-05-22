# Security Policy

## Supported versions

Aegis is at v0.4 (beta). The current minor line receives security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: |
| < 0.4   | :x:                |

## Reporting a vulnerability

**Do not file a public GitHub issue for a security report.**

Email **security@aegis-harness.dev** with:

* A description of the vulnerability
* Steps to reproduce (or a proof-of-concept)
* The version you tested (`aegis version`)
* Your name / handle if you'd like credit in the advisory

We aim to:

1. Acknowledge within **48 hours**.
2. Provide a triage assessment within **7 days**.
3. Ship a fix within **30 days** for high-severity issues, sooner for critical.

You may receive a CVE if the issue warrants one.

## Scope

### In scope

* Sandbox escapes in `aegis.synthesize.sandbox` (a generated harness that
  reads or writes files outside the workspace, executes shell commands,
  exfiltrates env vars, escapes the AST validator, etc.).
* Prompt-injection paths that cause Aegis to leak the API key, the
  conversation history, or the workspace contents to the model output.
* Path-traversal in any built-in tool (`read_file`, `write_file`, `list_dir`).
* Auth-handling bugs in `aegis proxy` (e.g. leaking the upstream `Authorization`
  header to clients).
* MCP server vulnerabilities (e.g. tool-call argument injection).
* Dependency vulnerabilities in pinned versions.

### Out of scope

* The model itself producing incorrect or dangerous *content* — that's a
  capability question, not a security one. (Aegis's job is to constrain
  what the model can *do*, not what it can *say*.)
* DoS via expensive prompts — rate limiting is the operator's responsibility.
* Issues that require physical access to the host or root privileges.

## Hardening notes for production deployments

* **Run untrusted goals inside process isolation.** Aegis's in-process sandbox
  stops the obvious foot-guns but is not a hardened security boundary. For
  multi-tenant / public-internet exposure, wrap Aegis in Docker, firejail,
  gVisor, or a similar boundary.
* **Set `AEGIS_WORKSPACE`** to a dedicated directory; the built-in file tools
  refuse paths outside it.
* **Use the proxy's `passthrough` mode sparingly** — it bypasses the harness.
  Only enable for endpoints you control.
* **Rotate API keys** if they ever appear in a log, chat transcript, or
  audit-trail JSON. The audit trail does not log the key, but the model's
  responses can sometimes echo input.

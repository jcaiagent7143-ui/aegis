"""Stage 3 — Synthesize: generate the Python harness code."""

from aegis.synthesize.generator import synthesize
from aegis.synthesize.sandbox import HarnessModule, SandboxError, load_harness, validate_source

__all__ = ["HarnessModule", "SandboxError", "load_harness", "synthesize", "validate_source"]

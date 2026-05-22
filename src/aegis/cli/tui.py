"""Optional live-trace TUI built on Textual.

Activated only if `self-harness[tui]` is installed.
"""

from __future__ import annotations


def run() -> None:
    try:
        import textual  # noqa: F401
    except ImportError as e:
        raise ImportError("Textual TUI requires `pip install self-harness[tui]`") from e
    raise NotImplementedError(
        "Textual TUI is on the v0.2 roadmap — see github.com/jcaiagent7143-ui/aegis/issues"
    )

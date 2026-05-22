"""Built-in tools available to Aegis-driven agents.

Tools are *functions* with a thin metadata wrapper. The Aegis tool registry
discovers them, and the execute stage exposes only the subset the synthesized
harness allows.
"""

from aegis.tools.builtin import (
    fetch_url,
    list_dir,
    read_file,
    run_python_snippet,
    web_search,
    write_file,
)

__all__ = [
    "fetch_url",
    "list_dir",
    "read_file",
    "run_python_snippet",
    "web_search",
    "write_file",
]

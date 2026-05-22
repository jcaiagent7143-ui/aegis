"""Robust JSON extraction from model outputs.

Models sometimes wrap JSON in markdown fences, add prose preamble, or emit
multiple objects. We do a best-effort recovery so the pipeline stays robust.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.+?)```", re.DOTALL)


def extract_json(text: str) -> Any | None:
    """Try increasingly aggressive strategies to pull JSON out of `text`."""
    if not text:
        return None
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from a ```json``` fence
    m = _FENCE.search(text)
    if m:
        body = m.group(1).strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            pass

    # 3. Find the first {...} or [...] balanced span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    span = text[start : i + 1]
                    try:
                        return json.loads(span)
                    except json.JSONDecodeError:
                        break
    return None

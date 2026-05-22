"""OpenAI-compatible REST proxy — drop Aegis in front of any OpenAI client.

Most AI coding tools (Cursor, Continue, Aider, Open WebUI, …) speak OpenAI's
``/v1/chat/completions`` shape. This proxy accepts that shape, runs the
request through the Aegis pipeline, and returns the same shape back. Tools
plug in by changing one URL.

Run with::

    aegis proxy --port 8000

Then in your tool's settings::

    base URL: http://localhost:8000/v1
    API key:  anything (the proxy uses your real key from env)
"""

from aegis.proxy.app import build_app

__all__ = ["build_app"]

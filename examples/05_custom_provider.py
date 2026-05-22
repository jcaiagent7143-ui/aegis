"""Example 05 — Plug your own LLM endpoint into Aegis.

You only need to implement a single method::

    async def complete(self, messages, *, tools=None, temperature=0.2,
                       max_tokens=4096, json_only=False) -> Completion

…and Aegis will use it for every stage (analyze, assess, synthesize, execute).
"""

from __future__ import annotations

import asyncio

import httpx

from aegis import Aegis
from aegis.providers.base import Completion, Message, Tool


class MyProvider:
    name = "my-provider"
    model = "my-model-v1"

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[Tool] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_only: bool = False,
    ) -> Completion:
        payload = {
            "model": self.model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self.base_url}/v1/chat",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            r.raise_for_status()
            data = r.json()
        return Completion(
            text=data["text"],
            tokens_in=data.get("tokens_in", 0),
            tokens_out=data.get("tokens_out", 0),
        )


async def main() -> None:
    provider = MyProvider(base_url="https://my-llm.example", api_key="...")
    aegis = Aegis(provider=provider)
    result = await aegis.run("What's 2 + 2?")
    print(result.to_json())


if __name__ == "__main__":
    asyncio.run(main())

"""Tests for the OpenAI-compatible /v1/chat/completions proxy."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from aegis.providers.mock import Mock
from aegis.proxy.app import build_app

SCRIPTED_PIPELINE = [
    # analyze
    json.dumps(
        {
            "summary": "g",
            "deliverable": "d",
            "output_schema_hint": "x",
            "needed_tools": [],
            "open_questions": [],
        }
    ),
    # assess
    json.dumps({"risks": [], "invariants": [], "suggested_tools": [], "forbidden_tools": []}),
    # synthesize
    "from pydantic import BaseModel\n\nclass Output(BaseModel):\n    value: str = ''\n\n"
    "ALLOWED_TOOLS: list[str] = []\n\ndef verify(output): return []\n",
    # execute
    json.dumps({"value": "the answer"}),
]


@pytest.fixture
def proxy_client(tmp_path, monkeypatch) -> TestClient:
    """Build the proxy with a Mock-backed Aegis instance."""

    # Need to inject the mock provider via the Aegis constructor used inside
    # build_app — easiest: monkeypatch auto_provider so Aegis() picks Mock.
    def _force_mock():
        return Mock(responses=list(SCRIPTED_PIPELINE))

    monkeypatch.setattr("aegis.providers.auto_provider", _force_mock)
    monkeypatch.setattr("aegis.core.aegis.auto_provider", _force_mock, raising=False)

    # Build_app constructs an Aegis with no provider → uses auto_provider
    app = build_app(cache_dir=tmp_path)
    return TestClient(app)


class TestBasics:
    def test_health(self, proxy_client: TestClient):
        r = proxy_client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["provider"] == "mock"

    def test_models_lists_two(self, proxy_client: TestClient):
        r = proxy_client.get("/v1/models")
        assert r.status_code == 200
        body = r.json()
        ids = {m["id"] for m in body["data"]}
        assert "aegis" in ids


class TestAegisMode:
    def test_basic_completion(self, proxy_client: TestClient):
        r = proxy_client.post(
            "/v1/chat/completions",
            json={
                "model": "aegis",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["object"] == "chat.completion"
        # Content is a JSON-encoded version of the value
        content = body["choices"][0]["message"]["content"]
        assert "the answer" in content
        # Aegis-specific metadata included
        assert body["aegis"]["succeeded"] is True
        assert "run_id" in body["aegis"]
        assert "harness_code" in body["aegis"]

    def test_invalid_request_returns_400(self, proxy_client: TestClient):
        r = proxy_client.post("/v1/chat/completions", json={"model": "aegis"})  # no messages
        assert r.status_code == 400

    def test_missing_user_message_returns_400(self, proxy_client: TestClient):
        r = proxy_client.post(
            "/v1/chat/completions",
            json={
                "model": "aegis",
                "messages": [{"role": "system", "content": "you are helpful"}],
            },
        )
        assert r.status_code == 400


class TestMultimodalContent:
    """The OpenAI spec allows content to be a list of {type, text, image_url}."""

    def test_extracts_text_from_list_content(self, proxy_client: TestClient):
        r = proxy_client.post(
            "/v1/chat/completions",
            json={
                "model": "aegis",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "what is 2+2?"},
                            {"type": "image_url", "image_url": {"url": "x"}},  # ignored
                        ],
                    }
                ],
            },
        )
        assert r.status_code == 200


class TestModeHeader:
    def test_per_request_passthrough_via_header(self, tmp_path, monkeypatch):
        """X-Aegis-Mode: passthrough bypasses the pipeline."""

        # passthrough makes a single provider.complete call — script just one response.
        def _make_passthrough_provider():
            return Mock(responses=["just a string answer"])

        monkeypatch.setattr("aegis.providers.auto_provider", _make_passthrough_provider)
        monkeypatch.setattr(
            "aegis.core.aegis.auto_provider", _make_passthrough_provider, raising=False
        )

        app = build_app(cache_dir=tmp_path)
        client = TestClient(app)

        r = client.post(
            "/v1/chat/completions",
            headers={"X-Aegis-Mode": "passthrough"},
            json={
                "model": "aegis",
                "messages": [{"role": "user", "content": "anything"}],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["choices"][0]["message"]["content"] == "just a string answer"
        # No aegis metadata in passthrough mode
        assert "aegis" not in body

    def test_invalid_mode_rejected(self, proxy_client: TestClient):
        r = proxy_client.post(
            "/v1/chat/completions",
            headers={"X-Aegis-Mode": "nope"},
            json={"model": "aegis", "messages": [{"role": "user", "content": "x"}]},
        )
        assert r.status_code == 400


class TestStreaming:
    def test_streaming_emits_sse_chunks_ending_in_done(self, proxy_client: TestClient):
        r = proxy_client.post(
            "/v1/chat/completions",
            json={
                "model": "aegis",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )
        assert r.status_code == 200
        text = r.text
        assert text.startswith("data: ")
        assert "[DONE]" in text
        # Should see at least one delta chunk with content
        assert "delta" in text

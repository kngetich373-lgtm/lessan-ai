"""Tests for OpenAICompatibleAdapter request/response normalization."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.gateway.adapters.openai_compatible import OpenAICompatibleAdapter
from core.gateway.models import (
    GatewayConfig,
    GatewayRecord,
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    GatewayType,
)


def _make_record(gateway_id="test", api_key="sk-test"):
    cfg = GatewayConfig(
        gateway_id=gateway_id,
        gateway_type=GatewayType.OPENAI,
        api_key=api_key,
        base_url="https://api.openai.com/v1",
    )
    return GatewayRecord(config=cfg, status=GatewayStatus.CONNECTED)


class TestOpenAICompatibleAdapterConstruction:
    def test_default_base_url(self):
        adapter = OpenAICompatibleAdapter()
        assert adapter._BASE_URL == "https://api.openai.com/v1"

    def test_custom_base_url(self):
        adapter = OpenAICompatibleAdapter(timeout=30)
        assert adapter._client is not None


class TestRequestNormalization:
    def test_build_payload_basic(self):
        adapter = OpenAICompatibleAdapter()
        request = GatewayRequest(
            prompt="Hello", system="You are helpful", max_tokens=100, temperature=0.7,
        )
        payload = adapter._build_payload(request)
        assert payload["model"] == "gpt-4o-mini"
        assert payload["max_tokens"] == 100
        assert payload["temperature"] == 0.7
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    def test_build_payload_with_model(self):
        adapter = OpenAICompatibleAdapter()
        request = GatewayRequest(prompt="Hi", model="gpt-4o", max_tokens=50)
        payload = adapter._build_payload(request)
        assert payload["model"] == "gpt-4o"

    def test_build_payload_no_system(self):
        adapter = OpenAICompatibleAdapter()
        request = GatewayRequest(prompt="Hi", max_tokens=50)
        payload = adapter._build_payload(request)
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_resolve_base_url_from_config(self):
        adapter = OpenAICompatibleAdapter()
        cfg = GatewayConfig(
            gateway_id="custom",
            gateway_type=GatewayType.CUSTOM_OPENAI,
            base_url="http://localhost:8080/v1",
        )
        record = GatewayRecord(config=cfg)
        assert adapter._resolve_base_url(record) == "http://localhost:8080/v1"

    def test_resolve_base_url_fallback_to_default(self):
        adapter = OpenAICompatibleAdapter()
        cfg = GatewayConfig(gateway_id="g1", gateway_type=GatewayType.OPENAI)
        record = GatewayRecord(config=cfg)
        assert adapter._resolve_base_url(record) == "https://api.openai.com/v1"


class TestOpenAICompatibleChat:
    def test_chat_success(self):
        adapter = OpenAICompatibleAdapter()
        record = _make_record()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from OpenAI"}}],
            "usage": {"total_tokens": 10},
        }

        with patch.object(adapter._client, "post", return_value=mock_response):
            request = GatewayRequest(prompt="Hi", max_tokens=50)
            resp = asyncio_run(adapter.chat(record, request))

        assert resp.success is True
        assert resp.text == "Hello from OpenAI"
        assert resp.provider == "openai_compatible"
        assert resp.tokens_used == 10

    def test_chat_failure_returns_error_response(self):
        adapter = OpenAICompatibleAdapter()
        record = _make_record()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        mock_response.json.return_value = {}

        with patch.object(adapter._client, "post", return_value=mock_response):
            request = GatewayRequest(prompt="Hi", max_tokens=50)
            resp = asyncio_run(adapter.chat(record, request))

        assert resp.success is False
        assert "Unauthorized" in resp.error

    def test_chat_extracts_text_with_no_choices(self):
        adapter = OpenAICompatibleAdapter()
        record = _make_record()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": []}

        with patch.object(adapter._client, "post", return_value=mock_response):
            request = GatewayRequest(prompt="Hi", max_tokens=50)
            resp = asyncio_run(adapter.chat(record, request))

        assert resp.success is True
        assert resp.text == ""


class TestStreaming:
    def test_stream_chat_yields_chunks(self):
        adapter = OpenAICompatibleAdapter()
        record = _make_record()

        chunks = [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
            b'data: [DONE]\n\n',
        ]

        class MockAsyncLinesIterator:
            def __init__(self, items):
                self._items = list(items)
                self._idx = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._idx >= len(self._items):
                    raise StopAsyncIteration
                item = self._items[self._idx]
                self._idx += 1
                return item

            async def aclose(self):
                self._items.clear()

        def mock_aiter_lines():
            return MockAsyncLinesIterator(c.decode() for c in chunks)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.aclose = AsyncMock()

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

        with patch.object(adapter._client, "stream", return_value=mock_stream_ctx):
            request = GatewayRequest(prompt="Hi", max_tokens=50, stream=True)
            results = asyncio_run(_collect(adapter.stream_chat(record, request)))

        assert len(results) == 2
        assert results[0].text == "hello"
        assert results[1].text == " world"


def asyncio_run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

async def _collect(aiter):
    results = []
    async for item in aiter:
        results.append(item)
    return results

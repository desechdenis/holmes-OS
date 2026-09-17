from __future__ import annotations

import json

import httpx
import pytest

from jarvis.providers.memory.soul import SoulMCPClient


@pytest.mark.asyncio
async def test_soul_mcp_client_initializes_then_calls_a_tool() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload["method"] == "initialize":
            message = {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "Soul"}}}
            return httpx.Response(
                200,
                headers={"mcp-session-id": "session_123"},
                text=f"event: message\ndata: {json.dumps(message)}\n",
            )
        message = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"structuredContent": {"result": {"permalink": "holmes/events/mem_1"}}},
        }
        return httpx.Response(
            200,
            text=f"event: message\ndata: {json.dumps(message)}\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = SoulMCPClient("http://soul.local/mcp", http_client=http_client)
        result = await client.call_tool("write_note", {"title": "Test"})

    assert result == {"permalink": "holmes/events/mem_1"}
    assert len(requests) == 2
    assert requests[1].headers["mcp-session-id"] == "session_123"


def test_soul_mcp_client_rejects_an_empty_endpoint() -> None:
    with pytest.raises(ValueError, match="ne peut pas être vide"):
        SoulMCPClient("  ")


def test_soul_mcp_client_keeps_the_result_after_a_progress_notification() -> None:
    progress = {
        "jsonrpc": "2.0",
        "method": "notifications/message",
        "params": {"level": "info", "data": {"msg": "Searching"}},
    }
    result = {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}

    parsed = SoulMCPClient._parse_message(
        f"event: message\ndata: {json.dumps(progress)}\n\n"
        f"event: message\ndata: {json.dumps(result)}\n"
    )

    assert parsed == result

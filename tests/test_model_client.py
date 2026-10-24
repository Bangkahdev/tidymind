from __future__ import annotations

import json
import socket
from typing import Any

import pytest

from fake_ollama import chat_reply, default_responder
from tidymind import model_client
from tidymind.errors import ConfigError, ModelResponseError, ModelUnavailableError
from tidymind.model_client import OllamaClient, parse_suggestions, validate_endpoint
from tidymind.models import FileEntry

ENTRIES = [FileEntry("a.pdf", ".pdf", 10, 111), FileEntry("b.png", ".png", 20, 222)]


def good(n: int = 2) -> str:
    items = [{"id": i, "category": "Documents", "target_name": f"n{i}.pdf", "reason": "r"} for i in range(n)]
    return json.dumps({"suggestions": items})


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:11434", "http://localhost:11434/", "http://[::1]:11434", "https://127.0.0.2"],
)
def test_loopback_endpoints_accepted(url: str) -> None:
    assert validate_endpoint(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com", "http://192.168.1.5:11434", "http://10.0.0.1", "http://0.0.0.0",
        "ftp://127.0.0.1", "127.0.0.1:11434", "http://", "http://user:pw@127.0.0.1",
        "http://127.0.0.1:notaport", "http://localhost.evil.com", "http://127.0.0.1.evil.com",
    ],
)  # fmt: skip
def test_non_loopback_endpoints_rejected(url: str) -> None:
    with pytest.raises(ConfigError):
        validate_endpoint(url)


def test_parse_ok_and_reason_clipped() -> None:
    long_reason = "x" * 500
    payload = json.dumps(
        {"suggestions": [{"id": 0, "category": "Other", "target_name": "a.pdf", "reason": long_reason}]}
    )
    (suggestion,) = parse_suggestions(payload, 1)
    assert suggestion.category == "Other" and len(suggestion.reason) == 200


def test_parse_orders_by_id() -> None:
    items = [
        {"id": 1, "category": "Images", "target_name": "b.png", "reason": ""},
        {"id": 0, "category": "Documents", "target_name": "a.pdf", "reason": ""},
    ]
    result = parse_suggestions(json.dumps({"suggestions": items}), 2)
    assert [s.category for s in result] == ["Documents", "Images"]


def _item(**over: Any) -> dict[str, Any]:
    base = {"id": 0, "category": "Documents", "target_name": "a.pdf", "reason": "r"}
    base.update(over)
    return base


BAD = [
    "", "   ", "not json", "[]", "null", '{"suggestions": []}', '{"other": []}',
    json.dumps({"suggestions": [_item()], "extra": 1}),
    json.dumps({"suggestions": "x"}),
    json.dumps({"suggestions": [1]}),
    json.dumps({"suggestions": [{"id": 0}]}),
    json.dumps({"suggestions": [{**_item(), "extra": 1}]}),
    json.dumps({"suggestions": [_item(id=True)]}),
    json.dumps({"suggestions": [_item(id="0")]}),
    json.dumps({"suggestions": [_item(id=5)]}),
    json.dumps({"suggestions": [_item(id=-1)]}),
    json.dumps({"suggestions": [_item(category="Videos")]}),
    json.dumps({"suggestions": [_item(category=3)]}),
    json.dumps({"suggestions": [_item(target_name="")]}),
    json.dumps({"suggestions": [_item(target_name="  ")]}),
    json.dumps({"suggestions": [_item(target_name=7)]}),
    json.dumps({"suggestions": [_item(target_name="a" * 256)]}),
    json.dumps({"suggestions": [_item(reason=None)]}),
]  # fmt: skip


@pytest.mark.parametrize("content", BAD)
def test_parse_rejects_bad_output(content: str) -> None:
    with pytest.raises(ModelResponseError):
        parse_suggestions(content, 1)


def test_parse_rejects_duplicate_ids() -> None:
    items = [_item(), _item()]
    with pytest.raises(ModelResponseError, match="duplicate"):
        parse_suggestions(json.dumps({"suggestions": items}), 2)


def test_request_contains_only_minimal_metadata() -> None:
    client = OllamaClient(transport=lambda *_: {})
    request = client.build_request(ENTRIES)
    user = json.loads(request["messages"][-1]["content"])
    assert user == {
        "files": [
            {"id": 0, "name": "a.pdf", "extension": ".pdf", "size_bytes": 10},
            {"id": 1, "name": "b.png", "extension": ".png", "size_bytes": 20},
        ]
    }
    assert "111" not in json.dumps(request)  # mtime is never sent
    assert request["stream"] is False and request["options"] == {"temperature": 0}


def test_suggest_batches() -> None:
    calls: list[int] = []

    def transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        calls.append(len(json.loads(payload["messages"][-1]["content"])["files"]))
        assert url.endswith("/api/chat") and timeout == 7
        return default_responder(payload)[1]

    client = OllamaClient(batch_size=2, timeout=7, transport=transport)
    entries = [FileEntry(f"f{i}.pdf", ".pdf", i, i) for i in range(5)]
    assert len(client.suggest(entries)) == 5
    assert calls == [2, 2, 1]


def test_retry_is_bounded_then_fails_closed() -> None:
    calls = []

    def transport(*_: object) -> dict[str, Any]:
        calls.append(1)
        return chat_reply("garbage")

    client = OllamaClient(max_attempts=3, transport=transport)
    with pytest.raises(ModelResponseError, match="3 attempts"):
        client.suggest(ENTRIES)
    assert len(calls) == 3


def test_retry_recovers() -> None:
    replies = iter([chat_reply("garbage"), chat_reply(good())])
    client = OllamaClient(transport=lambda *_: next(replies))
    assert len(client.suggest(ENTRIES)) == 2


def test_missing_message_content_counts_as_bad_response() -> None:
    client = OllamaClient(max_attempts=1, transport=lambda *_: {"message": {"content": None}})
    with pytest.raises(ModelResponseError, match="no message content"):
        client.suggest(ENTRIES)
    client = OllamaClient(max_attempts=1, transport=lambda *_: {})
    with pytest.raises(ModelResponseError):
        client.suggest(ENTRIES)


def test_client_rejects_non_loopback_at_construction() -> None:
    with pytest.raises(ConfigError):
        OllamaClient(endpoint="http://example.com")


def test_batch_and_attempt_minimums() -> None:
    client = OllamaClient(batch_size=0, max_attempts=0, transport=lambda *_: {})
    assert client.batch_size == 1 and client.max_attempts == 1


# --- real HTTP transport against the fake server -------------------------------------------


def test_http_success(fake_ollama: Any) -> None:
    server = fake_ollama()
    client = OllamaClient(endpoint=server.url)
    assert len(client.suggest(ENTRIES)) == 2
    assert server.requests[0]["model"] == model_client.DEFAULT_MODEL


def test_http_model_missing_404(fake_ollama: Any) -> None:
    server = fake_ollama(lambda r: (404, {"error": "model not found"}))
    with pytest.raises(ModelUnavailableError, match="ollama pull"):
        OllamaClient(endpoint=server.url).suggest(ENTRIES)


def test_http_server_error(fake_ollama: Any) -> None:
    server = fake_ollama(lambda r: (500, {"error": "boom"}))
    with pytest.raises(ModelUnavailableError, match="HTTP 500"):
        OllamaClient(endpoint=server.url).suggest(ENTRIES)


def test_http_invalid_json_and_wrong_shape(fake_ollama: Any) -> None:
    server = fake_ollama(lambda r: (200, b"<html>"))
    with pytest.raises(ModelResponseError, match="invalid JSON"):
        OllamaClient(endpoint=server.url).suggest(ENTRIES)
    server = fake_ollama(lambda r: (200, [1, 2]))
    with pytest.raises(ModelResponseError, match="unexpected payload"):
        OllamaClient(endpoint=server.url).suggest(ENTRIES)


def test_http_oversized_response(fake_ollama: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_client, "MAX_RESPONSE_BYTES", 10)
    server = fake_ollama()
    with pytest.raises(ModelResponseError, match="too large"):
        OllamaClient(endpoint=server.url).suggest(ENTRIES)


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_http_connection_refused() -> None:
    client = OllamaClient(endpoint=f"http://127.0.0.1:{_closed_port()}", timeout=2)
    with pytest.raises(ModelUnavailableError, match="Cannot reach Ollama"):
        client.suggest(ENTRIES)


def test_http_timeout(fake_ollama: Any) -> None:
    import time

    def slow(request: dict[str, Any]) -> tuple[int, Any]:
        time.sleep(1.0)
        return default_responder(request)

    server = fake_ollama(slow)
    with pytest.raises(ModelUnavailableError, match="timed out"):
        OllamaClient(endpoint=server.url, timeout=0.2).suggest(ENTRIES)


def test_generic_os_error_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Opener:
        def open(self, *a: object, **k: object) -> None:
            raise ConnectionResetError("reset")

    monkeypatch.setattr(model_client.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(ModelUnavailableError, match="connection error"):
        model_client._http_transport("http://127.0.0.1:1/api/chat", {}, 1)

"""Deterministic Ollama-compatible test double (loopback only, no model, no network)."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

Responder = Callable[[dict[str, Any]], tuple[int, Any]]

_EXTENSION_CATEGORY = {
    ".pdf": "Documents", ".docx": "Documents", ".txt": "Documents", ".md": "Documents",
    ".png": "Images", ".jpg": "Images", ".jpeg": "Images", ".gif": "Images",
    ".zip": "Archives", ".tar": "Archives", ".gz": "Archives", ".7z": "Archives",
    ".exe": "Installers", ".msi": "Installers", ".deb": "Installers", ".dmg": "Installers",
}  # fmt: skip


def rule_based_suggestions(request: dict[str, Any]) -> dict[str, Any]:
    """Valid, schema-conforming suggestions derived from extensions only."""
    files = json.loads(request["messages"][-1]["content"])["files"]
    return {
        "suggestions": [
            {
                "id": f["id"],
                "category": _EXTENSION_CATEGORY.get(f["extension"], "Other"),
                "target_name": f["name"],
                "reason": "Chosen from the file extension.",
            }
            for f in files
        ]
    }


def chat_reply(content: str) -> dict[str, Any]:
    return {"message": {"role": "assistant", "content": content}, "done": True}


def default_responder(request: dict[str, Any]) -> tuple[int, Any]:
    return 200, chat_reply(json.dumps(rule_based_suggestions(request)))


class FakeOllama:
    def __init__(self, responder: Responder = default_responder) -> None:
        self.responder = responder
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                request = json.loads(self.rfile.read(length))
                outer.requests.append(request)
                status, body = outer.responder(request)
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> FakeOllama:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()

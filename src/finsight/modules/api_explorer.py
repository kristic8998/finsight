"""API Explorer — a lightweight REST client for testing FinTech services.

Pure logic, no UI. Wraps :mod:`requests` with request/response value
objects, response-time tracking, JSON pretty-printing, and a capped
in-session history. The network call is isolated behind an injectable
session, so the whole ``send`` path is unit-tested offline with a fake
transport. The UI layer runs :meth:`ApiExplorer.send` on a worker
thread — this module never blocks or touches Tk.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import requests

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class ApiRequest:
    """A request the user has composed in the Explorer."""

    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: str = ""
    timeout: float = 30.0

    def normalized_method(self) -> str:
        return self.method.strip().upper()

    def validate(self) -> None:
        if self.normalized_method() not in HTTP_METHODS:
            raise ValueError(f"unsupported HTTP method: {self.method!r}")
        url = self.url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")


@dataclass
class ApiResponse:
    """The outcome of a send: an HTTP response, or a transport error."""

    ok: bool
    status_code: int | None
    reason: str
    elapsed_ms: float
    size_bytes: int
    content_type: str
    headers: dict[str, str]
    text: str
    error: str | None = None

    def pretty_body(self) -> str:
        """Response body, pretty-printed when it is JSON."""
        return format_json(self.text)

    def status_line(self) -> str:
        if self.error is not None:
            return f"ERROR — {self.error}"
        return (
            f"{self.status_code} {self.reason} · {self.elapsed_ms:.0f} ms · "
            f"{_human_size(self.size_bytes)}"
        )


class ApiExplorer:
    """Sends requests and remembers the recent ones (this session only)."""

    def __init__(self, *, session: Any | None = None, max_history: int = 50) -> None:
        self._session = session if session is not None else requests.Session()
        self._history: deque[tuple[ApiRequest, ApiResponse]] = deque(maxlen=max_history)

    @property
    def history(self) -> list[tuple[ApiRequest, ApiResponse]]:
        return list(self._history)

    def send(self, request: ApiRequest) -> ApiResponse:
        """Perform the request, timing it and never raising on HTTP errors."""
        request.validate()
        method = request.normalized_method()
        data = request.body.encode("utf-8") if (request.body and method in _BODY_METHODS) else None

        start = time.perf_counter()
        try:
            raw = self._session.request(
                method=method,
                url=request.url.strip(),
                headers=request.headers or None,
                params=request.params or None,
                data=data,
                timeout=request.timeout,
            )
        except requests.exceptions.RequestException as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            response = ApiResponse(
                ok=False,
                status_code=None,
                reason="",
                elapsed_ms=elapsed_ms,
                size_bytes=0,
                content_type="",
                headers={},
                text="",
                error=f"{type(exc).__name__}: {exc}",
            )
            self._history.append((request, response))
            return response

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        content = getattr(raw, "content", b"") or b""
        headers = {str(k): str(v) for k, v in dict(getattr(raw, "headers", {})).items()}
        response = ApiResponse(
            ok=bool(getattr(raw, "ok", 200 <= (raw.status_code or 0) < 400)),
            status_code=raw.status_code,
            reason=getattr(raw, "reason", "") or "",
            elapsed_ms=elapsed_ms,
            size_bytes=len(content),
            content_type=headers.get("Content-Type", ""),
            headers=headers,
            text=getattr(raw, "text", ""),
        )
        self._history.append((request, response))
        return response


# ---- helpers --------------------------------------------------------------
def parse_headers(text: str) -> dict[str, str]:
    """Parse ``Key: Value`` lines into a dict; blanks and ``#`` are skipped."""
    headers: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key:
            headers[key] = value.strip()
    return headers


def parse_params(text: str) -> dict[str, str]:
    """Parse ``key=value`` lines (or a ``a=1&b=2`` query string) into a dict."""
    params: dict[str, str] = {}
    normalized = text.replace("&", "\n")
    for line in normalized.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            params[key] = value.strip()
    return params


def format_json(text: str) -> str:
    """Pretty-print ``text`` if it is valid JSON, else return it unchanged."""
    stripped = text.strip()
    if not stripped:
        return text
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return text
    return json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=False)


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"

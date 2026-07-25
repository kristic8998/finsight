"""Tests for the API Explorer client (offline — fake transport)."""

from __future__ import annotations

import pytest
import requests

from finsight.modules.api_explorer import (
    ApiExplorer,
    ApiRequest,
    format_json,
    parse_headers,
    parse_params,
)


class _FakeResponse:
    def __init__(self, status=200, reason="OK", body=b'{"ok": true}', headers=None):
        self.status_code = status
        self.reason = reason
        self.ok = 200 <= status < 400
        self.content = body
        self.text = body.decode("utf-8")
        self.headers = headers or {"Content-Type": "application/json"}


class _FakeSession:
    """Records the last request and returns a canned response."""

    def __init__(self, response=None, raise_exc=None):
        self._response = response or _FakeResponse()
        self._raise = raise_exc
        self.last_kwargs: dict | None = None

    def request(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise is not None:
            raise self._raise
        return self._response


class TestHelpers:
    def test_format_json_pretty_prints(self):
        assert format_json('{"b":1,"a":2}') == '{\n  "b": 1,\n  "a": 2\n}'

    def test_format_json_passthrough_on_invalid(self):
        assert format_json("not json") == "not json"

    def test_parse_headers(self):
        parsed = parse_headers("Accept: application/json\n# comment\n\nX-Env: prod")
        assert parsed == {"Accept": "application/json", "X-Env": "prod"}

    def test_parse_params_lines_and_querystring(self):
        assert parse_params("page=1\nsize=50") == {"page": "1", "size": "50"}
        assert parse_params("a=1&b=2") == {"a": "1", "b": "2"}


class TestRequestValidation:
    def test_rejects_bad_method(self):
        with pytest.raises(ValueError):
            ApiRequest(method="FETCH", url="https://x.test").validate()

    def test_rejects_non_http_url(self):
        with pytest.raises(ValueError):
            ApiRequest(method="GET", url="ftp://x.test").validate()

    def test_accepts_valid(self):
        ApiRequest(method="post", url="https://x.test").validate()  # no raise


class TestSend:
    def test_successful_response_is_parsed(self):
        api = ApiExplorer(session=_FakeSession())
        response = api.send(ApiRequest(method="GET", url="https://api.test/ping"))
        assert response.ok is True
        assert response.status_code == 200
        assert response.elapsed_ms >= 0.0
        assert response.size_bytes == len(b'{"ok": true}')
        assert '"ok"' in response.pretty_body()
        assert len(api.history) == 1

    def test_body_only_sent_for_body_methods(self):
        session = _FakeSession()
        api = ApiExplorer(session=session)
        api.send(ApiRequest(method="GET", url="https://api.test", body='{"x":1}'))
        assert session.last_kwargs["data"] is None  # GET drops the body
        api.send(ApiRequest(method="POST", url="https://api.test", body='{"x":1}'))
        assert session.last_kwargs["data"] == b'{"x":1}'

    def test_transport_error_becomes_response(self):
        session = _FakeSession(raise_exc=requests.exceptions.ConnectionError("boom"))
        api = ApiExplorer(session=session)
        response = api.send(ApiRequest(method="GET", url="https://api.test"))
        assert response.ok is False
        assert response.status_code is None
        assert "ConnectionError" in (response.error or "")
        assert len(api.history) == 1  # failures are still recorded

    def test_history_is_capped(self):
        api = ApiExplorer(session=_FakeSession(), max_history=2)
        for _ in range(5):
            api.send(ApiRequest(method="GET", url="https://api.test"))
        assert len(api.history) == 2

    def test_status_line_reports_time(self):
        api = ApiExplorer(session=_FakeSession(_FakeResponse(status=201, reason="Created")))
        response = api.send(ApiRequest(method="POST", url="https://api.test", body="{}"))
        assert "201" in response.status_line()
        assert "ms" in response.status_line()

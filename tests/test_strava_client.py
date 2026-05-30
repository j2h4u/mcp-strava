"""Focused tests for StravaClient facade (D-08).

All tests inject a fake transport — no real network calls, no real credentials
required at construction or test time.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from mcp_strava.adapters.strava.client import StravaClient
from mcp_strava.adapters.strava.types import StravaRateInfo, StravaResponse, StravaUnavailable


class _FakeTransport:
    """Minimal transport stub: pre-configured with a single response or error."""

    def __init__(self, response=None, raises: StravaUnavailable | None = None) -> None:
        self._response = response
        self._raises = raises
        self.fetched_paths: list[str] = []
        # Stub token_provider for refresh_token tests.
        self.token_provider = SimpleNamespace(refresh=self._refresh_token)
        self._refresh_result: str | None = None
        self._refresh_raises: StravaUnavailable | None = None

    def fetch(self, path: str) -> StravaResponse:
        self.fetched_paths.append(path)
        if self._raises is not None:
            raise self._raises
        return self._response

    def _refresh_token(self) -> str:
        if self._refresh_raises is not None:
            raise self._refresh_raises
        return self._refresh_result or "new_access_token"

    def configure_refresh(self, result: str | None = None, raises: StravaUnavailable | None = None) -> None:
        self._refresh_result = result
        self._refresh_raises = raises


def _make_response(data: Any, rate_dict: dict | None = None) -> StravaResponse:
    rate_info = StravaRateInfo(
        overall_short=(5, 100),
        overall_long=(50, 1000),
    )
    return StravaResponse(data=data, rate_info=rate_info, status=200)


# ---------------------------------------------------------------------------
# api_request — happy path
# ---------------------------------------------------------------------------


def test_api_request_returns_data_and_rate_headers() -> None:
    payload = {"id": 42, "name": "Morning Run"}
    transport = _FakeTransport(response=_make_response(payload))
    client = StravaClient(transport=transport)

    data, rate_headers = client.api_request("/activities/42")

    assert data == payload
    assert transport.fetched_paths == ["/activities/42"]
    # rate_headers must be a dict (from StravaRateInfo.as_dict())
    assert isinstance(rate_headers, dict)
    assert "usage_15min" in rate_headers


# ---------------------------------------------------------------------------
# api_request — rate-limited sentinel
# ---------------------------------------------------------------------------


def test_api_request_returns_sentinel_on_rate_limited() -> None:
    transport = _FakeTransport(raises=StravaUnavailable("rate_limited"))
    client = StravaClient(transport=transport)

    data, rate_headers = client.api_request("/athlete/activities")

    assert data == {"_rate_limited": True, "_retry_after": None}
    assert rate_headers == {}


# ---------------------------------------------------------------------------
# api_request — non-rate-limit error raises RuntimeError
# ---------------------------------------------------------------------------


def test_api_request_raises_runtime_error_on_network_unstable() -> None:
    transport = _FakeTransport(raises=StravaUnavailable("network_unstable"))
    client = StravaClient(transport=transport)

    with pytest.raises(RuntimeError, match="network_unstable"):
        client.api_request("/athlete/activities")


# ---------------------------------------------------------------------------
# refresh_token — happy path
# ---------------------------------------------------------------------------


def test_refresh_token_returns_new_access_token() -> None:
    transport = _FakeTransport()
    transport.configure_refresh(result="refreshed_token_abc")
    client = StravaClient(transport=transport)

    token = client.refresh_token()

    assert token == "refreshed_token_abc"


# ---------------------------------------------------------------------------
# refresh_token — failure raises RuntimeError without leaking client_secret
# ---------------------------------------------------------------------------


def test_refresh_token_raises_runtime_error_on_failure() -> None:
    transport = _FakeTransport()
    transport.configure_refresh(raises=StravaUnavailable("token_unavailable"))
    client = StravaClient(transport=transport)

    with pytest.raises(RuntimeError, match="token_unavailable"):
        client.refresh_token()


def test_refresh_token_error_does_not_contain_secret() -> None:
    """Error message must not leak client credentials."""
    transport = _FakeTransport()
    transport.configure_refresh(raises=StravaUnavailable("token_unavailable"))
    client = StravaClient(transport=transport)

    try:
        client.refresh_token()
    except RuntimeError as exc:
        assert "secret" not in str(exc).lower()
        assert "client_secret" not in str(exc)

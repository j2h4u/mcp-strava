import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


class FakeClock:
    def __init__(self, now: float = 1_700_000_000.0):
        self._now = now

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class FakeSleeper:
    def __init__(self, clock: FakeClock | None = None):
        self.clock = clock
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if self.clock is not None:
            self.clock.advance(seconds)


class FakeHttpResponse:
    def __init__(self, status: int, body: dict | list, headers: dict[str, str] | None = None):
        self.status = status
        self.code = status
        self.headers = headers or {}
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStravaHttp:
    def __init__(self, script):
        self.script = list(script)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request, timeout=30):
        self.requests.append(request)
        next_item = self.script.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item


class FakeTokenRefreshTransport:
    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls = 0
        self.refresh_tokens_seen: list[str] = []

    def refresh_tokens(self, refresh_token: str):
        from mcp_strava.adapters.strava import RefreshedTokens, StravaUnavailable

        self.calls += 1
        self.refresh_tokens_seen.append(refresh_token)
        if self.script:
            next_item = self.script.pop(0)
            if isinstance(next_item, BaseException):
                raise next_item
            return next_item
        return RefreshedTokens(
            access_token="access-new",
            refresh_token="refresh-new",
            expires_at=9_999_999_999,
        )


def _write_token_file(path: Path, *, access: str = "access-old", refresh: str = "refresh-old", expires: int = 0) -> None:
    path.write_text(
        "\n".join(
            [
                "STRAVA_CLIENT_ID=client-id",
                "STRAVA_CLIENT_SECRET=client-secret",
                f"STRAVA_ACCESS_TOKEN={access}",
                f"STRAVA_REFRESH_TOKEN={refresh}",
                f"STRAVA_EXPIRES_AT={expires}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_token_provider_is_single_writer_per_D10_STRAVA_02(tmp_path):
    from mcp_strava.adapters.strava import FileTokenProvider

    token_path = tmp_path / ".env"
    _write_token_file(token_path, expires=0)
    clock = FakeClock()
    refresh = FakeTokenRefreshTransport()
    providers = [
        FileTokenProvider(token_path, refresh_transport=refresh, clock=clock),
        FileTokenProvider(token_path, refresh_transport=refresh, clock=clock),
    ]
    barrier = threading.Barrier(2)
    results: list[str] = []

    def _worker(provider):
        barrier.wait()
        results.append(provider.refresh_if_needed())

    threads = [threading.Thread(target=_worker, args=(provider,)) for provider in providers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == ["access-new", "access-new"]
    assert refresh.calls == 1
    assert oct(token_path.stat().st_mode & 0o777) == "0o600"


def test_token_provider_atomic_write_keeps_original_on_replace_failure_per_D10(tmp_path, monkeypatch):
    from mcp_strava.adapters.strava import FileTokenProvider

    token_path = tmp_path / ".env"
    _write_token_file(token_path, access="original", refresh="refresh-old", expires=0)
    original = token_path.read_text(encoding="utf-8")
    provider = FileTokenProvider(token_path, refresh_transport=FakeTokenRefreshTransport(), clock=FakeClock())

    def _broken_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr("os.replace", _broken_replace)

    with pytest.raises(OSError):
        provider.refresh()

    assert token_path.read_text(encoding="utf-8") == original


def test_rate_limit_policy_parses_read_headers_and_waits_per_D14():
    from mcp_strava.adapters.strava import RateLimitPolicy

    policy = RateLimitPolicy()
    policy.update_from_headers(
        {
            "X-RateLimit-Limit": "200,2000",
            "X-RateLimit-Usage": "10,20",
            "X-ReadRateLimit-Limit": "100,1000",
            "X-ReadRateLimit-Usage": "100,40",
        }
    )

    decision = policy.decide_next_call(1_700_000_123.0)

    assert decision.status == "wait"
    assert decision.wait_until is not None


def test_rate_limit_policy_daily_exhaustion_per_D14():
    from mcp_strava.adapters.strava import RateLimitPolicy

    policy = RateLimitPolicy()
    policy.update_from_headers(
        {
            "X-RateLimit-Limit": "200,2000",
            "X-RateLimit-Usage": "10,20",
            "X-ReadRateLimit-Limit": "100,1000",
            "X-ReadRateLimit-Usage": "10,1000",
        }
    )

    decision = policy.decide_next_call(1_700_000_123.0)

    assert decision.status == "exhausted"
    assert decision.reason == "rate_limited"


def test_fetch_returns_typed_response_per_STRAVA_01_TEST_02():
    from mcp_strava.adapters.strava import RateLimitPolicy, StravaTransport

    class TokenProvider:
        def access_token(self):
            return "access-secret"

        def refresh(self):
            return "access-new"

    http = FakeStravaHttp(
        [
            FakeHttpResponse(
                200,
                {"ok": True},
                {
                    "X-RateLimit-Limit": "200,2000",
                    "X-RateLimit-Usage": "1,2",
                    "X-ReadRateLimit-Limit": "100,1000",
                    "X-ReadRateLimit-Usage": "1,2",
                },
            )
        ]
    )

    response = StravaTransport(
        TokenProvider(),
        RateLimitPolicy(),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        http=http,
    ).fetch("/athlete")

    assert response.status == 200
    assert response.data == {"ok": True}
    assert response.rate_info.read_short == (1, 100)


def test_fetch_401_consumes_one_data_attempt_for_refresh_retry_per_D18():
    from mcp_strava.adapters.strava import RateLimitPolicy, StravaTransport

    class TokenProvider:
        def __init__(self):
            self.refresh_calls = 0
            self.token = "access-old"

        def access_token(self):
            return self.token

        def refresh(self):
            self.refresh_calls += 1
            self.token = "access-new"
            return self.token

    token_provider = TokenProvider()
    http = FakeStravaHttp(
        [
            urllib.error.HTTPError("url", 401, "unauthorized", {}, None),
            FakeHttpResponse(200, {"ok": True}),
        ]
    )

    response = StravaTransport(
        token_provider,
        RateLimitPolicy(),
        clock=FakeClock(),
        sleeper=FakeSleeper(),
        http=http,
    ).fetch("/athlete")

    assert response.data == {"ok": True}
    assert token_provider.refresh_calls == 1
    assert len(http.requests) == 2


def test_data_transport_does_not_retry_on_token_unavailable_per_D18():
    from mcp_strava.adapters.strava import RateLimitPolicy, StravaTransport, StravaUnavailable

    class TokenProvider:
        def access_token(self):
            return "access-secret"

        def refresh(self):
            raise StravaUnavailable("token_unavailable")

    http = FakeStravaHttp([urllib.error.HTTPError("url", 401, "unauthorized", {}, None)])

    with pytest.raises(StravaUnavailable) as exc_info:
        StravaTransport(
            TokenProvider(),
            RateLimitPolicy(),
            clock=FakeClock(),
            sleeper=FakeSleeper(),
            http=http,
        ).fetch("/athlete")

    assert exc_info.value.reason == "token_unavailable"
    assert len(http.requests) == 1


def test_token_refresh_transport_owns_its_own_retry_budget_per_D18():
    from mcp_strava.adapters.strava import RefreshedTokens, TokenRefreshTransport

    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    responses = [
        urllib.error.URLError("temporary-1"),
        urllib.error.URLError("temporary-2"),
        FakeHttpResponse(200, {"access_token": "access-new", "refresh_token": "refresh-new", "expires_at": 999}),
    ]
    http = FakeStravaHttp(responses)

    tokens = TokenRefreshTransport("client", "secret", clock=clock, sleeper=sleeper, http=http).refresh_tokens(
        "refresh-secret"
    )

    assert isinstance(tokens, RefreshedTokens)
    assert tokens.access_token == "access-new"
    assert sleeper.sleeps == [2, 8]
    assert len(http.requests) == 3


def test_token_refresh_transport_4xx_is_token_unavailable_per_D18():
    from mcp_strava.adapters.strava import StravaUnavailable, TokenRefreshTransport

    with pytest.raises(StravaUnavailable) as exc_info:
        TokenRefreshTransport(
            "client",
            "secret",
            clock=FakeClock(),
            sleeper=FakeSleeper(),
            http=FakeStravaHttp([urllib.error.HTTPError("url", 400, "bad request", {}, None)]),
        ).refresh_tokens("refresh-secret")

    assert exc_info.value.reason == "token_unavailable"


def test_tokens_never_appear_in_errors_or_output_per_D10_D18(capsys):
    from mcp_strava.adapters.strava import RateLimitPolicy, StravaTransport, StravaUnavailable

    access_token = "access-secret-literal"
    refresh_token = "refresh-secret-literal"

    class TokenProvider:
        def access_token(self):
            return access_token

        def refresh(self):
            raise StravaUnavailable("token_unavailable")

    with pytest.raises(StravaUnavailable):
        StravaTransport(
            TokenProvider(),
            RateLimitPolicy(),
            clock=FakeClock(),
            sleeper=FakeSleeper(),
            http=FakeStravaHttp([urllib.error.HTTPError("url", 401, "unauthorized", {}, None)]),
        ).fetch("/athlete")

    captured = capsys.readouterr()
    rendered = f"{captured.out}\n{captured.err}"
    assert access_token not in str(rendered)
    assert refresh_token not in str(rendered)

"""Strava data-fetch transport with injectable retry collaborators."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable

from mcp_strava.adapters.strava.rate_limit import RateLimitPolicy
from mcp_strava.adapters.strava.types import Clock, Sleeper, StravaResponse, StravaUnavailable


class StravaTransport:
    def __init__(
        self,
        token_provider,
        policy: RateLimitPolicy,
        clock: Clock,
        sleeper: Sleeper,
        http: Callable | None = None,
        base_url: str = "https://www.strava.com/api/v3",
    ) -> None:
        self.token_provider = token_provider
        self.policy = policy
        self.clock = clock
        self.sleeper = sleeper
        self.http = http
        self.base_url = base_url.rstrip("/")

    def fetch(self, path: str) -> StravaResponse:
        attempts = 0
        refreshed = False
        last_reason = "network_unstable"

        while attempts < 3:
            decision = self.policy.decide_next_call(self.clock.now())
            if decision.status == "exhausted":
                raise StravaUnavailable(decision.reason or "rate_limited")
            if decision.status == "wait" and decision.wait_until is not None:
                self.sleeper.sleep(max(0, decision.wait_until - self.clock.now()))

            request = self._build_request(path, self.token_provider.access_token())
            try:
                response = self._http(request)
                status = int(getattr(response, "status", getattr(response, "code", 200)))
                data = self._read_json(response)
                rate_info = self.policy.update_from_headers(getattr(response, "headers", {}) or {})
                return StravaResponse(data=data, rate_info=rate_info, status=status)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    if refreshed:
                        raise StravaUnavailable("token_unavailable") from exc
                    try:
                        self.token_provider.refresh()
                    except StravaUnavailable as token_exc:
                        if token_exc.reason == "token_unavailable":
                            raise
                        raise
                    refreshed = True
                    attempts += 1
                    continue
                if exc.code == 429:
                    last_reason = "rate_limited"
                    self.policy.mark_rate_limited()
                    attempts += 1
                    if attempts >= 3:
                        break
                    self.sleeper.sleep(self._retry_after_seconds(exc))
                    continue
                if exc.code == 404:
                    raise
                last_reason = "network_unstable"
                attempts += 1
                if attempts >= 3:
                    break
                self.sleeper.sleep([1, 5, 30][attempts - 1])
            except (TimeoutError, urllib.error.URLError, OSError):
                last_reason = "network_unstable"
                attempts += 1
                if attempts >= 3:
                    break
                self.sleeper.sleep([1, 5, 30][attempts - 1])
                continue

        raise StravaUnavailable(last_reason)

    def _build_request(self, path: str, token: str) -> urllib.request.Request:
        url = f"{self.base_url}/{path.lstrip('/')}"
        return urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    def _http(self, request: urllib.request.Request):
        opener = self.http or urllib.request.urlopen
        return opener(request, timeout=30)

    @staticmethod
    def _read_json(response):
        if hasattr(response, "__enter__"):
            with response as opened:
                return json.loads(opened.read().decode())
        return json.loads(response.read().decode())

    @staticmethod
    def _retry_after_seconds(exc: urllib.error.HTTPError) -> int:
        retry_after = None
        headers = getattr(exc, "headers", None)
        if headers:
            retry_after = headers.get("Retry-After")
        try:
            return int(retry_after) + 1 if retry_after is not None else 15
        except TypeError, ValueError:
            return 15

"""Strava data-fetch transport with injectable retry collaborators."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from http import HTTPStatus
from typing import cast

from mcp_strava.adapters.strava.rate_limit import RateLimitPolicy
from mcp_strava.adapters.strava.types import Clock, RefreshReason, Sleeper, StravaResponse, StravaUnavailableError
from mcp_strava.constants import Config


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

        while attempts < Config.Transport.MAX_RETRIES:
            decision = self.policy.decide_next_call(self.clock.now())
            if decision.status == "exhausted":
                raise StravaUnavailableError(decision.reason or "rate_limited", detail=self.policy.rate_info.as_dict())
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
                attempts, last_reason, refreshed = self._handle_http_error(exc, attempts, last_reason, refreshed)
                if attempts >= Config.Transport.MAX_RETRIES:
                    break
            except TimeoutError, urllib.error.URLError, OSError:
                last_reason = "network_unstable"
                attempts += 1
                if attempts >= Config.Transport.MAX_RETRIES:
                    break
                self.sleeper.sleep([1, 5, 30][attempts - 1])
                continue

        # Attach the rate snapshot when we give up because of rate limiting, so
        # the operator log shows the usage/limit at the moment of exhaustion.
        detail = self.policy.rate_info.as_dict() if last_reason == "rate_limited" else None
        raise StravaUnavailableError(last_reason, detail=detail)

    def _handle_http_error(
        self, exc: urllib.error.HTTPError, attempts: int, last_reason: str, refreshed: bool
    ) -> tuple[int, str, bool]:
        """Handle one HTTPError; return updated (attempts, last_reason, refreshed).

        Raises immediately for UNAUTHORIZED (after one token refresh attempt) and
        NOT_FOUND. For TOO_MANY_REQUESTS and other HTTP errors, increments attempts
        and sleeps before signalling the caller to retry.
        """
        if exc.code == HTTPStatus.UNAUTHORIZED:
            if refreshed:
                raise StravaUnavailableError("token_unavailable") from exc
            self.token_provider.refresh()  # propagates StravaUnavailableError on failure
            # Preserve prior last_reason — a 401 after e.g. 429s must not overwrite "rate_limited".
            return attempts + 1, last_reason, True
        if exc.code == HTTPStatus.TOO_MANY_REQUESTS:
            self.policy.mark_rate_limited()
            new_attempts = attempts + 1
            if new_attempts < Config.Transport.MAX_RETRIES:
                self.sleeper.sleep(self._retry_after_seconds(exc))
            return new_attempts, "rate_limited", refreshed
        if exc.code == HTTPStatus.FORBIDDEN and self._is_application_inactive(exc):
            raise StravaUnavailableError(RefreshReason.STRAVA_APPLICATION_INACTIVE.value) from exc
        if exc.code == HTTPStatus.NOT_FOUND:
            raise exc
        new_attempts = attempts + 1
        if new_attempts < Config.Transport.MAX_RETRIES:
            self.sleeper.sleep([1, 5, 30][new_attempts - 1])
        return new_attempts, "network_unstable", refreshed

    def _build_request(self, path: str, token: str) -> urllib.request.Request:
        url = f"{self.base_url}/{path.lstrip('/')}"
        return urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    def _http(self, request: urllib.request.Request):
        opener = self.http or urllib.request.urlopen
        return opener(request, timeout=30)

    @staticmethod
    def _read_json(response) -> object:
        if hasattr(response, "__enter__"):
            with response as opened:
                return cast(object, json.loads(opened.read().decode()))
        return cast(object, json.loads(response.read().decode()))

    @staticmethod
    def _retry_after_seconds(exc: urllib.error.HTTPError) -> int:
        retry_after: str | None = None
        if exc.headers:
            raw_val = exc.headers.get("Retry-After")
            if isinstance(raw_val, str):
                retry_after = raw_val
        try:
            return int(retry_after) + 1 if retry_after is not None else 15
        except TypeError, ValueError:
            return 15

    @staticmethod
    def _is_application_inactive(exc: urllib.error.HTTPError) -> bool:
        try:
            raw = exc.read()
        except OSError:
            return False
        try:
            parsed = cast(object, json.loads(raw.decode()))
        except json.JSONDecodeError, UnicodeDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        errors = parsed.get("errors")
        if not isinstance(errors, list):
            return False
        for error in errors:
            if not isinstance(error, dict):
                continue
            if (
                error.get("resource") == "Application"
                and error.get("field") == "Status"
                and error.get("code") == "Inactive"
            ):
                return True
        return False

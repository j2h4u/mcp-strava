"""OAuth token refresh transport for Strava."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import cast

from mcp_strava.adapters.strava.types import Clock, RefreshedTokens, Sleeper, StravaUnavailableError


class TokenRefreshTransport:
    """Owns Strava OAuth POST retries separately from data-fetch retries."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        clock: Clock,
        sleeper: Sleeper,
        http: Callable | None = None,
        oauth_url: str = "https://www.strava.com/oauth/token",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.clock = clock
        self.sleeper = sleeper
        self.http = http
        self.oauth_url = oauth_url

    def refresh_tokens(self, refresh_token: str) -> RefreshedTokens:
        delays = [2, 8, 30]
        for attempt in range(3):
            request = self._build_request(refresh_token)
            try:
                response = self._http(request)
                status = int(getattr(response, "status", getattr(response, "code", 200)))
                if status >= 400:
                    raise StravaUnavailableError("token_unavailable")
                data = self._read_json(response)
                return RefreshedTokens(
                    access_token=str(data["access_token"]),
                    refresh_token=str(data["refresh_token"]),
                    expires_at=int(str(data["expires_at"])),
                )
            except urllib.error.HTTPError as exc:
                if 400 <= int(exc.code) < 500:
                    raise StravaUnavailableError("token_unavailable") from exc
                if attempt == 2:
                    raise StravaUnavailableError("token_unavailable") from exc
                self.sleeper.sleep(delays[attempt])
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                if attempt == 2:
                    raise StravaUnavailableError("token_unavailable") from exc
                self.sleeper.sleep(delays[attempt])
            except (KeyError, TypeError, ValueError) as exc:
                raise StravaUnavailableError("token_unavailable") from exc
        raise StravaUnavailableError("token_unavailable")

    def _build_request(self, refresh_token: str) -> urllib.request.Request:
        payload = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode()
        return urllib.request.Request(self.oauth_url, data=payload, method="POST")

    def _http(self, request: urllib.request.Request):
        opener = self.http or urllib.request.urlopen
        return opener(request, timeout=30)

    @staticmethod
    def _read_json(response) -> dict[str, object]:
        if hasattr(response, "__enter__"):
            with response as opened:
                parsed = cast(object, json.loads(opened.read().decode()))
                return parsed if isinstance(parsed, dict) else {}
        parsed = cast(object, json.loads(response.read().decode()))
        return parsed if isinstance(parsed, dict) else {}

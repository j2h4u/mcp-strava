"""StravaClient facade and shared transport-construction helper (D-08).

_build_strava_transport is the ONE place that wires:
    FileTokenProvider -> TokenRefreshTransport -> StravaTransport

It is used by both StravaClient and build_refresh_collaborators (12-03) so
there is no third parallel wiring path.

StravaClient exposes:
  - api_request(path) -> (data, rate_headers)   [no token= param — GP-02]
  - refresh_token()   -> str

Construction accepts an optional transport injection seam so tests and CLI
guards can supply a fake transport without real credentials.
"""

from __future__ import annotations

from mcp_strava.adapters.strava.clock import SystemClock, SystemSleeper
from mcp_strava.adapters.strava.rate_limit import RateLimitPolicy
from mcp_strava.adapters.strava.token_provider import FileTokenProvider
from mcp_strava.adapters.strava.token_refresh import TokenRefreshTransport
from mcp_strava.adapters.strava.transport import StravaTransport
from mcp_strava.adapters.strava.types import Clock, Sleeper, StravaUnavailableError
from mcp_strava.settings import Settings, required_strava_client_creds


def _build_strava_transport(
    settings: Settings,
    clock: Clock,
    sleeper: Sleeper,
) -> StravaTransport:
    """Compose FileTokenProvider -> TokenRefreshTransport -> StravaTransport.

    This is the single canonical wiring path used by both StravaClient and
    build_refresh_collaborators.  Raises RuntimeError (via
    required_strava_client_creds) when the token file is missing the required
    STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET keys.
    """
    client_id, client_secret = required_strava_client_creds(settings)
    refresh_transport = TokenRefreshTransport(
        client_id=client_id,
        client_secret=client_secret,
        clock=clock,
        sleeper=sleeper,
    )
    token_provider = FileTokenProvider(settings.token_path, refresh_transport, clock)
    return StravaTransport(token_provider, RateLimitPolicy(), clock, sleeper)


class StravaClient:
    """Facade for Strava HTTP + OAuth operations.

    Construction-time injection seam
    ---------------------------------
    Pass ``transport`` to inject a fake transport in tests or CLI guards so
    that no real credentials are needed at construction time.  When
    ``transport`` is omitted the real transport is built from ``settings``
    (or ``get_settings()`` if ``settings`` is also omitted) via
    ``_build_strava_transport``.

    Error contract
    --------------
    ``api_request`` returns a rate-limited sentinel dict when Strava signals
    rate exhaustion, and raises RuntimeError for all other failures.
    ``refresh_token`` raises RuntimeError on any StravaUnavailableError.
    Error messages surface only ``exc.reason`` — never the client_secret.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
        transport: StravaTransport | None = None,
    ) -> None:
        if transport is not None:
            # Injection seam: caller supplies the full transport (tests / guards).
            self._transport = transport
        else:
            from mcp_strava.settings import get_settings

            _settings = settings or get_settings()
            _clock = clock or SystemClock()
            _sleeper = sleeper or SystemSleeper()
            self._transport = _build_strava_transport(_settings, _clock, _sleeper)

    def api_request(self, path: str) -> tuple[object, dict]:
        """Fetch ``path`` from the Strava API.

        Returns ``(data, rate_headers)`` on success.  Returns the sentinel
        ``({"_rate_limited": True, "_retry_after": None}, {})`` when Strava
        responds with a rate-limit error so callers can handle back-off
        without exception handling.  All other failures raise RuntimeError.
        """
        try:
            response = self._transport.fetch(path)
        except StravaUnavailableError as exc:
            if exc.reason == "rate_limited":
                return {"_rate_limited": True, "_retry_after": None}, {}
            raise RuntimeError(f"Strava API request failed: {exc.reason}") from exc
        return response.data, response.rate_info.as_dict()

    def refresh_token(self) -> str:
        """Force an OAuth token refresh and return the new access token.

        Raises RuntimeError with the StravaUnavailableError reason on failure.
        The client_secret is never included in the error message.
        """
        try:
            return self._transport.token_provider.refresh()
        except StravaUnavailableError as exc:
            raise RuntimeError(f"Strava OAuth token refresh failed: {exc.reason}") from exc

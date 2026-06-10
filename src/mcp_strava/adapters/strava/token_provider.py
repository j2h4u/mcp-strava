"""File-backed Strava token provider with atomic single-writer refresh."""

from __future__ import annotations

import fcntl
import os
import tempfile
from pathlib import Path

from mcp_strava.adapters.strava.token_refresh import TokenRefreshTransport
from mcp_strava.adapters.strava.types import Clock, StravaUnavailableError


class FileTokenProvider:
    def __init__(self, path: str | Path, refresh_transport: TokenRefreshTransport, clock: Clock) -> None:
        self.path = Path(path)
        self._refresh_transport = refresh_transport
        self.clock = clock

    def access_token(self) -> str:
        return self.refresh_if_needed()

    def refresh_if_needed(self) -> str:
        with self._locked():
            values = self._read_values()
            if self._is_fresh(values):
                return values.get("STRAVA_ACCESS_TOKEN", "")
            return self._refresh_locked(values)

    def refresh(self) -> str:
        with self._locked():
            return self._refresh_locked(self._read_values())

    def _refresh_locked(self, values: dict[str, str]) -> str:
        refresh_token = values.get("STRAVA_REFRESH_TOKEN", "")
        if not refresh_token:
            raise StravaUnavailableError("token_unavailable")
        refreshed = self._refresh_transport.refresh_tokens(refresh_token)
        values["STRAVA_ACCESS_TOKEN"] = refreshed.access_token
        values["STRAVA_REFRESH_TOKEN"] = refreshed.refresh_token
        values["STRAVA_EXPIRES_AT"] = str(refreshed.expires_at)
        self._atomic_write(values)
        return refreshed.access_token

    def _locked(self):
        return _FileLock(self._lock_path())

    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    def _read_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.path.exists():
            return values
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
                continue
            key, value = raw_line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def _is_fresh(self, values: dict[str, str]) -> bool:
        token = values.get("STRAVA_ACCESS_TOKEN")
        if not token:
            return False
        try:
            expires_at = int(values.get("STRAVA_EXPIRES_AT", "0"))
        except ValueError:
            return False
        return expires_at > int(self.clock.now()) + 60

    def _atomic_write(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for key, value in values.items():
                    handle.write(f"{key}={value}\n")
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(self.path)
            self.path.chmod(0o600)
        except Exception:  # noqa: BLE001 - cleanup preserves the original atomic-write failure.
            try:
                temp_path.unlink(missing_ok=True)
            finally:
                raise


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Create the lock sidecar 0600 rather than umask-inherited 0644: os.open
        # honours the mode on creation, and chmod repairs a pre-existing file.
        # Keeps the advisory lock from being world-readable next to the token.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self.path.chmod(0o600)
        self._handle = os.fdopen(fd, "a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()

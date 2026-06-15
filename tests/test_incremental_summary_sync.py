"""Tests for incremental SUMMARIES sync (260610-nk9).

Coverage:
  (schema)  - last_full_summary_sync_at column: get/set round-trip
  (settings)- full_resync_interval_seconds env-var parse + default
  (a)       - sync_summaries URL includes &after=N when after_epoch set; absent when None
  (b-full)  - run_once with NULL marker triggers full walk and writes the marker
  (b-full-stale) - run_once with stale marker triggers full walk and updates the marker
  (b-incremental) - run_once with fresh marker triggers incremental with non-None after_epoch
  (c)       - cold-start (empty DB, NULL marker) -> full walk (after_epoch=None)
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from mcp_strava.adapters.duckdb.refresh_state_store import RefreshStateStore
from mcp_strava.adapters.duckdb.repository import DuckDBRepository
from mcp_strava.adapters.strava import StravaResponse
from mcp_strava.adapters.strava.types import StravaRateInfo
from mcp_strava.refresh.runtime import RefreshCollaborators
from tests._fixtures_duckdb import create_fixture_db


@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise RuntimeError("live network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path) -> DuckDBRepository:
    path = tmp_path / "test.duckdb"
    create_fixture_db(path)
    return DuckDBRepository.from_path(path)


def _empty_repo(tmp_path: Path) -> DuckDBRepository:
    """Repo with schema but no activities (cold-start)."""
    from tests._fixtures_duckdb import create_empty_fixture_db

    path = tmp_path / "empty.duckdb"
    create_empty_fixture_db(path)
    return DuckDBRepository.from_path(path)


class FakeClock:
    def __init__(self, value: float = 1_716_206_400.0):
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeSleeper:
    def sleep(self, seconds: float) -> None:
        pass


class _OnePageTransport:
    """Returns one activity page then empty; captures called URLs."""

    def __init__(self, activity_id: int = 9001):
        self.activity_id = activity_id
        self.called_urls: list[str] = []

    def fetch(self, path: str) -> StravaResponse:
        self.called_urls.append(path)
        if path.startswith("/athlete/activities") and path not in self.called_urls[:-1]:
            # Return data only on first call to this prefix; subsequent calls (page 2+) return [].
            first_call = sum(1 for u in self.called_urls if u.startswith("/athlete/activities")) == 1
            if first_call:
                return StravaResponse(
                    data=[
                        {
                            "id": self.activity_id,
                            "name": "Test Activity",
                            "sport_type": "Run",
                            "start_date_local": "2024-05-20T06:00:00Z",
                            "distance": 5000,
                            "moving_time": 1800,
                            "elapsed_time": 1850,
                            "total_elevation_gain": 50,
                        }
                    ],
                    rate_info=StravaRateInfo(),
                    status=200,
                )
        return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)


class _FullRunTransport:
    """Transport that handles all stages for run_once."""

    def __init__(self, activity_id: int = 9001):
        self.activity_id = activity_id
        self.called_urls: list[str] = []

    def fetch(self, path: str) -> StravaResponse:
        self.called_urls.append(path)
        if path.startswith("/athlete/activities"):
            first_call = sum(1 for u in self.called_urls if u.startswith("/athlete/activities")) == 1
            if first_call:
                return StravaResponse(
                    data=[
                        {
                            "id": self.activity_id,
                            "name": "Test Activity",
                            "sport_type": "Run",
                            "start_date_local": "2024-05-20T06:00:00Z",
                            "distance": 5000,
                            "moving_time": 1800,
                            "elapsed_time": 1850,
                            "total_elevation_gain": 50,
                        }
                    ],
                    rate_info=StravaRateInfo(),
                    status=200,
                )
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)
        if path.startswith(f"/activities/{self.activity_id}/streams"):
            return StravaResponse(
                data={"time": {"data": [0, 1]}, "heartrate": {"data": [140, 141]}},
                rate_info=StravaRateInfo(),
                status=200,
            )
        if path.startswith(f"/activities/{self.activity_id}/kudos"):
            return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)
        if path.startswith(f"/activities/{self.activity_id}"):
            return StravaResponse(
                data={"id": self.activity_id, "name": "Test Activity", "resource_state": 3},
                rate_info=StravaRateInfo(),
                status=200,
            )
        return StravaResponse(data=[], rate_info=StravaRateInfo(), status=200)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_schema_get_last_full_summary_sync_at_returns_none_when_null(tmp_path):
    """get_last_full_summary_sync_at returns None when column value is NULL."""
    with _repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.get_last_full_summary_sync_at() is None


def test_schema_set_and_get_last_full_summary_sync_at_round_trip(tmp_path):
    """set_last_full_summary_sync_at writes a value that get_ reads back."""
    marker = "2024-05-20T06:00:00"
    with _repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        store.set_last_full_summary_sync_at(marker)
        assert store.get_last_full_summary_sync_at() == marker


# ---------------------------------------------------------------------------
# Settings tests
# ---------------------------------------------------------------------------


def test_settings_full_resync_interval_seconds_env_override(monkeypatch):
    """MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS=86400 parses to 86400."""
    from mcp_strava.settings import load_settings, reset_settings_cache

    reset_settings_cache()
    monkeypatch.setenv("MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS", "86400")
    settings = load_settings(environ={"MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS": "86400"})
    assert settings.refresh.full_resync_interval_seconds == 86400


def test_settings_full_resync_interval_seconds_default(monkeypatch):
    """full_resync_interval_seconds defaults to 604800 when env var absent."""
    from mcp_strava.settings import load_settings, reset_settings_cache

    reset_settings_cache()
    settings = load_settings(environ={})
    assert settings.refresh.full_resync_interval_seconds == 604800


# ---------------------------------------------------------------------------
# Test (a): sync_summaries URL construction
# ---------------------------------------------------------------------------


def test_sync_summaries_with_after_epoch_appends_after_param(tmp_path):
    """sync_summaries(after_epoch=N) appends &after=N to the first request URL."""
    from mcp_strava.refresh._sync_ops import sync_summaries

    transport = _OnePageTransport()
    with _repo(tmp_path) as repo:
        sync_summaries(repo, transport, "2024-05-20T07:00:00", after_epoch=1716206400)

    summary_urls = [u for u in transport.called_urls if u.startswith("/athlete/activities")]
    assert summary_urls, "no /athlete/activities call made"
    assert "&after=1716206400" in summary_urls[0]


def test_sync_summaries_without_after_epoch_has_no_after_param(tmp_path):
    """sync_summaries(after_epoch=None) has no &after= in the URL."""
    from mcp_strava.refresh._sync_ops import sync_summaries

    transport = _OnePageTransport()
    with _repo(tmp_path) as repo:
        sync_summaries(repo, transport, "2024-05-20T07:00:00", after_epoch=None)

    summary_urls = [u for u in transport.called_urls if u.startswith("/athlete/activities")]
    assert summary_urls, "no /athlete/activities call made"
    assert "&after=" not in summary_urls[0]


# ---------------------------------------------------------------------------
# Test (b-full): NULL marker -> full walk + marker written
# ---------------------------------------------------------------------------


def test_run_once_null_marker_triggers_full_walk_and_writes_marker(tmp_path, monkeypatch):
    """run_once with NULL last_full_summary_sync_at calls sync_summaries with after_epoch=None."""
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once

    captured: list[int | None] = []

    original_sync = _sync_ops.sync_summaries

    def fake_sync_summaries(repo, transport, now_iso, *, after_epoch=None):
        captured.append(after_epoch)
        return original_sync(repo, transport, now_iso, after_epoch=after_epoch)

    monkeypatch.setattr(_sync_ops, "sync_summaries", fake_sync_summaries)

    clock = FakeClock()
    policy = RefreshPolicy(full_resync_interval_seconds=604800)
    transport = _FullRunTransport()

    with _repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.get_last_full_summary_sync_at() is None

        result = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper()),
            force=True,
        )

        marker_after = store.get_last_full_summary_sync_at()

    assert result.status == "ok"
    assert len(captured) == 1
    assert captured[0] is None, f"expected after_epoch=None for full walk, got {captured[0]}"
    assert marker_after is not None, "last_full_summary_sync_at must be written after full run"


# ---------------------------------------------------------------------------
# Test (b-full-stale): stale marker -> full walk + marker updated
# ---------------------------------------------------------------------------


def test_run_once_stale_marker_triggers_full_walk_and_updates_marker(tmp_path, monkeypatch):
    """run_once with stale last_full_summary_sync_at triggers full walk and updates marker."""
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once

    captured: list[int | None] = []
    original_sync = _sync_ops.sync_summaries

    def fake_sync(repo, transport, now_iso, *, after_epoch=None):
        captured.append(after_epoch)
        return original_sync(repo, transport, now_iso, after_epoch=after_epoch)

    monkeypatch.setattr(_sync_ops, "sync_summaries", fake_sync)

    # Clock is at epoch 1716206400 = 2024-05-20T06:00:00
    clock = FakeClock(value=1_716_206_400.0)
    # Stale marker: 10 days ago
    stale_marker = "2024-05-10T06:00:00"
    policy = RefreshPolicy(full_resync_interval_seconds=604800)  # 7 days
    transport = _FullRunTransport()

    with _repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        store.set_last_full_summary_sync_at(stale_marker)

        result = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper()),
            force=True,
        )

        marker_after = store.get_last_full_summary_sync_at()

    assert result.status == "ok"
    assert captured[0] is None, "stale marker should trigger full walk (after_epoch=None)"
    assert marker_after != stale_marker, "marker must be updated after full run"


# ---------------------------------------------------------------------------
# Test (b-incremental): fresh marker -> incremental with non-None after_epoch
# ---------------------------------------------------------------------------


def test_run_once_fresh_marker_triggers_incremental(tmp_path, monkeypatch):
    """run_once with fresh last_full_summary_sync_at calls sync_summaries with non-None after_epoch."""
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once

    captured: list[int | None] = []
    original_sync = _sync_ops.sync_summaries

    def fake_sync(repo, transport, now_iso, *, after_epoch=None):
        captured.append(after_epoch)
        return original_sync(repo, transport, now_iso, after_epoch=after_epoch)

    monkeypatch.setattr(_sync_ops, "sync_summaries", fake_sync)

    # Clock is at epoch 1716206400 = 2024-05-20T06:00:00
    clock = FakeClock(value=1_716_206_400.0)
    # Fresh marker: 1 hour ago (well within 7 days)
    fresh_marker = "2024-05-20T05:00:00"
    policy = RefreshPolicy(full_resync_interval_seconds=604800)
    transport = _FullRunTransport()

    with _repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        store.set_last_full_summary_sync_at(fresh_marker)

        result = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper()),
            force=True,
        )

        marker_after = store.get_last_full_summary_sync_at()

    assert result.status == "ok"
    assert len(captured) == 1
    assert captured[0] is not None, "fresh marker should trigger incremental (after_epoch != None)"
    # Marker must NOT be updated on incremental run
    assert marker_after == fresh_marker, "marker must not change on incremental run"


# ---------------------------------------------------------------------------
# Test (c): cold-start — empty DB, NULL marker -> full walk
# ---------------------------------------------------------------------------


def test_run_once_cold_start_triggers_full_walk(tmp_path, monkeypatch):
    """Empty DB (no activities, NULL marker) triggers full walk (after_epoch=None)."""
    from mcp_strava.refresh import RefreshPolicy, _sync_ops, run_once

    captured: list[int | None] = []
    original_sync = _sync_ops.sync_summaries

    def fake_sync(repo, transport, now_iso, *, after_epoch=None):
        captured.append(after_epoch)
        return original_sync(repo, transport, now_iso, after_epoch=after_epoch)

    monkeypatch.setattr(_sync_ops, "sync_summaries", fake_sync)

    clock = FakeClock()
    policy = RefreshPolicy(full_resync_interval_seconds=604800)
    transport = _FullRunTransport()

    with _empty_repo(tmp_path) as repo:
        store = RefreshStateStore.from_connection(repo.conn)
        assert store.get_last_full_summary_sync_at() is None

        result = run_once(
            RefreshCollaborators(repo=repo, transport=transport, policy=policy, clock=clock, sleeper=FakeSleeper()),
            force=True,
        )

    assert result.status == "ok"
    assert len(captured) == 1
    assert captured[0] is None, "cold-start must trigger full walk (after_epoch=None)"

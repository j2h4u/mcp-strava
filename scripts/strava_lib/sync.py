"""Strava API sync and backfill operations."""

import sys
import json
import time
import socket
import urllib.error
from datetime import datetime

from strava_lib.db import DbConn, init_db, load_env, api_request
from strava_lib.types import parse_strava_activity, parse_strava_streams
from strava_lib.sports import detect_new_types


STREAM_KEYS = "time,heartrate,velocity_smooth,altitude,cadence,latlng,grade_smooth,grade_adjusted_speed,grade_adjusted_distance,moving"


class RateLimiter:
    """Track Strava API calls and enforce limit using server-reported usage when available."""

    def __init__(self, limit=190, window=900):
        self.limit = limit
        self.window = window
        self.timestamps = []
        self.total = 0
        self._server_usage = None
        self._server_limit = 200

    def update_from_headers(self, rate_info):
        """Update with server-reported X-RateLimit-Usage (more accurate than client counter)."""
        if 'usage_15min' in rate_info:
            self._server_usage = rate_info['usage_15min']
            self._server_limit = rate_info.get('limit_15min', 200)

    def mark_rate_limited(self):
        """Force rate limiter to block until the window resets — call after receiving 429."""
        self._server_usage = self._server_limit
        print(f"  Rate limiter: marked as exhausted ({self._server_limit}/{self._server_limit})", file=sys.stderr)

    def wait(self):
        import time as _t
        now = _t.time()
        self.timestamps = [ts for ts in self.timestamps if now - ts < self.window]
        effective_count = self._server_usage if self._server_usage is not None else len(self.timestamps)
        if effective_count >= self.limit:
            oldest = self.timestamps[0] if self.timestamps else now - self.window
            sleep_time = self.window - (now - oldest) + 1
            print(f"  Rate limit: {effective_count}/{self._server_limit}, sleeping {sleep_time:.0f}s...", file=sys.stderr)
            _t.sleep(sleep_time)
            self.timestamps = []
            self._server_usage = None
        self.timestamps.append(_t.time())
        self.total += 1


def _insert_streams(conn, act_id, data):
    """Parse streams API response and insert into DB in batches."""
    streams = parse_strava_streams(data)
    n = len(streams.time.data)
    if n == 0:
        return 0
    batch_size = 5000
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        rows = []
        for idx in range(start, end):
            rows.append((
                act_id,
                streams.time.data[idx],
                streams.heartrate.data[idx] if streams.heartrate and idx < len(streams.heartrate.data) else None,
                streams.velocity_smooth.data[idx] if streams.velocity_smooth and idx < len(streams.velocity_smooth.data) else None,
                streams.altitude.data[idx] if streams.altitude and idx < len(streams.altitude.data) else None,
                streams.cadence.data[idx] if streams.cadence and idx < len(streams.cadence.data) else None,
                json.dumps(streams.latlng.data[idx]) if streams.latlng and idx < len(streams.latlng.data) else None,
                streams.grade_smooth.data[idx] if streams.grade_smooth and idx < len(streams.grade_smooth.data) else None,
                streams.grade_adjusted_speed.data[idx] if streams.grade_adjusted_speed and idx < len(streams.grade_adjusted_speed.data) else None,
                streams.grade_adjusted_distance.data[idx] if streams.grade_adjusted_distance and idx < len(streams.grade_adjusted_distance.data) else None,
                streams.moving.data[idx] if streams.moving and idx < len(streams.moving.data) else None,
            ))
        conn.executemany("""
            INSERT OR REPLACE INTO streams
            (activity_id, time_offset, heartrate, velocity, altitude, cadence,
             latlng, grade, gap_speed, gap_distance, is_moving)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
    return n


def _fetch_with_retry(path, token, limiter, label=""):
    """API request with rate-limit + network-error retry. Returns data or None after 3 attempts."""
    for attempt in range(3):
        limiter.wait()
        try:
            data, rate_info = api_request(path, token)
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, OSError) as e:
            if isinstance(e, urllib.error.HTTPError):
                if e.code == 404:
                    print(f"  404 on {label} — skipping", file=sys.stderr)
                    return None
                print(f"  HTTP {e.code} on {label} (attempt {attempt + 1}/3)", file=sys.stderr)
                if e.code in (401, 429):
                    continue
            delay = [1, 5, 30][attempt]
            print(f"  Network error on {label} (attempt {attempt + 1}/3): {e}", file=sys.stderr)
            if attempt < 2:
                print(f"    Retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
            continue

        limiter.update_from_headers(rate_info)

        if isinstance(data, dict) and data.get('_rate_limited'):
            limiter.mark_rate_limited()
            retry_after = data.get('_retry_after')
            if retry_after is not None:
                try:
                    sleep_s = int(retry_after) + 1
                    print(f"  Rate limited on {label}, Retry-After={retry_after}s (attempt {attempt + 1}/3)...", file=sys.stderr)
                    time.sleep(sleep_s)
                except (ValueError, TypeError):
                    print(f"  Rate limited on {label}, retrying in 15s ({attempt + 1}/3)...", file=sys.stderr)
                    time.sleep(15)
            else:
                print(f"  Rate limited on {label}, retrying in 15s ({attempt + 1}/3)...", file=sys.stderr)
                time.sleep(15)
            continue
        return data
    return None


def sync_activities(quick=True):
    """Incremental sync: new activities + streams + details + schema validation.
    quick=True (default): uses after= to fetch only recent activities (~1-2 API calls).
    quick=False: full pagination from page 1 (~6 API calls) — catches back-dated uploads.
    """
    t0 = time.time()
    with DbConn() as conn:
        init_db(conn)
        token = load_env().get('STRAVA_ACCESS_TOKEN', '')
        limiter = RateLimiter()

        activities_seen = 0
        activities_new = 0
        streams_fetched = 0
        details_fetched = 0

        # Quick sync: only fetch activities since last known date
        after_param = ""
        if quick:
            row = conn.execute("SELECT MAX(date) FROM activities").fetchone()
            latest_date = row[0] if row[0] else '2000-01-01'
            # Subtract 7 days — catches late kudos/likes and timezone edge cases
            from datetime import timedelta
            safe_date = (datetime.strptime(latest_date, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
            after_ts = int(datetime.strptime(safe_date, '%Y-%m-%d').timestamp())
            after_param = f"&after={after_ts}"
            print(f"--- Quick Sync (since {safe_date}) ---", file=sys.stderr)
        else:
            print("--- Full Sync ---", file=sys.stderr)

        # Phase 1: Sync activity summaries
        print("--- Phase 1: Activity Summaries ---", file=sys.stderr)
        page = 1
        while True:
            data = _fetch_with_retry(
                f"/athlete/activities?per_page=100{after_param}&page={page}",
                token, limiter, f"page {page}")
            if not data:
                break
            if not isinstance(data, list):
                print(f"  Unexpected API response type on page {page}: {type(data).__name__}", file=sys.stderr)
                break
            activities_seen += len(data)
            added = 0
            for raw in data:
                act = parse_strava_activity(raw)
                existing = conn.execute("SELECT id FROM activities WHERE id=?", (act.id,)).fetchone()
                if existing:
                    conn.execute("""
                        UPDATE activities SET name=?, sport_type=?, distance=?, moving_time=?,
                        elapsed_time=?, total_elevation_gain=?, summary_json=?, synced_at=?
                        WHERE id=?
                    """, (act.name, act.sport_type, act.distance, act.moving_time,
                          act.elapsed_time, act.total_elevation_gain, json.dumps(raw),
                          datetime.now().isoformat(), act.id))
                else:
                    conn.execute("""
                        INSERT INTO activities (id, date, name, sport_type, distance, moving_time,
                        elapsed_time, total_elevation_gain, summary_json, synced_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (act.id, act.start_date_local[:10], act.name, act.sport_type, act.distance,
                          act.moving_time, act.elapsed_time, act.total_elevation_gain, json.dumps(raw),
                          datetime.now().isoformat()))
                    added += 1
            activities_new += added
            conn.commit()
            print(f"  Page {page}: {len(data)} activities, {added} new", file=sys.stderr)
            if len(data) < 100:
                break
            page += 1

        # Phase 2: Sync streams (with GAP)
        print("--- Phase 2: Streams ---", file=sys.stderr)
        missing = conn.execute("""
            SELECT a.id, a.name FROM activities a
            WHERE NOT EXISTS (SELECT 1 FROM streams s WHERE s.activity_id = a.id)
            ORDER BY a.date
        """).fetchall()
        for row in missing:
            data = _fetch_with_retry(
                f"/activities/{row['id']}/streams?keys={STREAM_KEYS}&key_by_type=true",
                token, limiter, row['name'])
            if data and isinstance(data, dict):
                _insert_streams(conn, row['id'], data)
                streams_fetched += 1
            elif data:
                print(f"  Unexpected streams response for {row['name']}: {type(data).__name__}", file=sys.stderr)
        conn.commit()

        # Phase 3: Sync details
        print("--- Phase 3: Details ---", file=sys.stderr)
        missing_detail = conn.execute("""
            SELECT id, name FROM activities WHERE detail_json IS NULL ORDER BY date
        """).fetchall()
        for row in missing_detail:
            data = _fetch_with_retry(f"/activities/{row['id']}", token, limiter, row['name'])
            if data and isinstance(data, dict):
                conn.execute("UPDATE activities SET detail_json=? WHERE id=?", (json.dumps(data), row['id']))
                details_fetched += 1
            elif data:
                print(f"  Unexpected detail response for {row['name']}: {type(data).__name__}", file=sys.stderr)
        conn.commit()

        # Phase 4: Schema validation
        sport_types = [r['sport_type'] for r in conn.execute(
            "SELECT DISTINCT sport_type FROM activities WHERE sport_type IS NOT NULL").fetchall()]
        new_types = detect_new_types(sport_types)
        if new_types:
            print(f"  New sport types detected: {new_types}", file=sys.stderr)

        # Phase 5: Kudos
        kudos_fetched = _sync_kudos(conn, token, limiter)

        duration_ms = int((time.time() - t0) * 1000)
        conn.execute("""
            INSERT INTO sync_log (timestamp, status, activities_seen, activities_new,
                                  streams_fetched, details_fetched, kudos_fetched, api_calls)
            VALUES (?, 'ok', ?, ?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), activities_seen, activities_new,
              streams_fetched, details_fetched, kudos_fetched, limiter.total))
        conn.commit()

        print(f"Sync done. {limiter.total} API calls used.", file=sys.stderr)


def backfill_activities():
    """Incremental backfill: fetch missing GAP streams + details only."""
    with DbConn() as conn:
        init_db(conn)
        token = load_env().get('STRAVA_ACCESS_TOKEN', '')
        limiter = RateLimiter()

        # Find activities missing GAP streams
        need_gap = conn.execute("""
            SELECT a.id, a.name, a.sport_type FROM activities a
            WHERE NOT EXISTS (
                SELECT 1 FROM streams s WHERE s.activity_id = a.id AND s.gap_speed IS NOT NULL
            ) AND a.sport_type IN ('Run', 'TrailRun')
            ORDER BY a.date
        """).fetchall()

        # Find activities missing detail_json
        need_detail = conn.execute("""
            SELECT id, name, sport_type FROM activities
            WHERE detail_json IS NULL ORDER BY date
        """).fetchall()

        total_streams = len(need_gap)
        total_detail = len(need_detail)
        total_calls = total_streams + total_detail
        print(f"=== Backfill: {total_streams} need GAP streams, {total_detail} need detail ({total_calls} API calls) ===", file=sys.stderr)

        if total_calls == 0:
            print("Nothing to backfill.", file=sys.stderr)
            return

        for i, row in enumerate(need_gap, 1):
            act_id, name, sport = row['id'], row['name'], row['sport_type']
            data = _fetch_with_retry(
                f"/activities/{act_id}/streams?keys={STREAM_KEYS}&key_by_type=true",
                token, limiter, f"{name} streams")
            if data and isinstance(data, dict):
                conn.execute("DELETE FROM streams WHERE activity_id=?", (act_id,))
                n = _insert_streams(conn, act_id, data)
            else:
                if data:
                    print(f"  Unexpected streams response for {name}: {type(data).__name__}", file=sys.stderr)
                n = 0
            print(f"  [{i}/{total_streams}] {name} ({sport}): {n} stream points", file=sys.stderr)

        for i, row in enumerate(need_detail, 1):
            act_id, name, sport = row['id'], row['name'], row['sport_type']
            data = _fetch_with_retry(f"/activities/{act_id}", token, limiter, f"{name} detail")
            if data and isinstance(data, dict):
                conn.execute("UPDATE activities SET detail_json=? WHERE id=?", (json.dumps(data), act_id))
                n = 1
            else:
                if data:
                    print(f"  Unexpected detail response for {name}: {type(data).__name__}", file=sys.stderr)
                n = 0
            print(f"  [{i}/{total_detail}] {name} ({sport}): detail {'OK' if n else 'FAIL'}", file=sys.stderr)

        conn.commit()
        print(f"Backfill done. {limiter.total} API calls used.", file=sys.stderr)


def _sync_kudos(conn, token, limiter, window_days=None):
    """Fetch kudos for activities that have kudos but aren't synced yet.
    window_days=None: all time. window_days=30: last 30 days only.
    Returns number of activities whose kudos were fetched."""
    query = """
        SELECT a.id, a.name FROM activities a
        WHERE CAST(json_extract(a.summary_json, '$.kudos_count') AS INTEGER) > 0
          AND NOT EXISTS (SELECT 1 FROM kudos k WHERE k.activity_id = a.id)
    """
    params = []
    if window_days is not None:
        query += " AND a.date >= date('now', ?)"
        params.append(f'-{window_days} days')
    query += " ORDER BY a.date DESC"

    rows = conn.execute(query, params).fetchall()

    if not rows:
        return 0

    print(f"--- Phase 5: Kudos ({len(rows)} activities with unsynced kudos) ---", file=sys.stderr)
    fetched = 0
    for row in rows:
        data = _fetch_with_retry(
            f"/activities/{row['id']}/kudos?per_page=100",
            token, limiter, f"kudos {row['name']}")
        if not data or not isinstance(data, list):
            continue
        for athlete in data:
            conn.execute("""
                INSERT OR REPLACE INTO kudos (activity_id, firstname, lastname, fetched_at)
                VALUES (?, ?, ?, ?)
            """, (row['id'],
                  athlete.get('firstname', ''),
                  athlete.get('lastname', ''),
                  datetime.now().isoformat()))
        fetched += 1
    conn.commit()
    return fetched

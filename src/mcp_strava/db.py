"""Database layer — connection management, auth, zones, TRIMP queries."""

import sqlite3
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta

from mcp_strava.adapters.sqlite.connection import open_expected_mirror_db
from mcp_strava.adapters.sqlite.migrations import run_preflight
from mcp_strava.adapters.sqlite.repository import SQLiteRepository
from mcp_strava.settings import get_settings


def _db_path() -> str:
    return str(get_settings().database_path)


def _env_path() -> str:
    return str(get_settings().token_path)


# --- DB ---

class DbConn:
    """Context manager for SQLite connections — auto-closes on exit."""

    def __enter__(self):
        self.conn = open_expected_mirror_db(_db_path())
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()



def init_db(conn):
    # Phase 2: runtime paths do not run schema-changing DDL.
    run_preflight(_db_path())


# --- Auth ---

def load_env():
    env = {}
    env_path = _env_path()
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env


def save_env(env):
    with open(_env_path(), 'w') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def refresh_token():
    env = load_env()
    required = ['STRAVA_CLIENT_ID', 'STRAVA_CLIENT_SECRET', 'STRAVA_REFRESH_TOKEN']
    missing = [k for k in required if k not in env]
    if missing:
        env_path = _env_path()
        raise RuntimeError(f"Missing env vars for Strava auth: {', '.join(missing)}. Check {env_path}")
    data = urllib.parse.urlencode({
        'client_id': env['STRAVA_CLIENT_ID'],
        'client_secret': env['STRAVA_CLIENT_SECRET'],
        'grant_type': 'refresh_token',
        'refresh_token': env['STRAVA_REFRESH_TOKEN'],
    }).encode()
    req = urllib.request.Request("https://www.strava.com/oauth/token", data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            res = json.loads(f.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Strava OAuth token refresh failed: HTTP {e.code}. "
            f"Refresh token may be expired — re-authorize at https://www.strava.com/settings/api"
        ) from e
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(f"Strava OAuth token refresh failed: network error — {e}") from e
    env['STRAVA_ACCESS_TOKEN'] = res['access_token']
    env['STRAVA_REFRESH_TOKEN'] = res['refresh_token']
    save_env(env)
    return res['access_token']


def _parse_rate_headers(headers):
    """Extract rate limit info from Strava response headers."""
    info = {}
    usage = headers.get('X-RateLimit-Usage')
    limit_val = headers.get('X-RateLimit-Limit')
    if usage:
        parts = usage.split(',')
        try:
            info['usage_15min'] = int(parts[0].strip())
        except (ValueError, IndexError):
            pass
        if len(parts) > 1:
            try:
                info['usage_daily'] = int(parts[1].strip())
            except ValueError:
                pass
    if limit_val:
        parts = limit_val.split(',')
        try:
            info['limit_15min'] = int(parts[0].strip())
        except ValueError:
            pass
    return info


def api_request(path, token=None):
    """Strava API request. Returns (data, rate_headers) tuple.
    rate_headers contains usage_15min, usage_daily, limit_15min from X-RateLimit-* headers."""
    if not token:
        token = load_env().get('STRAVA_ACCESS_TOKEN', '')
    url = f"https://www.strava.com/api/v3{path}"
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            data = json.loads(f.read().decode())
            rate_info = _parse_rate_headers(f.headers)
            return data, rate_info
    except urllib.error.HTTPError as e:
        if e.code == 401:
            new_token = refresh_token()
            req2 = urllib.request.Request(url)
            req2.add_header('Authorization', f'Bearer {new_token}')
            with urllib.request.urlopen(req2, timeout=30) as f:
                data = json.loads(f.read().decode())
                rate_info = _parse_rate_headers(f.headers)
            return data, rate_info
        if e.code == 429:
            retry_after = e.headers.get('Retry-After')
            return {"_rate_limited": True, "_retry_after": retry_after}, {}
        raise


# --- HR Zones ---

def get_zones():
    """Get cached zones or fetch from Strava."""
    with DbConn() as conn:
        row = conn.execute("SELECT zones_json FROM athlete_zones ORDER BY fetched_at DESC LIMIT 1").fetchone()
        if row:
            return json.loads(row['zones_json'])
    # Fetch from API
    token = load_env().get('STRAVA_ACCESS_TOKEN', '')
    data, _rate_info = api_request('/athlete/zones', token)
    zones = [{'min': z['min'], 'max': z['max'] if z['max'] != -1 else 300}
             for z in data['heart_rate']['zones']]
    with DbConn() as conn:
        conn.execute("INSERT INTO athlete_zones (fetched_at, zones_json) VALUES (?, ?)",
                     (datetime.now().isoformat(), json.dumps(zones)))
        conn.commit()
    return zones


# --- TRIMP History ---

def get_daily_trimp_history(conn, days=None, sport_filter=None):
    """Return dict {date_str: trimp} for last N days (0 for rest days).
    days=None: use all available history (needed for Banister warmup).
    sport_filter='training': exclude non-training activities (Walk) from TRIMP.
                           Prevents daily walking from creating false fatigue signals.
    """
    repo = SQLiteRepository.from_connection(conn)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d') if days is not None else None
    return repo.observed_trimp_history(since_day=since, sport_filter=sport_filter)

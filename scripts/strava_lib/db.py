"""Database layer — connection management, auth, zones, TRIMP queries."""

import sqlite3
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta

from strava_lib.constants import Config, TRAINING_SPORTS

# strava_lib/ is inside scripts/, so go up 2 levels to reach skill root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, 'data', 'strava.db')
ENV_PATH = os.path.join(BASE_DIR, '.env')


# --- DB ---

class DbConn:
    """Context manager for SQLite connections — auto-closes on exit."""

    def __enter__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA wal_autocheckpoint=1000")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()



def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY,
            date TEXT, name TEXT, sport_type TEXT,
            distance REAL, moving_time INTEGER, elapsed_time INTEGER,
            total_elevation_gain REAL,
            summary_json TEXT, detail_json TEXT, synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS streams (
            activity_id INTEGER, time_offset INTEGER,
            heartrate INTEGER, velocity REAL, altitude REAL,
            cadence INTEGER, lat REAL, lng REAL, grade REAL,
            PRIMARY KEY (activity_id, time_offset)
        );
        CREATE INDEX IF NOT EXISTS idx_streams_act ON streams(activity_id);
        CREATE TABLE IF NOT EXISTS athlete_zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT, zones_json TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            activities_seen INTEGER,
            activities_new INTEGER,
            streams_fetched INTEGER,
            details_fetched INTEGER,
            api_calls INTEGER,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS kudos (
            activity_id INTEGER NOT NULL,
            firstname TEXT NOT NULL DEFAULT '',
            lastname TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (activity_id, firstname, lastname)
        );
    """)
    # Migrate: add GAP/moving columns if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(streams)")}
    if 'gap_speed' not in cols:
        conn.execute("ALTER TABLE streams ADD COLUMN gap_speed REAL")
    if 'gap_distance' not in cols:
        conn.execute("ALTER TABLE streams ADD COLUMN gap_distance REAL")
    if 'is_moving' not in cols:
        conn.execute("ALTER TABLE streams ADD COLUMN is_moving INTEGER")
    if 'latlng' not in cols:
        conn.execute("ALTER TABLE streams ADD COLUMN latlng TEXT")
    # Migrate: add kudos_fetched to sync_log
    slog_cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_log)")}
    if 'kudos_fetched' not in slog_cols:
        conn.execute("ALTER TABLE sync_log ADD COLUMN kudos_fetched INTEGER")
    conn.commit()


# --- Auth ---

def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env


def save_env(env):
    with open(ENV_PATH, 'w') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def refresh_token():
    env = load_env()
    required = ['STRAVA_CLIENT_ID', 'STRAVA_CLIENT_SECRET', 'STRAVA_REFRESH_TOKEN']
    missing = [k for k in required if k not in env]
    if missing:
        raise RuntimeError(f"Missing env vars for Strava auth: {', '.join(missing)}. Check {ENV_PATH}")
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
    where_parts = ["s.heartrate IS NOT NULL"]
    params = []

    if days is not None:
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        where_parts.append("SUBSTR(a.date,1,10) >= ?")
        params.append(since)

    if sport_filter == 'training':
        placeholders = ','.join('?' * len(TRAINING_SPORTS))
        where_parts.append(f"a.sport_type IN ({placeholders})")
        params.extend(TRAINING_SPORTS)

    where = "WHERE " + " AND ".join(where_parts)
    rows = conn.execute(f"""
        SELECT SUBSTR(a.date,1,10) as day,
               {Config.SQL.TRIMP_S}
        FROM activities a JOIN streams s ON a.id = s.activity_id
        {where}
        GROUP BY day
    """, params).fetchall()
    return {r['day']: round(r['trimp'], 1) for r in rows}

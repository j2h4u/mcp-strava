"""Typed runtime settings for mcp_strava."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class HttpSettings:
    host: str
    port: int


@dataclass(frozen=True)
class FreshnessSettings:
    warn_age_hours: int
    max_age_hours: int


@dataclass(frozen=True)
class Settings:
    database_path: Path
    token_path: Path
    runtime_profile: str
    http: HttpSettings
    freshness: FreshnessSettings


_KEYS = {
    'MCP_STRAVA_DB_PATH',
    'MCP_STRAVA_TOKEN_PATH',
    'MCP_STRAVA_RUNTIME_PROFILE',
    'MCP_STRAVA_HTTP_HOST',
    'MCP_STRAVA_HTTP_PORT',
    'MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS',
    'MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS',
}

_CACHED_SETTINGS: Settings | None = None


def _read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in raw_line:
            continue
        key, value = raw_line.split('=', 1)
        key = key.strip()
        if key in _KEYS:
            values[key] = value
    return values


def _parse_int(raw: str, key: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid integer for {key}: {raw}') from exc


def _validate_ranges(http_port: int, warn_age_hours: int, max_age_hours: int) -> None:
    if http_port < 1 or http_port > 65535:
        raise ValueError('Invalid integer for MCP_STRAVA_HTTP_PORT: out of range')
    if warn_age_hours < 0:
        raise ValueError('Invalid integer for MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS: out of range')
    if max_age_hours < 0:
        raise ValueError('Invalid integer for MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS: out of range')


def load_settings(
    environ: Mapping[str, str] | None = None,
    env_file: str | Path | None = None,
    project_root: str | Path | None = None,
) -> Settings:
    """Load settings without mutating process-global state."""
    env_map = dict(environ) if environ is not None else {}
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    compat_env_path = Path(env_file) if env_file is not None else (root / '.env')

    file_values = _read_env_file(compat_env_path)

    def resolve(key: str, default: str) -> str:
        if key in env_map:
            return env_map[key]
        if key in file_values:
            return file_values[key]
        return default

    database_path = Path(resolve('MCP_STRAVA_DB_PATH', str(root / 'data' / 'strava.db')))
    token_path = Path(resolve('MCP_STRAVA_TOKEN_PATH', str(root / '.env')))
    runtime_profile = resolve('MCP_STRAVA_RUNTIME_PROFILE', 'local')

    http_host = resolve('MCP_STRAVA_HTTP_HOST', '127.0.0.1')
    http_port = _parse_int(resolve('MCP_STRAVA_HTTP_PORT', '8000'), 'MCP_STRAVA_HTTP_PORT')
    warn_age_hours = _parse_int(
        resolve('MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS', '12'),
        'MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS',
    )
    max_age_hours = _parse_int(
        resolve('MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS', '24'),
        'MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS',
    )

    _validate_ranges(http_port, warn_age_hours, max_age_hours)

    return Settings(
        database_path=database_path,
        token_path=token_path,
        runtime_profile=runtime_profile,
        http=HttpSettings(host=http_host, port=http_port),
        freshness=FreshnessSettings(
            warn_age_hours=warn_age_hours,
            max_age_hours=max_age_hours,
        ),
    )


def get_settings(
    environ: Mapping[str, str] | None = None,
    env_file: str | Path | None = None,
    project_root: str | Path | None = None,
) -> Settings:
    global _CACHED_SETTINGS
    if _CACHED_SETTINGS is None:
        _CACHED_SETTINGS = load_settings(environ=environ, env_file=env_file, project_root=project_root)
    return _CACHED_SETTINGS


def reset_settings_cache() -> None:
    global _CACHED_SETTINGS
    _CACHED_SETTINGS = None

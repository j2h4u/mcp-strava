"""Typed runtime settings for mcp_strava."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from mcp_strava.hr_zones import DEFAULT_MODEL_ID, known_model_ids
from mcp_strava.mcp_content import DEFAULT_PROMPT_LANGUAGE, SUPPORTED_PROMPT_LANGUAGES


@dataclass(frozen=True)
class AthleteSettings:
    """Athlete heart-rate anchors. ``hr_rest`` has no default — it must be
    configured by the operator; computations that need it fail fast when unset.
    ``hr_max`` is observed from the mirror, so it is not configured here."""

    hr_rest: int | None
    hr_zone_model: str


@dataclass(frozen=True)
class HttpSettings:
    host: str
    port: int
    allow_container_bind: bool
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class FreshnessSettings:
    warn_age_hours: int
    max_age_hours: int


@dataclass(frozen=True)
class RefreshSettings:
    interval_seconds: int
    stream_backfill_batch_size: int
    read_model_batch_size: int
    full_resync_interval_seconds: int


@dataclass(frozen=True)
class Settings:
    database_path: Path
    token_path: Path
    runtime_profile: str
    prompt_language: str
    athlete: AthleteSettings
    http: HttpSettings
    freshness: FreshnessSettings
    refresh: RefreshSettings


_KEYS = {
    "MCP_STRAVA_DB_PATH",
    "MCP_STRAVA_TOKEN_PATH",
    "MCP_STRAVA_RUNTIME_PROFILE",
    "MCP_STRAVA_HTTP_HOST",
    "MCP_STRAVA_HTTP_PORT",
    "MCP_STRAVA_ALLOW_CONTAINER_BIND",
    "MCP_STRAVA_ALLOWED_HOSTS",
    "MCP_STRAVA_ALLOWED_ORIGINS",
    "MCP_STRAVA_REFRESH_INTERVAL_SECONDS",
    "MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS",
    "MCP_STRAVA_PROJECT_ROOT",
    "MCP_STRAVA_HR_REST",
    "MCP_STRAVA_HR_ZONE_MODEL",
    "MCP_STRAVA_PROMPT_LANGUAGE",
}

_CacheKey = tuple[tuple[tuple[str, str], ...], str | None, str | None]

_CACHED_SETTINGS: dict[_CacheKey, Settings] = {}
CANONICAL_DUCKDB_RUNTIME_PATH = Path("/runtime/data/strava.duckdb")

# Internal tuning constants. These were previously MCP_STRAVA_* env vars, but
# they are not user-facing configuration: no operator tunes them, and they are
# exercised only through injected settings/fakes in tests. They stay as typed
# settings fields populated from these fixed defaults.
FRESHNESS_WARN_AGE_HOURS = 12
FRESHNESS_MAX_AGE_HOURS = 24
STREAM_BACKFILL_BATCH_SIZE = 50
READ_MODEL_BATCH_SIZE = 25


def _read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if key in _KEYS:
            values[key] = value
    return values


def _parse_int(raw: str, key: str) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer for {key}: {raw}") from exc


def _validate_ranges(http_port: int, refresh_interval_seconds: int) -> None:
    if http_port < 1 or http_port > 65535:
        raise ValueError("Invalid integer for MCP_STRAVA_HTTP_PORT: out of range")
    if refresh_interval_seconds < 60:
        raise ValueError("Invalid integer for MCP_STRAVA_REFRESH_INTERVAL_SECONDS: out of range")


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes"}


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _default_database_path(root: Path, runtime_profile: str) -> Path:
    if runtime_profile in {"docker", "container", "live"}:
        return CANONICAL_DUCKDB_RUNTIME_PATH
    return root / "data" / "strava.duckdb"


def _resolve_project_root(
    env_map: Mapping[str, str],
    file_values: Mapping[str, str],
    project_root: str | Path | None,
) -> Path:
    if project_root is not None:
        return Path(project_root)
    if env_root := env_map.get("MCP_STRAVA_PROJECT_ROOT"):
        return Path(env_root)
    if file_root := file_values.get("MCP_STRAVA_PROJECT_ROOT"):
        return Path(file_root)
    return Path.cwd()


def _cache_key(
    environ: Mapping[str, str] | None,
    env_file: str | Path | None,
    project_root: str | Path | None,
) -> _CacheKey:
    env_map = os.environ if environ is None else environ
    relevant_env = tuple(sorted((key, env_map[key]) for key in _KEYS if key in env_map))
    env_file_key = str(Path(env_file)) if env_file is not None else None
    project_root_key = str(Path(project_root)) if project_root is not None else None
    return (relevant_env, env_file_key, project_root_key)


def load_settings(
    environ: Mapping[str, str] | None = None,
    env_file: str | Path | None = None,
    project_root: str | Path | None = None,
) -> Settings:
    """Load settings without mutating process-global state."""
    env_map = dict(os.environ if environ is None else environ)
    explicit_file_values = _read_env_file(Path(env_file)) if env_file is not None else {}
    root = _resolve_project_root(env_map, explicit_file_values, project_root)
    compat_env_path = Path(env_file) if env_file is not None else (root / ".env")

    file_values = explicit_file_values if env_file is not None else _read_env_file(compat_env_path)

    def resolve(key: str, default: str) -> str:
        if key in env_map:
            return env_map[key]
        if key in file_values:
            return file_values[key]
        return default

    runtime_profile = resolve("MCP_STRAVA_RUNTIME_PROFILE", "local")
    database_path = Path(resolve("MCP_STRAVA_DB_PATH", str(_default_database_path(root, runtime_profile))))
    token_path = Path(resolve("MCP_STRAVA_TOKEN_PATH", str(root / ".env")))

    http_host = resolve("MCP_STRAVA_HTTP_HOST", "127.0.0.1")
    http_port = _parse_int(resolve("MCP_STRAVA_HTTP_PORT", "8000"), "MCP_STRAVA_HTTP_PORT")
    allow_container_bind = _parse_bool(resolve("MCP_STRAVA_ALLOW_CONTAINER_BIND", "false"))
    allowed_hosts = _parse_csv(resolve("MCP_STRAVA_ALLOWED_HOSTS", "127.0.0.1,localhost,mcp-strava"))
    allowed_origins = _parse_csv(
        resolve(
            "MCP_STRAVA_ALLOWED_ORIGINS",
            "http://127.0.0.1,http://localhost,http://[::1]",
        )
    )
    refresh_interval_seconds = _parse_int(
        resolve("MCP_STRAVA_REFRESH_INTERVAL_SECONDS", "3600"),
        "MCP_STRAVA_REFRESH_INTERVAL_SECONDS",
    )
    full_resync_interval_seconds = _parse_int(
        resolve("MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS", "604800"),
        "MCP_STRAVA_REFRESH_FULL_RESYNC_INTERVAL_SECONDS",
    )

    hr_rest_raw = resolve("MCP_STRAVA_HR_REST", "").strip()
    hr_rest = _parse_int(hr_rest_raw, "MCP_STRAVA_HR_REST") if hr_rest_raw else None
    if hr_rest is not None and not (20 <= hr_rest <= 120):
        raise ValueError("Invalid integer for MCP_STRAVA_HR_REST: out of range")
    hr_zone_model = resolve("MCP_STRAVA_HR_ZONE_MODEL", DEFAULT_MODEL_ID)
    if hr_zone_model not in known_model_ids():
        raise ValueError(f"Unknown MCP_STRAVA_HR_ZONE_MODEL: {hr_zone_model}; known: {known_model_ids()}")

    prompt_language = resolve("MCP_STRAVA_PROMPT_LANGUAGE", DEFAULT_PROMPT_LANGUAGE).strip().lower()
    if prompt_language not in SUPPORTED_PROMPT_LANGUAGES:
        raise ValueError(
            f"Unknown MCP_STRAVA_PROMPT_LANGUAGE: {prompt_language}; supported: {SUPPORTED_PROMPT_LANGUAGES}"
        )

    _validate_ranges(http_port, refresh_interval_seconds)

    return Settings(
        database_path=database_path,
        token_path=token_path,
        runtime_profile=runtime_profile,
        prompt_language=prompt_language,
        athlete=AthleteSettings(
            hr_rest=hr_rest,
            hr_zone_model=hr_zone_model,
        ),
        http=HttpSettings(
            host=http_host,
            port=http_port,
            allow_container_bind=allow_container_bind,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
        freshness=FreshnessSettings(
            warn_age_hours=FRESHNESS_WARN_AGE_HOURS,
            max_age_hours=FRESHNESS_MAX_AGE_HOURS,
        ),
        refresh=RefreshSettings(
            interval_seconds=refresh_interval_seconds,
            stream_backfill_batch_size=STREAM_BACKFILL_BATCH_SIZE,
            read_model_batch_size=READ_MODEL_BATCH_SIZE,
            full_resync_interval_seconds=full_resync_interval_seconds,
        ),
    )


def get_settings(
    environ: Mapping[str, str] | None = None,
    env_file: str | Path | None = None,
    project_root: str | Path | None = None,
) -> Settings:
    key = _cache_key(environ=environ, env_file=env_file, project_root=project_root)
    if key not in _CACHED_SETTINGS:
        _CACHED_SETTINGS[key] = load_settings(environ=environ, env_file=env_file, project_root=project_root)
    return _CACHED_SETTINGS[key]


def reset_settings_cache() -> None:
    _CACHED_SETTINGS.clear()


# ---------------------------------------------------------------------------
# Strava client credential accessor (D-06)
# ---------------------------------------------------------------------------
# Credentials live in the token file (settings.token_path), NOT in env vars.
# The token-file keys use Strava's own naming convention (STRAVA_CLIENT_ID /
# STRAVA_CLIENT_SECRET), which is intentionally different from the MCP_STRAVA_*
# env-var namespace so they are never confused.  They are NOT in _KEYS and
# load_settings() never reads or validates them — the read-only mirror path
# must remain credential-free.
#
# Call required_strava_client_creds(settings) only when creds are actually
# needed (StravaClient / build_refresh_collaborators construction).  It raises
# RuntimeError with missing keys + token_path so the caller gets an actionable
# message, matching the existing bootstrap._required_strava_client semantics.


def _read_token_file_values(token_path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE token file, skipping comments and blank lines."""
    values: dict[str, str] = {}
    if not token_path.exists():
        return values
    for raw_line in token_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def required_strava_client_creds(settings: Settings) -> tuple[str, str]:
    """Return (client_id, client_secret) from the token file.

    Raises RuntimeError naming the missing keys and token_path when either
    credential is absent.  Never called from load_settings() — the read-only
    mirror path must load settings without Strava creds.
    """
    values = _read_token_file_values(settings.token_path)
    required = ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(f"Missing Strava client settings: {', '.join(missing)}. Check {settings.token_path}")
    return values["STRAVA_CLIENT_ID"], values["STRAVA_CLIENT_SECRET"]

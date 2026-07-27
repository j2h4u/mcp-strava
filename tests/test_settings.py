from pathlib import Path

import pytest

from mcp_strava.settings import get_settings, load_settings, reset_settings_cache


def test_load_settings_defaults() -> None:
    settings = load_settings(environ={}, project_root=Path("/tmp/project"))

    assert settings.database_path == Path("/tmp/project/data/strava.duckdb")
    assert settings.token_path == Path("/tmp/project/.env")
    assert settings.runtime_profile == "local"
    assert settings.http.host == "127.0.0.1"
    assert settings.http.port == 8000
    assert settings.http.allow_container_bind is False
    assert settings.http.allowed_hosts == ("127.0.0.1", "localhost", "mcp-strava")
    assert settings.http.allowed_origins == (
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]",
    )
    assert settings.freshness.warn_age_hours == 12
    assert settings.freshness.max_age_hours == 24
    assert settings.refresh.interval_seconds == 3600
    assert settings.refresh.stream_backfill_batch_size == 50
    assert settings.refresh.read_model_batch_size == 25
    assert settings.prompt_language == "en"


def test_prompt_language_defaults_overrides_and_rejects_invalid() -> None:
    root = Path("/tmp/project")
    assert load_settings(environ={}, project_root=root).prompt_language == "en"
    # Case-insensitive, normalized to lowercase.
    assert load_settings(environ={"MCP_STRAVA_PROMPT_LANGUAGE": "RU"}, project_root=root).prompt_language == "ru"
    with pytest.raises(ValueError, match="MCP_STRAVA_PROMPT_LANGUAGE"):
        load_settings(environ={"MCP_STRAVA_PROMPT_LANGUAGE": "fr"}, project_root=root)


def test_load_settings_defaults_to_current_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    settings = load_settings(environ={})

    assert settings.database_path == tmp_path / "data" / "strava.duckdb"
    assert settings.token_path == tmp_path / ".env"


def test_container_runtime_database_path_is_canonical_duckdb_path() -> None:
    import mcp_strava.settings as settings_module

    settings = load_settings(
        environ={"MCP_STRAVA_RUNTIME_PROFILE": "docker"},
        project_root=Path("/tmp/project"),
    )

    assert settings.database_path == Path("/runtime/data/strava.duckdb")
    assert "MCP_STRAVA_DB_PATH" in settings_module._KEYS
    assert "MCP_STRAVA_DUCKDB_PATH" not in settings_module._KEYS


def test_load_settings_reads_process_environment_when_environ_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "MCP_STRAVA_TOKEN_PATH",
        "MCP_STRAVA_RUNTIME_PROFILE",
        "MCP_STRAVA_HTTP_HOST",
        "MCP_STRAVA_HTTP_PORT",
        "MCP_STRAVA_ALLOW_CONTAINER_BIND",
        "MCP_STRAVA_ALLOWED_HOSTS",
        "MCP_STRAVA_ALLOWED_ORIGINS",
        "MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS",
        "MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS",
        "MCP_STRAVA_REFRESH_INTERVAL_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MCP_STRAVA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_STRAVA_DB_PATH", str(tmp_path / "custom.db"))

    settings = load_settings()

    assert settings.database_path == tmp_path / "custom.db"
    assert settings.token_path == tmp_path / ".env"


def test_load_settings_environment_overrides() -> None:
    env = {
        "MCP_STRAVA_DB_PATH": "/tmp/custom/db.duckdb",
        "MCP_STRAVA_TOKEN_PATH": "/tmp/custom/token.env",
        "MCP_STRAVA_RUNTIME_PROFILE": "docker",
        "MCP_STRAVA_HTTP_HOST": "0.0.0.0",
        "MCP_STRAVA_HTTP_PORT": "8123",
        "MCP_STRAVA_ALLOW_CONTAINER_BIND": "true",
        "MCP_STRAVA_ALLOWED_HOSTS": "api.local,mcp-strava",
        "MCP_STRAVA_ALLOWED_ORIGINS": "https://app.local,http://localhost:3000",
        "MCP_STRAVA_REFRESH_INTERVAL_SECONDS": "7200",
    }

    settings = load_settings(environ=env, project_root=Path("/tmp/project"))

    assert settings.database_path == Path("/tmp/custom/db.duckdb")
    assert settings.token_path == Path("/tmp/custom/token.env")
    assert settings.runtime_profile == "docker"
    assert settings.http.host == "0.0.0.0"
    assert settings.http.port == 8123
    assert settings.http.allow_container_bind is True
    assert settings.http.allowed_hosts == ("api.local", "mcp-strava")
    assert settings.http.allowed_origins == ("https://app.local", "http://localhost:3000")
    assert settings.refresh.interval_seconds == 7200


def test_load_settings_env_file_compatibility(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(  # noqa: FLY002 — multi-line list reads far better than one giant literal
            [
                "# comment",
                "   # spaced comment",
                "",
                "MCP_STRAVA_DB_PATH=/tmp/with=equals.db",
                "MCP_STRAVA_TOKEN_PATH=/tmp/token.env",
                "MCP_STRAVA_RUNTIME_PROFILE=dev",
                "MCP_STRAVA_HTTP_HOST=localhost",
                "MCP_STRAVA_HTTP_PORT=8011",
                "MCP_STRAVA_ALLOW_CONTAINER_BIND=yes",
                "MCP_STRAVA_ALLOWED_HOSTS=127.0.0.1,localhost,mcp-strava",
                "MCP_STRAVA_ALLOWED_ORIGINS=http://127.0.0.1,http://localhost",
                "MCP_STRAVA_REFRESH_INTERVAL_SECONDS=5400",
                "IGNORED_KEY=ignored",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(environ={}, env_file=env_file, project_root=Path("/tmp/project"))

    assert settings.database_path == Path("/tmp/with=equals.db")
    assert settings.token_path == Path("/tmp/token.env")
    assert settings.runtime_profile == "dev"
    assert settings.http.host == "localhost"
    assert settings.http.port == 8011
    assert settings.http.allow_container_bind is True
    assert settings.http.allowed_hosts == ("127.0.0.1", "localhost", "mcp-strava")
    assert settings.http.allowed_origins == ("http://127.0.0.1", "http://localhost")
    assert settings.refresh.interval_seconds == 5400


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("anything", False),
    ],
)
def test_load_settings_parses_allow_container_bind(raw: str, expected: bool) -> None:
    settings = load_settings(
        environ={"MCP_STRAVA_ALLOW_CONTAINER_BIND": raw},
        project_root=Path("/tmp/project"),
    )
    assert settings.http.allow_container_bind is expected


def test_explicit_environ_wins_over_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MCP_STRAVA_DB_PATH=/tmp/from-file.db\n", encoding="utf-8")

    settings = load_settings(
        environ={"MCP_STRAVA_DB_PATH": "/tmp/from-env.db"},
        env_file=env_file,
        project_root=Path("/tmp/project"),
    )

    assert settings.database_path == Path("/tmp/from-env.db")


def test_get_settings_cache_can_be_reset(tmp_path: Path) -> None:
    reset_settings_cache()

    env_one = {
        "MCP_STRAVA_DB_PATH": str(tmp_path / "first.db"),
        "MCP_STRAVA_TOKEN_PATH": str(tmp_path / "first.env"),
    }
    first = get_settings(environ=env_one, project_root=tmp_path)

    env_two = {
        "MCP_STRAVA_DB_PATH": str(tmp_path / "second.db"),
        "MCP_STRAVA_TOKEN_PATH": str(tmp_path / "second.env"),
    }
    second = get_settings(environ=env_two, project_root=tmp_path)

    assert first is not second
    assert second.database_path == tmp_path / "second.db"

    reset_settings_cache()
    third = get_settings(environ=env_two, project_root=tmp_path)
    assert third.database_path == tmp_path / "second.db"
    assert third is not second


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("MCP_STRAVA_HTTP_PORT", "bad"),
        ("MCP_STRAVA_HTTP_PORT", "70000"),
        ("MCP_STRAVA_REFRESH_INTERVAL_SECONDS", "bad"),
        ("MCP_STRAVA_REFRESH_INTERVAL_SECONDS", "59"),
    ],
)
def test_load_settings_rejects_invalid_port(key: str, value: str) -> None:
    environ = {key: value}

    with pytest.raises(ValueError, match=key):
        load_settings(environ=environ, project_root=Path("/tmp/project"))


def test_athlete_hr_rest_has_no_default() -> None:
    settings = load_settings(environ={}, project_root=Path("/tmp/project"))
    assert settings.athlete.hr_rest is None
    assert settings.athlete.hr_zone_model == "karvonen_hrr"


def test_athlete_hr_rest_parsed_when_set() -> None:
    settings = load_settings(environ={"MCP_STRAVA_HR_REST": "53"}, project_root=Path("/tmp/project"))
    assert settings.athlete.hr_rest == 53


def test_athlete_hr_rest_out_of_range_rejected() -> None:
    with pytest.raises(ValueError, match="MCP_STRAVA_HR_REST"):
        load_settings(environ={"MCP_STRAVA_HR_REST": "5"}, project_root=Path("/tmp/project"))


def test_unknown_hr_zone_model_rejected() -> None:
    with pytest.raises(ValueError, match="MCP_STRAVA_HR_ZONE_MODEL"):
        load_settings(environ={"MCP_STRAVA_HR_ZONE_MODEL": "bogus"}, project_root=Path("/tmp/project"))


def test_read_token_file_values_parses_credentials(tmp_path: Path) -> None:
    from mcp_strava.settings import _read_token_file_values

    token_file = tmp_path / "token.env"
    token_file.write_text(
        "\n".join(  # noqa: FLY002 — multi-line token file literal reads better than one giant string
            [
                "# comment",
                "STRAVA_CLIENT_ID=12345",
                "STRAVA_CLIENT_SECRET=abcdef",
                "  # indented comment",
                "OTHER_KEY=value",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    values = _read_token_file_values(token_file)
    assert values["STRAVA_CLIENT_ID"] == "12345"
    assert values["STRAVA_CLIENT_SECRET"] == "abcdef"
    assert values["OTHER_KEY"] == "value"


def test_read_token_file_values_returns_empty_for_missing_file(tmp_path: Path) -> None:
    from mcp_strava.settings import _read_token_file_values

    values = _read_token_file_values(tmp_path / "nonexistent.env")
    assert values == {}


def test_required_strava_client_creds_returns_credentials(tmp_path: Path) -> None:
    from mcp_strava.settings import (
        AthleteSettings,
        FreshnessSettings,
        HttpSettings,
        RefreshSettings,
        Settings,
        required_strava_client_creds,
    )

    token_file = tmp_path / "token.env"
    token_file.write_text("STRAVA_CLIENT_ID=12345\nSTRAVA_CLIENT_SECRET=secret\n", encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "db.duckdb",
        token_path=token_file,
        runtime_profile="local",
        prompt_language="en",
        athlete=AthleteSettings(hr_rest=None, hr_zone_model="karvonen_hrr"),
        http=HttpSettings(host="127.0.0.1", port=8000, allow_container_bind=False, allowed_hosts=(), allowed_origins=()),
        freshness=FreshnessSettings(warn_age_hours=12, max_age_hours=24),
        refresh=RefreshSettings(
            interval_seconds=3600, stream_backfill_batch_size=50, read_model_batch_size=25, full_resync_interval_seconds=604800
        ),
    )
    client_id, client_secret = required_strava_client_creds(settings)
    assert client_id == "12345"
    assert client_secret == "secret"


def test_required_strava_client_creds_raises_on_missing_token_path(tmp_path: Path) -> None:
    from mcp_strava.settings import (
        AthleteSettings,
        FreshnessSettings,
        HttpSettings,
        RefreshSettings,
        Settings,
        required_strava_client_creds,
    )

    settings = Settings(
        database_path=tmp_path / "db.duckdb",
        token_path=tmp_path / "nonexistent.env",
        runtime_profile="local",
        prompt_language="en",
        athlete=AthleteSettings(hr_rest=None, hr_zone_model="karvonen_hrr"),
        http=HttpSettings(host="127.0.0.1", port=8000, allow_container_bind=False, allowed_hosts=(), allowed_origins=()),
        freshness=FreshnessSettings(warn_age_hours=12, max_age_hours=24),
        refresh=RefreshSettings(
            interval_seconds=3600, stream_backfill_batch_size=50, read_model_batch_size=25, full_resync_interval_seconds=604800
        ),
    )
    with pytest.raises(RuntimeError, match="Missing Strava client settings"):
        required_strava_client_creds(settings)


def test_required_strava_client_creds_raises_on_partial_credentials(tmp_path: Path) -> None:
    from mcp_strava.settings import (
        AthleteSettings,
        FreshnessSettings,
        HttpSettings,
        RefreshSettings,
        Settings,
        required_strava_client_creds,
    )

    token_file = tmp_path / "token.env"
    token_file.write_text("STRAVA_CLIENT_ID=12345\n", encoding="utf-8")
    settings = Settings(
        database_path=tmp_path / "db.duckdb",
        token_path=token_file,
        runtime_profile="local",
        prompt_language="en",
        athlete=AthleteSettings(hr_rest=None, hr_zone_model="karvonen_hrr"),
        http=HttpSettings(host="127.0.0.1", port=8000, allow_container_bind=False, allowed_hosts=(), allowed_origins=()),
        freshness=FreshnessSettings(warn_age_hours=12, max_age_hours=24),
        refresh=RefreshSettings(
            interval_seconds=3600, stream_backfill_batch_size=50, read_model_batch_size=25, full_resync_interval_seconds=604800
        ),
    )
    with pytest.raises(RuntimeError, match="Missing Strava client settings"):
        required_strava_client_creds(settings)

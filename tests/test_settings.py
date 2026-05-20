from pathlib import Path

import pytest

from mcp_strava.settings import get_settings, load_settings, reset_settings_cache


def test_load_settings_defaults() -> None:
    settings = load_settings(environ={}, project_root=Path('/tmp/project'))

    assert settings.database_path == Path('/tmp/project/data/strava.db')
    assert settings.token_path == Path('/tmp/project/.env')
    assert settings.runtime_profile == 'local'
    assert settings.http.host == '127.0.0.1'
    assert settings.http.port == 8000
    assert settings.freshness.warn_age_hours == 12
    assert settings.freshness.max_age_hours == 24


def test_load_settings_environment_overrides() -> None:
    env = {
        'MCP_STRAVA_DB_PATH': '/tmp/custom/db.sqlite',
        'MCP_STRAVA_TOKEN_PATH': '/tmp/custom/token.env',
        'MCP_STRAVA_RUNTIME_PROFILE': 'docker',
        'MCP_STRAVA_HTTP_HOST': '0.0.0.0',
        'MCP_STRAVA_HTTP_PORT': '8123',
        'MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS': '8',
        'MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS': '20',
    }

    settings = load_settings(environ=env, project_root=Path('/tmp/project'))

    assert settings.database_path == Path('/tmp/custom/db.sqlite')
    assert settings.token_path == Path('/tmp/custom/token.env')
    assert settings.runtime_profile == 'docker'
    assert settings.http.host == '0.0.0.0'
    assert settings.http.port == 8123
    assert settings.freshness.warn_age_hours == 8
    assert settings.freshness.max_age_hours == 20


def test_load_settings_env_file_compatibility(tmp_path: Path) -> None:
    env_file = tmp_path / '.env'
    env_file.write_text(
        '\n'.join(
            [
                '# comment',
                '   # spaced comment',
                '',
                'MCP_STRAVA_DB_PATH=/tmp/with=equals.db',
                'MCP_STRAVA_TOKEN_PATH=/tmp/token.env',
                'MCP_STRAVA_RUNTIME_PROFILE=dev',
                'MCP_STRAVA_HTTP_HOST=localhost',
                'MCP_STRAVA_HTTP_PORT=8011',
                'MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS=7',
                'MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS=30',
                'IGNORED_KEY=ignored',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    settings = load_settings(environ={}, env_file=env_file, project_root=Path('/tmp/project'))

    assert settings.database_path == Path('/tmp/with=equals.db')
    assert settings.token_path == Path('/tmp/token.env')
    assert settings.runtime_profile == 'dev'
    assert settings.http.host == 'localhost'
    assert settings.http.port == 8011
    assert settings.freshness.warn_age_hours == 7
    assert settings.freshness.max_age_hours == 30


def test_explicit_environ_wins_over_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / '.env'
    env_file.write_text('MCP_STRAVA_DB_PATH=/tmp/from-file.db\n', encoding='utf-8')

    settings = load_settings(
        environ={'MCP_STRAVA_DB_PATH': '/tmp/from-env.db'},
        env_file=env_file,
        project_root=Path('/tmp/project'),
    )

    assert settings.database_path == Path('/tmp/from-env.db')


def test_get_settings_cache_can_be_reset(tmp_path: Path) -> None:
    reset_settings_cache()

    env_one = {
        'MCP_STRAVA_DB_PATH': str(tmp_path / 'first.db'),
        'MCP_STRAVA_TOKEN_PATH': str(tmp_path / 'first.env'),
    }
    first = get_settings(environ=env_one, project_root=tmp_path)

    env_two = {
        'MCP_STRAVA_DB_PATH': str(tmp_path / 'second.db'),
        'MCP_STRAVA_TOKEN_PATH': str(tmp_path / 'second.env'),
    }
    second = get_settings(environ=env_two, project_root=tmp_path)

    assert first is second
    assert second.database_path == tmp_path / 'first.db'

    reset_settings_cache()
    third = get_settings(environ=env_two, project_root=tmp_path)
    assert third.database_path == tmp_path / 'second.db'


@pytest.mark.parametrize(
    ('key', 'value'),
    [
        ('MCP_STRAVA_HTTP_PORT', 'bad'),
        ('MCP_STRAVA_HTTP_PORT', '70000'),
        ('MCP_STRAVA_FRESHNESS_WARN_AGE_HOURS', 'x'),
        ('MCP_STRAVA_FRESHNESS_MAX_AGE_HOURS', 'y'),
    ],
)
def test_load_settings_rejects_invalid_port(key: str, value: str) -> None:
    environ = {key: value}

    with pytest.raises(ValueError, match=key):
        load_settings(environ=environ, project_root=Path('/tmp/project'))

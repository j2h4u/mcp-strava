"""Contract tests for the Markdown-backed MCP prompt loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_strava.mcp_content import (
    DEFAULT_PROMPT_LANGUAGE,
    MCP_PROMPT_NAMES,
    content_root,
    load_prompt,
)

# ═══════════════════════════════════════════════════════════════════
#  Successful loading
# ═══════════════════════════════════════════════════════════════════


def test_load_prompt_english_default():
    """English prompt loads by default and is non-empty."""
    for name in MCP_PROMPT_NAMES:
        text = load_prompt(name)
        assert isinstance(text, str)
        assert len(text) > 0
        assert text == text.strip()


def test_load_prompt_russian():
    """Russian prompt files load when language='ru' is requested."""
    for name in MCP_PROMPT_NAMES:
        text = load_prompt(name, language="ru")
        assert isinstance(text, str)
        assert len(text) > 0


def test_load_prompt_english_and_russian_are_different():
    """Russian localization is not a silent fallback to English."""
    for name in MCP_PROMPT_NAMES:
        en = load_prompt(name, language="en")
        ru = load_prompt(name, language="ru")
        assert en != ru, f"{name}: ru prompt must differ from en prompt"


# ═══════════════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════════════


def test_load_prompt_unknown_name_raises():
    """Unknown prompt names are rejected before any filesystem access."""
    with pytest.raises(ValueError, match="Unknown MCP prompt"):
        load_prompt("not_a_prompt")


def test_load_prompt_unsupported_language_raises():
    """Unsupported languages are rejected even for valid prompt names."""
    with pytest.raises(ValueError, match="Unsupported MCP prompt language"):
        load_prompt(MCP_PROMPT_NAMES[0], language="fr")


def test_load_prompt_missing_file_raises(tmp_path: Path):
    """A configured content directory without the requested file raises FileNotFoundError."""
    empty_dir = tmp_path / "mcp-content" / "prompts"
    empty_dir.mkdir(parents=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("MCP_STRAVA_MCP_CONTENT_PATH", str(tmp_path / "mcp-content"))
    try:
        with pytest.raises(FileNotFoundError, match="MCP prompt content not found"):
            load_prompt(MCP_PROMPT_NAMES[0])
    finally:
        monkeypatch.undo()


# ═══════════════════════════════════════════════════════════════════
#  Path resolution
# ═══════════════════════════════════════════════════════════════════


def test_content_root_env_override(tmp_path: Path):
    """MCP_STRAVA_MCP_CONTENT_PATH overrides the default lookup."""
    custom_root = tmp_path / "custom-content"
    custom_root.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("MCP_STRAVA_MCP_CONTENT_PATH", str(custom_root))
    try:
        assert content_root() == custom_root
    finally:
        monkeypatch.undo()


def test_content_root_falls_back_to_cwd_or_package(monkeypatch):
    """When no env var is set, content_root resolves against the working tree."""
    monkeypatch.delenv("MCP_STRAVA_MCP_CONTENT_PATH", raising=False)
    root = content_root()
    assert root.exists()
    assert (root / "prompts" / f"{MCP_PROMPT_NAMES[0]}.md").exists()


# ═══════════════════════════════════════════════════════════════════
#  Filename helper
# ═══════════════════════════════════════════════════════════════════


def test_prompt_filename_uses_bare_name_for_default_language():
    """Default language maps to '<name>.md'."""
    from mcp_strava.mcp_content import _prompt_filename

    assert _prompt_filename("strava_daily_training_brief", DEFAULT_PROMPT_LANGUAGE) == "strava_daily_training_brief.md"


def test_prompt_filename_adds_language_suffix():
    """Non-default languages map to '<name>_<lang>.md'."""
    from mcp_strava.mcp_content import _prompt_filename

    assert _prompt_filename("strava_daily_training_brief", "ru") == "strava_daily_training_brief_ru.md"

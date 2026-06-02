"""Markdown-backed MCP content loader."""

from __future__ import annotations

import os
from pathlib import Path

MCP_PROMPT_NAMES = (
    "strava_daily_training_brief",
    "strava_weekly_training_digest",
    "strava_shoe_mileage_watchdog",
)

_CONTENT_ENV = "MCP_STRAVA_MCP_CONTENT_PATH"

# Prompt language. English is the canonical default and lives in the bare
# ``<name>.md`` file; every other supported language is a ``<name>_<lang>.md``
# sibling. Keep this list in sync with the shipped ``mcp-content/prompts`` files.
SUPPORTED_PROMPT_LANGUAGES = ("en", "ru")
DEFAULT_PROMPT_LANGUAGE = "en"


def content_root() -> Path:
    candidates: list[Path] = []
    configured = os.environ.get(_CONTENT_ENV)
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            Path.cwd() / "mcp-content",
            Path(__file__).resolve().parents[2] / "mcp-content",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _prompt_filename(name: str, language: str) -> str:
    if language == DEFAULT_PROMPT_LANGUAGE:
        return f"{name}.md"
    return f"{name}_{language}.md"


def load_prompt(name: str, language: str = DEFAULT_PROMPT_LANGUAGE) -> str:
    if name not in MCP_PROMPT_NAMES:
        raise ValueError(f"Unknown MCP prompt: {name}")
    if language not in SUPPORTED_PROMPT_LANGUAGES:
        raise ValueError(f"Unsupported MCP prompt language: {language}; supported: {SUPPORTED_PROMPT_LANGUAGES}")
    path = content_root() / "prompts" / _prompt_filename(name, language)
    if not path.exists():
        raise FileNotFoundError(f"MCP prompt content not found: {path}")
    return path.read_text(encoding="utf-8").strip()

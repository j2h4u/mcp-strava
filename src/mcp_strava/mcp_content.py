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


def load_prompt(name: str) -> str:
    if name not in MCP_PROMPT_NAMES:
        raise ValueError(f"Unknown MCP prompt: {name}")
    path = content_root() / "prompts" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"MCP prompt content not found: {path}")
    return path.read_text(encoding="utf-8").strip()

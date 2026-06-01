"""Structured stdout events for deployed service processes."""

from __future__ import annotations

import json


def emit_service_event(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)

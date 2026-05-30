"""Real-time clock and sleeper implementations for the Strava adapter (D-07).

SystemClock and SystemSleeper are the production implementations of the Clock
and Sleeper protocols defined in adapters/strava/types.py.  They replace the
private _RealClock/_RealSleeper in db.py and converge with bootstrap.RealClock/
RealSleeper, which are retained until 12-03/12-04 remove the bootstrap copies.
"""

from __future__ import annotations

import time

from mcp_strava.adapters.strava.types import Clock, Sleeper


class SystemClock:
    """Clock implementation backed by time.time()."""

    def now(self) -> float:
        return time.time()


class SystemSleeper:
    """Sleeper implementation backed by time.sleep()."""

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


# Explicit re-export so type checkers see the Protocol satisfaction.
__all__: list[str] = ["SystemClock", "SystemSleeper"]

# Satisfy Protocol static checks at import time (no runtime cost).
_: Clock = SystemClock()
__: Sleeper = SystemSleeper()
del _, __

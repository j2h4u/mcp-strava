"""Read-model logic-version repository methods."""

from __future__ import annotations

import duckdb

from mcp_strava.adapters.duckdb.read_model_repository_host import ReadModelRepositoryHost
from mcp_strava.adapters.duckdb.repository_models import LogicVersionRow
from mcp_strava.adapters.duckdb.repository_utils import as_int as _as_int


class ReadModelLogicRepositoryMixin(ReadModelRepositoryHost):
    # Read-model logic version (system-managed metric_version source of truth)
    def _max_fact_metric_version(self) -> int | None:
        """Max metric_version present across the four fact tables, or None when
        all are empty. Used as the seed/fallback when the sidecar is unseeded."""
        row = self._fetchone(
            """
            SELECT MAX(metric_version) AS v
            FROM (
                SELECT metric_version FROM activity_metric_facts
                UNION ALL
                SELECT metric_version FROM daily_load_facts
                UNION ALL
                SELECT metric_version FROM training_model_daily
                UNION ALL
                SELECT metric_version FROM rolling_period_facts
            ) all_facts
            """
        )
        if row is None or row.get("v") is None:
            return None
        return _as_int(row["v"])

    def current_logic_version(self) -> LogicVersionRow | None:
        """Return the singleton sidecar row ({metric_version, logic_fingerprint,
        changed_at}) or None when the table is empty/absent (unseeded DB)."""
        try:
            return self._one(
                self._fetchone(
                    """
                    SELECT metric_version, logic_fingerprint, changed_at
                    FROM read_model_logic_version
                    WHERE id=1
                    """
                )
            )
        except duckdb.CatalogException:
            # Sidecar table absent (schema not created yet / fail-soft path) — unseeded.
            return None

    def current_metric_version(self) -> int:
        """Return the system-managed metric_version.

        The sidecar is the single source of truth. The constructor seeds it
        whenever the schema exists, so on a healthy DB `stored` is never None;
        the only None case is the schema-missing fail-soft path (no read model
        yet), where 1 is the sane default. Memoized for the repo lifetime;
        bump_logic_version() clears the memo so a post-bump read sees the new int.
        """
        if self._current_metric_version_cache is not None:
            return self._current_metric_version_cache
        stored = self.current_logic_version()
        resolved = int(stored["metric_version"]) if stored is not None else 1
        self._current_metric_version_cache = resolved
        return resolved

    def bump_logic_version(self, metric_version: int, logic_fingerprint: str, changed_at: str) -> None:
        """Upsert the singleton sidecar row to (metric_version, fingerprint, ts).

        After the upsert commits, invalidate the current_metric_version memo on
        THIS repo instance (cycle-2 HIGH): the recompute path bumps to N+1 and
        immediately needs current_metric_version() to return N+1 so the
        materialize version and the enqueued dirty rows agree. Clearing the memo
        here is the single guaranteed point that closes that — callers never have
        to remember to reset it.
        """
        self._execute(
            """
            INSERT INTO read_model_logic_version (id, metric_version, logic_fingerprint, changed_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                metric_version=excluded.metric_version,
                logic_fingerprint=excluded.logic_fingerprint,
                changed_at=excluded.changed_at
            """,
            [metric_version, logic_fingerprint, changed_at],
        )
        self._commit_if_standalone()
        self._current_metric_version_cache = None

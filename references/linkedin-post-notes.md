# LinkedIn Post Notes

The same local Strava mirror took about 500 MB in SQLite and about 205 MB after moving to DuckDB.
This is a concrete example of how choosing a storage engine that matches the workload can cut storage use by roughly 2.5x.
DuckDB is also a more natural fit for analytics-heavy questions like period comparisons and aggregate training metrics.

# Strava Kudos API — Field Notes

## Endpoint

```
GET /activities/{id}/kudos?per_page=100
```

**Scope:** `activity:read` (same as existing sync)

## Response Format

Array of `SummaryAthlete` objects — **MINIMAL**. Unlike other endpoints, kudos returns a stripped-down athlete:

```json
[
  {
    "resource_state": 2,
    "firstname": "Charles",
    "lastname": "A."
  }
]
```

**Fields present:** `resource_state`, `firstname`, `lastname`
**Fields ABSENT:** `id` — the athlete's Strava ID is NOT included.

This is a known Strava API limitation (documented in community discussions). The full `SummaryAthlete` model includes `id`, `profile_medium`, `city`, `state`, `country`, `sex`, `premium`, etc. — but the kudos endpoint strips all except name fields.

## Implications

1. **Cannot use `athlete_id` as a key** — no unique identifier. Use composite `(activity_id, firstname, lastname)` as primary key. A person cannot kudos the same activity twice, so this combination IS unique.
2. **Cannot join kudos to athlete profile** — no way to correlate kudoers across activities beyond name matching.
3. **Duplicate names possible** — two different people with the same first+last name would collide. Rare, acceptable risk.

## Integration

Kudos sync fetches kudos for activities with `kudos_count > 0` in the last 30 days that aren't yet synced. Cost: 1 API call per activity with unsynced kudos.

First run on May 20, 2026: 13 activities found, all fetched successfully.

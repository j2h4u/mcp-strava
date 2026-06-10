# MCP Server Design Review — 2026-06-10

Grounded review of the MCP surface. Sources read:
`src/mcp_strava/interfaces/mcp_http.py`, `src/mcp_strava/mcp_content.py`,
`mcp-content/prompts/`. SDK: official `mcp` (FastMCP), pinned `mcp>=1.27.2,<1.28`.
Transport: streamable-http, stateless, DNS-rebinding protection + host/origin allowlists.

This is a **design discussion artifact**, not an executed plan. Nothing here is implemented yet.

---

## 1. What is currently exposed

| MCP primitive | Count | Detail |
|---|---|---|
| **Tools** | 6 | `get_fitness_state`, `list_workouts`, `get_workout_detail`, `compare_periods`, `project_fitness_state`, `get_training_aggregates` |
| **Prompts** | 3 | `strava_daily_training_brief`, `strava_weekly_training_digest`, `strava_shoe_mileage_watchdog` (markdown-backed, en + ru via `prompt_language`) |
| **Resources** | **0** | not used at all |
| Server `instructions` | yes | read-only framing: don't invent sync/admin/SQL/token/raw-Strava; expand abbreviations on first use; no medical diagnoses; interpretation belongs to the calling agent (`mcp_http.py:40`) |

All tools share one annotation set (`_tool_annotations()`, `mcp_http.py:55`):
`readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False`.
All declare `structured_output=True` and return the shared envelope
(`data` / `freshness` / `completeness` / `warnings` / `rationale`, `mcp_http.py:64`).

---

## 2. Tools — strengths

- **Annotations are correct and meaningful.** For a local read-only mirror the set is exactly
  right: clients see calls are safe, repeatable, and closed-world (`openWorldHint=False` —
  not hitting the open internet). Good.
- **`structured_output=True`** on every tool; uniform envelope shape.
- **Response cache** on the two expensive tools (`compare_periods`, `get_training_aggregates`),
  30 s TTL, max 32 entries, with pruning (`mcp_http.py:49`, `_run_cached_logged_tool`).
- **Structured logging** with warning *codes* (not just counts) and data-shape summaries
  (`_warning_codes`, `_data_shape`, `mcp_http.py:84`) — self-explanatory operator output.
- **Transport security is well-reasoned** with an explicit single-user threat-model comment
  (`build_transport_security`, `mcp_http.py:178`): no per-request auth, justified by loopback
  default + `expose` (not `ports`) + DNS-rebinding guard. Documents the upgrade path if it ever
  becomes multi-user.

## 3. Tools — weaknesses (where the ROI is)

### 3.1 Parameters are undocumented and enums aren't enums  ← biggest lever
Tool parameters carry only a name + type. The calling agent does **not** know:
- date format for `start_date` / `end_date` (ISO? `YYYY-MM-DD`?);
- valid values for `bucket` (day/week/month?), `scope` (`"global"` default — what else?),
  `scenarios` items, `metric_bundle`, `metric_ids`;
- valid `sport` values.

Today these are plain `str` / `list[str]` (e.g. `bucket: str`, `scope: str = "global"`,
`scenarios: list[str]`, `mcp_http.py:331`, `:352`). The agent guesses and only learns of a bad
value at call time.

**Fix:** convert to `Literal[...]` so they appear as JSON-schema enums, and add
`Annotated[T, Field(description=..., examples=...)]` for formats/semantics. This is the single
highest-value correctness change and is cheap. FastMCP derives the input schema from the
signature + Pydantic `Field`, so this surfaces directly to clients.

### 3.2 `-> dict[str, Any]` makes `structured_output` schema opaque
Every tool returns `dict[str, Any]` (e.g. `mcp_http.py:254`), so the published output schema is
effectively "object" — clients get no real shape. The envelope is already built from dataclasses
(`_envelope_payload`), so typing the return as a TypedDict/Pydantic model would publish a true
output schema. Medium effort, medium value.

### 3.3 Tools have no `title` (cosmetic)
Prompts set `title`; tools don't. `ToolAnnotations` supports a human-friendly `title`. Minor polish.

---

## 4. Prompts

Implemented cleanly (`mcp_http.py:224`–`246`): name / title / description, content loaded from
`mcp-content/prompts/<name>[_<lang>].md`, two locales (en canonical, ru sibling). The 3 scenarios
the owner remembered (daily brief / weekly digest / shoe-mileage watchdog) are all here.

**Limitation:** prompts are **static** — they take no arguments. MCP prompts can accept parameters
(e.g. `strava_daily_training_brief(date, sport)`). Currently each returns a fixed scenario script.
Parametrizing is low effort but only modest value.

---

## 5. Resources / other primitives — feasibility

Distinction that frames the decision:
- **Tool** = action the *model* decides to invoke.
- **Resource** = read-only context by URI that the *application/user* attaches (not the model).
- **Prompt** = user-controlled template (slash-command-like).

Good resource candidates here:
- **Metric glossary** (TRIMP, CTL/ATL/TSB definitions) — directly serves the `instructions`
  mandate to "expand abbreviations on first use". Strong fit.
- **Supported metrics / bundles catalog** (also doubles as enum documentation for `metric_ids`/`metric_bundle`).
- **Mirror freshness / coverage summary** (last sync, activity count).
- **Athlete HR zones / gear list.**

Skip: per-workout resource templates (`strava://workout/{id}`) — duplicates `get_workout_detail`.

### ⚠️ Linchpin (UNVERIFIED): does the gateway forward prompts/resources?
The owner reaches the server **through `docker-mcp-gateway`** (`docker/mcp-gateway:v0.42.1`).
Open question: does that gateway forward **prompts and resources**, or **only tools**?
- If only tools → the 3 prompts are already dead through the gateway path (visible only to a
  direct MCP client), and building resources for that path is wasted.
- This is the load-bearing unknown for all non-tool work. **Verify before investing.**
  How: hit the gateway via `mcp-auth-proxy` with proper MCP `Accept: application/json,
  text/event-stream` headers and list capabilities, or check gateway docs/capability flags.

---

## 6. ROI-ranked recommendations

| Priority | Item | Effort | Value |
|---|---|---|---|
| **1** | `Literal` enums + `Field(description/examples)` on tool params (`interfaces/mcp_http.py`) | low | high — call correctness |
| **2** | Verify gateway forwards prompts/resources | very low | high — gates everything below |
| **3** | Typed output schema (replace `dict[str, Any]`) | medium | medium |
| **4** | Glossary / metric-catalog as a **resource** (gated on #2) | medium | medium |
| **5** | Parametrize prompts (date/sport) | low | low–medium |
| skip | per-workout resource templates; tool `title` | — | cosmetic |

**Recommended order:** do #2 first (cheap, reshapes priorities for prompts/resources), then #1
as the cheapest high-value code change.

---

## 7. Open question to the user (where the thread paused)
"Сначала проверю, что gateway реально отдаёт наружу (tools/prompts/resources), а потом обсудим
конкретику по енумам? Или сразу нырнуть в дизайн параметров тулов?" — awaiting the owner's pick.

---

## 8. Implementation log

**2026-06-11 — gateway forwarding verified (was ROI #2).** Docker MCP Gateway forwards
prompts AND resources (not tools-only). Built `mcp-gateway-watchdog` (container) to auto-restart
the gateway when a backend returns healthy, fixing the recreate-drops-from-discovery quirk. So
the resource/prompt work (tasks 10/11) is worthwhile.

**2026-06-11 — tool-param typing landed (was ROI #1, "task 8").** Every closed-set param is now a
typed enum DERIVED from its canonical domain constant (single source of truth, drift impossible):
`bucket`→`SUPPORTED_AGGREGATE_BUCKETS`, `scope`→`SUPPORTED_AGGREGATE_SCOPES`,
`scenarios`→`SUPPORTED_PROJECTION_SCENARIOS` (newly extracted), `metric_bundle`→`AGGREGATE_METRIC_BUNDLES`,
`window_days`→`SUPPORTED_ROLLING_WINDOW_DAYS`, `sport(s)`→`sports.SPORT_ALL` (all 50). Dates carry
`Field(description=… ISO YYYY-MM-DD …, examples=…)`. The review's guessed bucket set was wrong —
the real set includes `year` and `all_time`.

**2026-06-11 — typed output schema landed (was ROI #3, "task 9").** Tools returned
`-> dict[str, Any]` (opaque `additionalProperties:true` output schema). They now return the
shared `ServiceEnvelope` dataclass, so FastMCP publishes a real `outputSchema`
(`data`/`freshness`/`completeness`/`warnings`/`rationale` + `$defs` for the metadata
dataclasses), reusing the existing contract — no duplicated output model. `_envelope_payload`
rounds only `data` (metadata is float-free). **Still open:** `data` itself stays an open object
(it is a dict or a list per tool); per-tool typed `data` models are a larger separate item.

### Open product question (parked) — bucket semantics
Buckets are **calendar-aligned**, verified against the live SQL (`time_bucket(INTERVAL …)`):
`day`=calendar day, `week`=calendar week **starting Monday**, `month`=calendar month, `year`=calendar
year, `all_time`=whole range. Rolling "last-N-days" is the separate `window_days` axis (7/14/28/42/90).
**To revisit (product call, not yet decided):** whether day/week/month should instead mean rolling
24h/7d/30d, and whether the week-start should be configurable (locale-driven / env-overridable).
Decision deferred — current behavior is documented as-is in the tool descriptions; changing it is a
read-model/SQL behavior change, out of scope for the param-typing slice.

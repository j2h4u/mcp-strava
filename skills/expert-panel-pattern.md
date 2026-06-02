# Expert Panel Pattern

A reusable workflow for hard, multi-disciplinary judgements: take several expert
perspectives over the same facts, surface where they agree and disagree, then synthesize.
Implementation-agnostic — it describes how to run the panel, not any specific tool or codebase.

## Two modes

The pattern is used in two settings. The shape is the same; the inputs, mechanics, and
output differ — keep these differences in mind throughout the process below.

| | **Design-time** (developer) | **Runtime** (agent over a user's data) |
|---|---|---|
| **Trigger** | Designing a new algorithm/metric where disciplines intersect | A user asks a hard training judgement, e.g. "am I overtrained, should I back off before the race?" |
| **Facts given to experts** | Repo/system constraints, athlete profile, existing behavior, literature | The user's actual metrics from the MCP tools, plus their `freshness`/`completeness` |
| **How experts run** | Spawn one subagent per role, in parallel (batch if many) | Usually **inline**: the agent works through each perspective itself. Spawn subagents only if that capability is available and the question warrants the cost |
| **Output** | A design decision — what to build now vs defer — recorded in docs | An interpretation/recommendation for the user, in plain language |
| **Constraints** | Libraries allowed, runtime/execution model, output format | Read-only, facts-not-coaching boundary; no medical diagnosis; explicitly flag partial/stale data |

## When to Use

- Designing a new algorithm/metric where multiple disciplines intersect (design-time)
- Answering a user's complex training question spanning statistics, physiology, coaching, and data quality (runtime)
- Avoiding single-perspective blind spots in either case

## Process

### 1. Define roles (3-5 experts)
Each role gets: name, domain context, problem-specific facts, and explicit questions.

A typical cross-disciplinary roster:
- **Statistician** — algorithm selection, clustering, thresholds
- **Domain clinician / physician** — clinical significance, confounders, false-alarm risk
- **Practitioner / coach** — practical actionability and language for the end user
- **Engineer** — how the result fits the system and what it costs to maintain
- **Domain scientist** — mechanisms and correction factors

(At runtime, the engineer role is usually irrelevant; weight the panel toward coach,
physiologist, and statistician — the disciplines that interpret the athlete's numbers.)

### 2. Give each expert

- **Subject profile**: the facts that constrain the decision — design-time: athlete age, HR zones, training patterns, sensor limitations; runtime: the actual tool results for this user, including data-quality metadata
- **Current context**: what already exists and what the gap/question is
- **Specific questions**: 3-5 targeted questions per role
- **Relevant constraints**: design-time — libraries, runtime/execution model, output language/format; runtime — the read-only boundary and any partial/stale data

### 3. Run the experts

- **Design-time:** spawn experts as parallel subagents; cap concurrency and batch the rest. Give each a detailed brief (context), its specific questions (goal), and only the capabilities it needs (e.g. web access for the researcher, read access for anyone grounding against the system).
- **Runtime:** reason through each perspective inline, one at a time, over the same tool facts. Only spawn subagents if the host supports it and the question is weighty enough to justify it.

### 4. Synthesize

After all perspectives are in:
- Extract consensus points (all agreed → just do it / state it plainly)
- Note disagreements (e.g. clinician says a fixed threshold, coach says context-dependent → resolve as a per-context threshold)
- Build the answer from the synthesis
- Key output: what to do NOW vs what to defer (design-time), or a clear recommendation with its caveats (runtime)

## Anti-Patterns

- Don't give all experts the same questions — they'll produce redundant answers
- Don't skip the synthesis step — raw expert answers are input, not output
- Don't over-engineer from the consensus — commit the 80% that's clear, defer the 20%
- (Runtime) Don't let the panel manufacture certainty the data doesn't support — if the facts are partial/stale, the synthesis must say so

## Example (design-time, illustrative)

A cardiac-drift detection design once used this pattern. Consensus emerged on the clustering
method, a sport-specific significance threshold, treating low-intensity activity as a sentinel
rather than a load source, and avoiding real-time alerts. The one unresolved item (an exact
environmental-correction formula) was explicitly deferred rather than guessed. The takeaway is
the shape of the outcome — clear consensus acted on, one disagreement resolved by scoping, one
unknown deferred — not the specific algorithm.

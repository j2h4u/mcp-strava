# Expert Panel Pattern

Reusable workflow for complex design decisions that span multiple disciplines.
Implementation-agnostic: it describes how to run the panel, not any specific tool or codebase.

## When to Use

- Designing a new algorithm/metric where multiple disciplines intersect
- Stakeholder concerns span statistics, medicine, coaching, and engineering
- Avoiding single-perspective blind spots

## Process

### 1. Define roles (3-5 experts)
Each role gets: name, domain context, problem-specific facts, and explicit questions.

A typical cross-disciplinary roster:
- **Statistician** — algorithm selection, clustering, thresholds
- **Domain clinician / physician** — clinical significance, confounders, false-alarm risk
- **Practitioner / coach** — practical actionability and language for the end user
- **Engineer** — how the result fits the system and what it costs to maintain
- **Domain scientist** — mechanisms and correction factors

### 2. Give each expert

- **Subject profile**: the facts that constrain the decision (for this project: athlete age, HR zones, training patterns, sensor limitations)
- **Current context**: what already exists and what the gap is
- **Specific questions**: 3-5 targeted questions per role
- **Relevant constraints**: libraries allowed, runtime/execution model, output language and format

### 3. Spawn the experts

Run experts as parallel subagents; cap concurrency and batch the rest. Give each one a
detailed brief (context), its specific questions (goal), and only the capabilities it needs
(e.g. web access for the researcher, read access for anyone grounding against the system).

### 4. Synthesize

After all experts return:
- Extract consensus points (all agreed → just do it)
- Note disagreements (e.g. clinician says a fixed threshold, coach says context-dependent → resolve as a per-context threshold)
- Build the plan from the synthesis
- Key output: what to do NOW vs what to defer

## Anti-Patterns

- Don't give all experts the same questions — they'll produce redundant answers
- Don't skip the synthesis step — raw expert answers are input, not output
- Don't over-engineer from the consensus — commit the 80% that's clear, defer the 20%

## Example (illustrative)

A cardiac-drift detection design once used this pattern. Consensus emerged on the clustering
method, a sport-specific significance threshold, treating low-intensity activity as a sentinel
rather than a load source, and avoiding real-time alerts. The one unresolved item (an exact
environmental-correction formula) was explicitly deferred rather than guessed. The takeaway is
the shape of the outcome — clear consensus acted on, one disagreement resolved by scoping, one
unknown deferred — not the specific algorithm.

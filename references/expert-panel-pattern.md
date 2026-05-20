# Expert Panel Pattern

Reusable workflow for complex design decisions. Used for cardiac drift algorithm design (May 2026).

## When to Use

- Designing a new algorithm/metric where multiple disciplines intersect
- Stakeholder concerns span statistics, medicine, coaching, and engineering
- Avoiding single-perspective blind spots

## Process

### 1. Define roles (3-5 experts)
Each role gets: name, domain context, athlete-specific facts, explicit questions.

Roles used for cardiac drift:
- **Спортивный статистик** — algorithm selection, clustering, thresholds
- **Спортивный врач** — clinical significance, confounders, risk of false alarms
- **Тренер по бегу** — practical actionability, language for the athlete
- **Дата-инженер** — integration into existing codebase
- **Физиолог** — mechanisms, altitude/temperature corrections

### 2. Give each expert

- **Athlete profile**: age, HR zones, training patterns, sensor limitations
- **Current system context**: what already exists, what the gap is
- **Specific questions**: 3-5 targeted questions per role
- **Relevant constraints**: no external libs, cron-only, Russian output

### 3. Spawn subagents

Use `delegate_task` with max 3 concurrent. Batch rest.

Each subagent gets: `context` (detailed brief) + `goal` (specific questions) + appropriate `toolsets` (web for research, terminal/file for code).

### 4. Synthesize

After all experts return:
- Extract consensus points (all agreed → just do it)
- Note disagreements (doctor says 10% threshold, coach says context-dependent → sport-specific)
- Build implementation plan from synthesis
- Key output: what to implement NOW vs what to defer

## Anti-Patterns

- Don't give all experts the same questions — they'll produce redundant answers
- Don't skip the synthesis step — raw expert answers are input, not output
- Don't over-engineer from the consensus — implement the 80% that's clear, defer the 20%

## Example: Cardiac Drift Synthesis

Consensus: Jenks > KMeans, 10% threshold for run, walk is sentinel, no real-time alerts.
Disagreement: exact altitude correction formula (deferred).
Implementation: pure Python Jenks, sport-specific thresholds, quality gate.

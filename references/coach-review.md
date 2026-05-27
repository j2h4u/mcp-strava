# Coaching Review — Training Methodology

*Endurance-coaching panel review of the training-load and readiness methodology for a single masters endurance athlete (50+; observed HRmax 191, resting HR 53). Implementation-agnostic: this assesses the training science, not the software.*

## Athlete Context Frames Everything

This is a 50+ recreational endurance athlete whose training is multi-modal — running, hiking, walking, with the door open to riding, skiing, rowing and gym cardio. The dominant real-world activity appears to be long, low-intensity mountain hiking plus shorter runs. Two facts should drive every methodological choice:

1. **Recovery is slower at 50+.** Fatigue clears more slowly than in a 30-year-old. The model correctly reflects this by lengthening the fatigue time constant (decay ~10 days rather than the textbook 7) and by raising the acute:chronic injury threshold to ~1.35 instead of the classic 1.3-1.5 ceiling. Good calls — they bias the system toward caution, which is the right error to make for this athlete.
2. **The athlete trains by feel, not by numbers.** The right job of this system is to *confirm or challenge* how the athlete feels, not to replace that signal. The methodology is closest to ideal when it answers three questions: *How loaded am I? Am I ramping safely? What should today look like?*

## Load Quantification (TRIMP & Zones)

**Assessment: sound, with one honest limitation.**

- HR zones are built off a proper Karvonen reserve scheme (rest 53, max 191) with five working zones plus a discounted recovery band below ~122 bpm. Weighting that recovery band at half rather than zero is a defensible choice — easy aerobic time is not metabolically free, and for a masters athlete who does a lot of low-intensity volume, crediting it partially keeps the chronic-load picture honest. I'd keep it.
- TRIMP is zone-time × zone-weight. This is zone-based TRIMP (Edwards-style), not Banister's exponential HR-weighted TRIMP. That's a reasonable, transparent choice and easy to explain to the athlete. Just be aware it slightly under-weights very high intensity relative to an exponential formula — minor for an athlete who lives in Z1-Z3.
- **The real dependency is HR-data completeness.** Every load number collapses to "what HR samples exist." When a watch drops HR, or an activity has none, the load is structurally understated. The system's habit of distinguishing *observed* load from *effective* load (filling rest/unknown days deliberately rather than silently) is exactly right and should be guarded jealously — a Banister curve fed by silently-missing days will read "fresh" when the athlete is actually undertrained-on-paper but fine in reality, or vice versa.

## Fitness / Fatigue / Form (Banister)

**Assessment: the core is correct and the form simplification is a genuine improvement.**

- Fitness as a 42-day EWMA and fatigue as a ~10-day EWMA of daily load, form = fitness − fatigue. This is the standard impulse-response model, age-tuned on the fatigue side. Good.
- **Form is reported in three plain-language states — tired / normal / fresh** (roughly form < −5, −5 to +10, > +10). This is a meaningful upgrade over the older multi-bucket scheme. A masters athlete cannot *feel* the difference between "optimal" and "transition" and "peaked"; collapsing to three states removes false precision and removes a low-grade source of anxiety (a model whose form sits negative most of the time because of the slow fatigue decay). Keep it at three.
- **One caveat on form zero-point.** With a slow fatigue constant, this athlete's form will read mildly negative during any consistent training block. That is *normal and healthy*, not a red flag. The methodology should keep framing sustained mild-negative form as "training is happening," and reserve concern for *deep* or *fast-deepening* form drops, not for form simply being below zero. The three-zone thresholds already do this reasonably; resist any temptation to tighten them.
- **Forward projection** (simulating form forward under rest/easy/maintain scenarios, including the "where will Monday land if I rest the weekend" question) is a strong, athlete-useful feature. Scenario projection that answers "what happens to my readiness if I do X" is precisely how a coach reasons. This is the most valuable predictive piece in the system.

## Acute:Chronic Workload (ACWR)

**Assessment: directionally right, one conceptual wrinkle to watch.**

- A single EWMA-based acute:chronic ratio with an age-adjusted danger threshold (~1.35) and a sweet-spot band (~0.8-1.3) is the correct modern approach (EWMA, not naive rolling averages — the latter creates the well-known "phantom" load-cliff artifacts). The earlier inconsistency of two competing ACWR definitions is gone; one source of truth is the right state.
- **Wrinkle:** the ratio is effectively short-term-EWMA over long-term-EWMA of the *same* Banister inputs. That's serviceable, but ACWR purists separate acute (≈7-day) and chronic (≈28-day) load explicitly rather than reusing the 10/42 fitness-fatigue constants. The two are correlated but not identical, and reusing the form constants means ACWR and form will sometimes tell slightly redundant stories. **Recommendation:** keep ACWR as a *coupling/ramp-rate* sentinel and let form be the *readiness* signal — present them as answering different questions (ACWR: "am I ramping too fast?"; form: "am I fresh enough today?"), so the athlete doesn't read them as two takes on the same thing. If they're ever going to be unified, unify the *narrative*, not the math.

## Cardiac Efficiency & Aerobic Decoupling

**Assessment: the cleanup here was the single best methodological decision.**

- **Decoupling (Pa:HR) is correctly demoted.** It is only valid for steady-state efforts, and for an athlete who hikes and run/walks on variable terrain it is almost always invalid (pace variability blows past the validity gate). Pulling it out of the headline readiness logic and out of routine enrichment was right — a metric that's N/A 90% of the time and occasionally fires a false "go easy" is worse than no metric.
- **Cardiac cost (avg HR ÷ avg velocity) is the right primary efficiency metric for this athlete**, with an elevation-adjusted variant to strip the terrain penalty. It degrades gracefully, works across variable-pace efforts, and trends cleanly over a 90-day window. This is the metric to watch for "is my aerobic engine improving." **Lower-is-better, tracked per sport, on a long window** — correct on all three counts.
- **Intra-activity cardiac drift via pace-clustering** (cluster pace into bands, compare early-vs-late HR within each band, weight, then judge against a per-sport threshold) is a genuinely sophisticated and *correct* solution to the variable-pace problem that defeats classic decoupling. The per-sport thresholds (run ~10%, trail ~12%, hike ~8%, walk ~6%) reflect real physiology: trail/hike efforts tolerate more drift due to terrain and heat, walks have a low baseline so small drift is more diagnostic. I endorse this design.
- **One residual concern: efficiency is still expressible several ways** (cardiac cost, elevation-adjusted cardiac cost, the drift family, HRR%). For a by-feel athlete this risks "one story told four ways." **Recommendation:** in any *athlete-facing summary*, lead with a single efficiency line (elevation-adjusted cardiac cost trend, per sport) and treat the rest as drill-down. The instruments can all exist; the *headline* should be one number.

## Recovery Signals

**Assessment: good ideas, under-instructed.**

- **HR recovery from in-activity standing pauses** (HR drop rate in bpm/min during genuine stops) is a clever way to harvest a recovery signal from normal training without a dedicated test. Higher drop-rate = better parasympathetic reactivation = a real, trendable autonomic-fitness marker. The median-of-pauses approach is the right robust statistic.
- **Gap:** the signal is silent on continuous efforts with no stops (a steady run produces no pauses → no data). The methodology should explicitly tell the athlete *when the metric is absent and what to do about it* — e.g. "no qualifying pauses today; if you want a recovery read, finish with a 60-second standing stop." A recovery metric that quietly disappears teaches the athlete nothing. **Recommendation:** add that guidance, and consider trending the rolling median rather than reacting to any single session (single pauses are noisy).
- **HRR% (median HR as a fraction of heart-rate reserve)** is a solid intensity descriptor and a sensible companion to TRIMP. Keep it.

## Sport-Specific Handling

**Assessment: thoughtfully differentiated — this is a strength.**

- **Walking is excluded from training load while still being analyzed** for HR and efficiency. This is the correct masters-athlete call: counting every stroll as training would inflate chronic load and corrupt ACWR. The earlier "walk × 0.3" fudge is gone; binary "walk doesn't build Banister fitness, but we still watch its HR cost" is cleaner and physiologically defensible.
- **Hiking counts as training** (it should — multi-hour Z1-Z2 mountain time is real aerobic work) with its own efficiency windows and a drift threshold tuned for terrain. Vertical speed (m/h ascending) is tracked, which is the *right* performance metric for a hiker — it's their analog of running pace. Good.
- **Running biomechanics are flagged separately** from generic cardio, so pace-based logic only fires where it's valid. Cycling, skiing, rowing, gym cardio all carry sensible training/efficiency defaults, and unknown sports default to non-training — a safe, conservative posture.
- **Recommendation:** for the hiker specifically, elevate the *vertical-speed trend* and *elevation-adjusted cardiac cost on climbs* to first-class progress signals. For this athlete, "am I climbing faster at the same HR cost" is a more honest fitness verdict than flat-ground pace will ever be.

## Things I Would Stop Computing (or Bury)

- **VO₂max estimation without lab data** carries ±3 ml/kg/min error — enough to swing a masters athlete between "age-normal" and "excellent" on noise. It does not belong in routine readiness. Reserve it for an annual retrospective with an explicit error-band disclaimer, or drop it.
- **Year-over-year comparison** is near-meaningless for an aging athlete: a 364-day delta confounds season, weight, illness, motivation and age-decline. Useful at most once a year as reflection, never as a routine signal.
- **Short-window (sub-3-week) trend lines** on sparse, mixed-sport data are statistical noise — a handful of points cannot support a trend claim. Keep efficiency trends on the long (≥90-day) window only.

## What's Missing (Highest-Value Addition)

**A subjective wellness input is the single biggest gap.** Every objective signal here is downstream of HR and movement. None of them capture sleep, soreness, life stress, or "I just feel flat" — and for a 50+ athlete those frequently *lead* the objective markers by days. The model is methodologically incomplete without a daily 1-5 self-rating (energy / legs / motivation) folded into the readiness verdict. A coach always asks "how do you feel?" before reading the watch; the system should too. **Make this the next addition.** When subjective and objective disagree, the methodology should *surface the disagreement* rather than overriding feel with numbers — that disagreement is itself the most coaching-relevant signal there is.

## Priority Summary

1. **(High) Add a subjective daily wellness rating** and fold it into the readiness verdict; surface objective-vs-subjective disagreement explicitly.
2. **(High) Give HR-recovery a presence-and-guidance contract** — say when it's absent, suggest a standing-recovery test, and trend the rolling median instead of single sessions.
3. **(Medium) Separate the ACWR and form narratives** so they answer distinct questions (ramp-rate vs readiness) rather than reading as redundant; consider giving ACWR its own explicit 7/28-day load basis.
4. **(Medium) One efficiency headline** (elevation-adjusted cardiac cost, per sport, long window); demote the rest to drill-down.
5. **(Medium) For the hiker, promote vertical-speed and climb-cost trends** to first-class fitness verdicts.
6. **(Low) Confine VO₂max and year-over-year to an annual retrospective** with disclaimers; drop short-window trend lines.

## Bottom Line

The methodology has matured into something a coach can largely endorse: age-tuned Banister, a sane three-state readiness signal, an EWMA ramp-rate guardrail, an efficiency suite that correctly abandoned fragile steady-state decoupling in favor of pace-clustered drift and cardiac cost, genuine masters-athlete safety checks (prolonged-Z5 and HR-anomaly flags), and sport handling that refuses to treat a walk as a workout. The remaining work is less about adding sophistication and more about *closing the loop with the human*: capture how the athlete feels, instruct the silent metrics, and keep the headline to the three questions that actually change today's decision.

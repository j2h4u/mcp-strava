# Sports-Medicine Review of the Training-Analytics Methodology

**Reviewer perspective:** sports medicine / exercise physiology, evidence-based.
**Scope:** physiological soundness of the training-load, readiness, and cardiac-monitoring methodology for a single male masters endurance athlete (50+), resting HR ~53 bpm, observed HRmax ~191. Mixed running / trail / hiking / walking, training at altitude ([REDACTED-LOCATION], hot continental summers).

This review judges *what* the system computes physiologically — load quantification, the impulse-response model, zones, cardiac drift, HR recovery, cardiac cost, safety flagging, and sport-specific handling — and *whether the methodology is defensible*. It is implementation-agnostic. Several recommendations from the prior (May 2026) review have since been adopted; those are credited below, and the remaining gaps re-prioritized.

---

## 1. Load Quantification (TRIMP)

**Method:** zone-based (Edwards-style) TRIMP — time in each HR zone multiplied by an integer zone coefficient, summed. Zones are Karvonen heart-rate-reserve (HRR) bands anchored to measured HRrest and observed HRmax. A discounted recovery band (coefficient ~0.5) now sits below Zone 1.

**Assessment — largely sound, with one structural caveat.**

- **Karvonen/HRR anchoring is correct.** Using %HRR rather than %HRmax for zone boundaries is the right choice for an athlete with a low resting HR; %HRmax zones would systematically misclassify low-intensity work (Karvonen et al., 1957; ACSM Guidelines, 11th ed., 2021). Anchoring HRmax to an *observed* maximum rather than a 220−age estimate is also correct — the population formula carries a SD of ~10–12 bpm and is unreliable for any individual (Tanaka et al., 2001, *JACC* 37:153).
- **The recovery-band discount is a genuine improvement.** Previously, easy daily walking at HR 90–110 entered the model at full weight, inflating chronic load with what is physiologically recovery. Splitting off a sub-Zone-1 recovery band and discounting it removes a real source of phantom fatigue. This was a prior recommendation and it has been adopted.
- **Remaining caveat — linear/arithmetic zone weighting understates high-intensity cost.** Edwards integer coefficients (1·2·3·4·5) grow linearly across zones, but the physiological and autonomic cost of time above the lactate/ventilatory threshold rises non-linearly: blood-lactate accumulation, sympathetic drive, and post-exercise parasympathetic reactivation impose disproportionate recovery demand at the top of the range (Banister & Calvert, 1980; Lucia et al., 1999, *Med Sci Sports Exerc* 31:1777). The exponentially weighted Banister TRIMP (Banister 1991) or Lucia's session-RPE-validated zone TRIMP would track top-end stress more faithfully. For a masters athlete — in whom recovery from high-intensity work is measurably slower — under-weighting Zone 4/5 is the *less safe* direction of error.

**Recommendation (priority: medium).** Keep the HRR zone structure. Consider a Banister exponential weighting (coefficient ∝ e^(b·%HRR), b≈1.67 for the male reference curve) or Lucia three-zone TRIMP so that threshold and supra-threshold minutes carry their true recovery cost. At minimum, retain explicit tracking of time-above-threshold (see §6).

---

## 2. Banister Impulse-Response Model (Fitness / Fatigue / Form)

**Method:** two exponentially weighted moving averages of daily load — a long time-constant ("fitness", τ≈42 d) and a short one ("fatigue", τ≈10 d) — with form = fitness − fatigue. A separate ACWR (acute:chronic ratio) is derived from short/long load windows.

**Assessment — methodologically standard and correctly parameterized for the athlete.**

- **τ_fitness ≈ 42 d / τ_fatigue ≈ 10 d is defensible.** The classical Banister constants (Busso et al., 1997; Banister 1991) are τ1≈45, τ2≈15 in the original two-component model; the 42/10 pairing is well within the empirically used range and the CTL=42 / ATL=7–10 convention is standard in applied practice. Raising the fatigue constant from a faster decay was a prior recommendation, and it has been adopted — appropriate, because masters athletes show 40–60% longer recovery kinetics after hard sessions (Borges et al., 2016, *Int J Sports Physiol Perform*). A τ_fatigue of 10–14 d is reasonable; the current 10 is at the conservative edge.
- **Known limitation — the model is linear in load.** Form treats every TRIMP unit as an additive, interchangeable fatigue increment. Real dose-response is non-linear above threshold and the single-fatigue-component model cannot represent the brief, deep "overreaching" fatigue that follows a single very hard session. This is an inherent property of the two-EWMA Banister formulation, not a defect of this implementation; it is worth stating explicitly so form is read as a *trend indicator*, not a precise readiness gauge.
- **Form-zone thresholds (tired/normal/fresh) are reasonable heuristics** and consistent with TSB-style interpretation, but they are population conventions, not individualized. Over months, the athlete's own form-vs-performance relationship should be used to recalibrate.

**Recommendation (priority: low–medium).** Keep the model. Document that form is directional. If a single objective fatigue marker is ever added to gate recommendations, prefer HR-recovery trend or resting-HR trend (§5, §7) over form alone.

---

## 3. ACWR and Progression

**Method:** acute:chronic workload ratio with a "danger" threshold; a sweet-spot band ~0.8–1.3.

**Assessment — the threshold has been correctly tightened for age.**

- The danger threshold has been lowered to ~1.35 (from a higher value). This is the right direction. Masters athletes show elevated injury and soft-tissue risk at lower ACWR than younger cohorts; the often-cited ~1.5 "danger" line derives from young team-sport data (Gabbett 2016, *Br J Sports Med* 50:273) and over-tolerates load spikes for a 51-year-old. A ceiling of 1.3–1.35 is appropriate.
- **ACWR methodology caveats apply.** The ACWR construct has been critiqued for mathematical coupling (the acute window is contained in the chronic) and sensitivity to the smoothing method (Lolli et al., 2019; Impellizzeri et al., 2020, *Int J Sports Physiol Perform*). EWMA-based ACWR (as used here) is the better of the available variants (Williams et al., 2017) but should still be read alongside absolute weekly load, not in isolation.
- **The ~10% progression rule and orthopaedic load are not directly enforced.** ACWR governs systemic load, but running impact load (2.5–3× body weight per footstrike) is best policed by week-over-week *running distance* progression — the classical ≤10% rule. A systemic ACWR in range can still hide a +25% jump in running km.

**Recommendation (priority: medium).** Add an explicit weekly running-distance progression guard (~10–15% cap) distinct from systemic ACWR. Keep the 1.35 ceiling. Continue to surface absolute weekly load beside the ratio.

**Recommendation (priority: medium-HIGH).** Ensure no load-recommendation logic creates a monotonic "more load is always better" gradient. A positive rest-day penalty now exists in the planning score, which addresses the prior critique; verify that mandatory rest and a periodic deload (−30–40% volume every 3–4 weeks) cannot be optimized away. Masters athletes adapt during recovery, not during accumulation; the system must be unable to recommend an unbroken load ramp.

---

## 4. HR Zones

**Method:** five Karvonen %HRR zones plus a discounted recovery band, fixed boundaries derived from HRrest and observed HRmax.

**Assessment — sound.** The boundaries (~64/72/80/88% of HRR style spacing) are physiologically conventional and individualized to the athlete's reserve. The only standing limitation is that zone anchors are static: HRrest in particular drifts with fitness, illness, heat, and overtraining. A static HRrest will slowly miscalibrate every zone if true resting HR moves. See §7.

---

## 5. HR Recovery (HRR after effort)

**Method:** detects stationary pauses within an activity and measures the rate of HR decline (bpm/min), reported as median/best/worst and tracked as a rolling median per sport.

**Assessment — physiologically the strongest fatigue/autonomic marker in the system, and it is now being trended (a prior recommendation adopted).**

- Post-exercise HR recovery reflects parasympathetic reactivation and is both a fitness and an autonomic-health marker; blunted recovery (<12 bpm in the first minute in the clinical setting) is independently associated with mortality (Cole et al., 1999, *NEJM* 341:1351). As a within-athlete trend, a *slowing* recovery rate is an early, sensitive sign of accumulated fatigue, illness, or overreaching.
- Computing it from in-activity pauses is pragmatic and valid for this athlete, though pause-derived HRR is noisier than a standardized post-exercise protocol (recovery depth depends on the intensity immediately preceding the pause). Reporting median across pauses and a rolling per-sport median is the right way to suppress that noise.

**Recommendation (priority: medium-HIGH).** Use the HR-recovery *trend* as a gate on progression/readiness, not merely as a displayed number. A sustained ≥15–20% slowing of the rolling median recovery rate is a strong physiological reason to withhold load increases regardless of what form/ACWR say. This is the single most defensible safety-and-readiness signal available here.

---

## 6. Cardiac Cost and Cardiac Drift

**Cardiac cost (CC):** mean HR ÷ mean speed (a HR-per-unit-velocity efficiency ratio), with an elevation-adjusted variant and per-sport rolling medians.

**Cardiac drift:** intra-activity — pace is clustered into bands (Jenks natural breaks), and early-vs-late median HR is compared *within* each pace band, weighted across bands. Severity is graded; only positive drift counts (negative early-to-late change is correctly treated as warm-up settling).

**Assessment — the cardiac-drift methodology is now genuinely good and resolves a prior blind spot.**

- **The within-pace-band, early-vs-late design is the correct way to measure cardiac drift.** Cardiac/HR drift is the upward creep of HR at constant work, driven by plasma-volume loss, rising core temperature, and cutaneous vasodilation for thermoregulation (Coyle & González-Alonso, 2001, *Exerc Sport Sci Rev* 29:88; Dawson et al., 2005). Naïve whole-activity decoupling fails for an athlete whose sessions mix running and walking (the pace change, not drift, dominates). Clustering by pace band and comparing like-with-like is exactly the right correction, and it makes the metric usable for this athlete where simple decoupling was "N/A." Restricting "significant" to positive drift with a consistency requirement is physiologically correct.
- **Per-sport thresholds are appropriate.** Drift tolerances calibrated per sport (running stricter, hiking looser because altitude/terrain inject HR variance, walking sensitive because of its low baseline) reflect real physiology. Hike drift is partly altitude-driven, not purely fatigue/heat, so a wider band is right.
- **Cardiac cost: useful as a within-sport longitudinal trend, but it is heat- and condition-sensitive.** CC is a reasonable surrogate for cardiovascular efficiency *within one sport over time*, and the elevation adjustment is a sensible first-order correction. Its main confound is unaddressed: ambient heat. In a hot continental summer, thermoregulatory drift alone raises HR 10–20 bpm at the same pace, inflating CC by 15–25% with no change in fitness. A rising CC trend in July could be read as deconditioning when it is simply heat.

**Recommendation (priority: medium).** Temperature-correct (or at least temperature-annotate) cardiac cost and any "efficiency declining" interpretation, using ambient temperature/humidity for the session. Without this, summer CC and drift trends will systematically misread heat strain as fatigue or fitness loss. Continue to treat CC strictly within-sport — cross-sport CC comparison is not physiologically meaningful.

*(Note on VO₂ estimation: the prior review flagged an age-unadjusted ACSM VO₂max extrapolation that over-estimated aerobic capacity by extrapolating a linear HR–VO₂ relationship past the ventilatory threshold. That estimation no longer appears in the methodology. If VO₂max is reintroduced, it must not extrapolate linearly to HRmax — the HR–VO₂ relationship plateaus/inflects above VT — and should carry an age term; a field-validated submaximal protocol is preferable.)*

---

## 7. Resting-HR Trend (gap)

The athlete profile carries a single static resting HR. There is no longitudinal resting-HR (or HRV) trend.

**Assessment — this is the most valuable *missing* readiness signal.** A morning resting-HR elevation of +5–7 bpm over baseline is one of the earliest, cheapest, and most validated indicators of incomplete recovery, infection onset, or cardiovascular strain (Buchheit 2014, *Front Physiol* 5:73; Plews et al., 2013). It is also the input that keeps Karvonen zones honest (§4).

**Recommendation (priority: medium-HIGH).** Track weekly resting HR (and HRV if available from the wearable). Use a sustained resting-HR rise to (a) recalibrate zone anchors and (b) gate load increases. Pairs naturally with the HR-recovery trend gate (§5).

---

## 8. Safety / Arrhythmia Flagging

**Method:** counts large beat-to-beat HR jumps (>30 bpm between adjacent samples) per activity as an anomaly count.

**Assessment — a reasonable, conservative sentinel; do not over-interpret it.**

- A >30 bpm inter-sample jump detector is a sensible cheap screen for both sensor artifact (optical/strap dropout) and genuine rhythm events. AFib prevalence is ~3–5% in the 50+ population and rises sharply with age and endurance-training history — lifelong endurance athletes carry a *higher* AFib risk than sedentary peers (Andersen et al., 2013, *Eur Heart J*; Calvo et al., 2016). So a flag is warranted for this athlete.
- **But it cannot diagnose anything**, and most positives will be motion/sensor artifact, not arrhythmia. Single-lead optical HR cannot distinguish ectopy from dropout. The flag's correct role is "review this stream," not "arrhythmia."

**Recommendations (priority — SAFETY):**
- **(HIGH) Add a Zone-5 dwell-time alert.** The system measures top-zone minutes but does not warn on prolonged accumulation. For a 51-year-old, sustained time above ~177 bpm (≈Z5) carries cardiac risk; an alert at, e.g., >5–8 cumulative Z5 minutes in a session is a cheap, high-value safeguard.
- **(HIGH) Add a high-load / heat compound alert.** Back-to-back long mountain efforts (e.g., two hikes totaling >800 TRIMP across a weekend, 10+ hours) in summer heat raise real risks: heat illness, rhabdomyolysis, and acute cardiac strain. Flag total load + ambient temperature jointly.
- **(MEDIUM) Surface persistent HR-anomaly clustering**, not just per-activity counts. A *rising trend* of anomalies across sessions — versus an isolated count — is what should prompt "consider a clinical ECG/Holter." Frame all such output as "seek medical evaluation," never as a diagnosis.

---

## 9. Sport-Specific Physiology

**Method:** sports are grouped (running vs. general training vs. HR-based), efficiency metrics are computed per sport, and drift thresholds vary by sport.

**Assessment — the per-sport separation is correct and has improved.**

- Treating efficiency, cardiac cost, and drift *within sport* is essential: HR-at-given-velocity is not comparable between running, hiking, and walking (different muscle mass, economy, gradient, and gait). The system does this correctly.
- Walking's role deserves a note. Easy daily walking is now discounted in load (recovery band, §1), which is physiologically right. But its low baseline makes it a sensitive drift sentinel — a useful property the per-sport drift threshold already exploits. Continue to treat walking as recovery for *load* purposes while still mining it for *autonomic* signal (drift, recovery, resting-HR context).
- Orthopaedic load is sport-specific and currently under-tracked relative to its risk weight for running (§3).

---

## Prioritized Summary

**Safety (act first):**
1. Zone-5 dwell-time alert (prolonged supra-threshold time for a 51-year-old). *(§8)*
2. Compound high-load + heat alert for long back-to-back mountain efforts. *(§8)*
3. HR-recovery-trend gate on progression — a ≥15–20% slowing should block load increases. *(§5)*

**Methodological accuracy:**
4. Temperature-correct/annotate cardiac cost and efficiency trends (heat masks fitness). *(§6)*
5. Add weekly resting-HR (and HRV) trend — recalibrates zones, gates load, earliest overtraining/illness signal. *(§7)*
6. Add a dedicated weekly running-distance progression guard (~10–15%) separate from systemic ACWR. *(§3)*
7. Consider Banister/Lucia exponential TRIMP weighting so threshold/supra-threshold minutes carry true recovery cost. *(§1)*

**Confirm guardrails / lower priority:**
8. Verify load-recommendation logic cannot optimize away mandatory rest or periodic deload. *(§3)*
9. Read form and ACWR as directional trends, not precise readiness gauges; recalibrate form zones from the athlete's own data over time. *(§2, §3)*

---

## What the Model Already Gets Right

- HRR/Karvonen zones anchored to measured HRrest and *observed* HRmax (not 220−age).
- Discounted recovery band so easy walking no longer inflates chronic load.
- Age-tightened ACWR ceiling (~1.35) and an age-appropriate fatigue time constant.
- A correctly designed intra-activity cardiac-drift metric (within-pace-band, early-vs-late, positive-only, per-sport thresholds) that fixes the old decoupling blind spot.
- HR-recovery now trended per sport — the strongest available autonomic marker.
- Strictly within-sport efficiency comparison.
- A conservative HR-anomaly sentinel appropriate to the athlete's elevated AFib risk.
- VO₂max linear-extrapolation estimate (previously over-optimistic for age) removed.

---

### Key References
- ACSM's Guidelines for Exercise Testing and Prescription, 11th ed., 2021.
- Banister EW. Modeling elite athletic performance. In: *Physiological Testing of Elite Athletes*, 1991.
- Banister EW, Calvert TW. Planning for future performance. *Med Sci Sports Exerc*, 1980.
- Borges NR et al. Aging and recovery. *Int J Sports Physiol Perform*, 2016.
- Buchheit M. Monitoring training status with HR measures. *Front Physiol*, 2014;5:73.
- Busso T et al. Modeling of adaptations to physical training. *J Appl Physiol*, 1997.
- Calvo N et al. Emerging risk factors for AFib in athletes. *Europace*, 2016.
- Cole CR et al. Heart-rate recovery and mortality. *NEJM*, 1999;341:1351.
- Coyle EF, González-Alonso J. Cardiovascular drift. *Exerc Sport Sci Rev*, 2001;29:88.
- Gabbett TJ. The training-injury prevention paradox. *Br J Sports Med*, 2016;50:273.
- Impellizzeri FM et al. ACWR: critique. *Int J Sports Physiol Perform*, 2020.
- Karvonen MJ et al. The effects of training on heart rate. *Ann Med Exp Biol Fenn*, 1957.
- Lolli L et al. Mathematical coupling of ACWR. *Br J Sports Med*, 2019.
- Lucia A et al. Heart-rate–based TRIMP in cyclists. *Med Sci Sports Exerc*, 1999;31:1777.
- Plews DJ et al. Training adaptation and HRV. *Sports Med*, 2013.
- Tanaka H et al. Age-predicted maximal heart rate revisited. *JACC*, 2001;37:153.
- Williams S et al. EWMA modeling of ACWR. *Br J Sports Med*, 2017.

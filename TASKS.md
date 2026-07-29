# Tasks

Working state of the pipeline rebuild started 2026-07-28, after milestones 1–6
all passed on synthetic data while the pipeline failed in the gym by two orders
of magnitude.

Related, and deliberately not duplicated here:

- `CLAUDE.md` — **Open problems** P1–P5, the *problems*. This file holds the
  *work*.
- `analysis/README.md` — the measurements and plots behind each finding.
- `src/README.md` — video ground truth (A2) in depth.

---

## Done

### B1 — stop applying the pause-derived gyro bias `17d5eee`
Applying `calibrate.gyro_bias` was worse than doing nothing on **13 of 13**
captures. Median per-rep horizontal residual **71.5 cm → 4.2 cm (17×)**, better
on 10/10, worse on none. The correction is now opt-in via `apply=True`.

We log `dm.rotationRate`, which Core Motion has already bias-corrected, and the
residual is smaller than the tremor we measure it in: ~7 °/s p-p at 6.5 Hz
against a 0.1–0.9 °/s bias, block-resampled SEM 0.16–0.36 °/s. A significance
gate was tried and rejected — it passed on 4/10 captures and made all 4 worse,
because SNR tests whether a mean is reproducible, not whether it is bias.

### A1 — rep segmentation `e8a8a0b` `efd5f5c`
**44/44 reps across all 10 captures, zero false positives**, against the old
stationarity segmenter's 0/14 bench and 1/15 squat. Shape matching in a
fixed-*duration* window, floor-impact anchors where the lift provides them
(6/6, 6/6, 3/3), and lateness as the tie-break. Every rep window now contains
both a concentric and an eccentric phase of comparable size (0/44 unbalanced,
was 9/15 deadlift reps holding only the pull).

Phase error later found by A2 and fixed — see below.

### A2 — video ground truth `374392b` `f6ff01c` `09c6bfc`
`src/truth.py`. Plate tracked from footage; first external truth for the
horizontal axis. Video landings match IMU floor impacts 6/6, 6/6, 3/3 at
**11–16 ms rms**, clock drift <0.25%. Deadlift is automatic and unattended;
squat warns; bench raises and needs a manual seed. Full detail and ten
drawbacks in `src/README.md`.

### #13 — rep-window phase, on deadlift
Windows ran lockout-to-lockout, half a rep out of phase. The cause was not a
bug in `segment.py`: band-passed IMU vertical correlates **-0.82** with video
truth, with 145 cm of in-band error against a 69 cm signal, already present at
the acceleration stage (-0.16). That is P3 — accel bias through a rotating
forearm sits at rep frequency, so no filter removes it. The segmenter was
finding real structure in the error, which is why the count was right and the
phase was wrong.

Where the bar sets down, boundaries now come from the impacts alone, which use
raw acceleration magnitude and match video to 13.5 ms. **All 15 deadlift
windows contain exactly one video lockout.** Bench and squat have no anchor,
still segment on the corrupted velocity, and their phase is unverified — that
needs B2 and B6, not a segmentation change.

### Acceleration sign inversion `3c2cbed`
**Core Motion's `userAcceleration` is the negative of physical acceleration.**
`io.load_log` negates it at the boundary; `synth.py` emits the device
convention so the CSV means the same thing whichever wrote it.

Invisible for months because at rest `userAcceleration` is zero — the gravity
check at the pause, `to_world` returning ~0 while still, and the synthetic
round trip are all evaluated exactly where the term vanishes. `synth.py` shared
the wrong convention with `orient.to_world`, so they agreed with each other and
disagreed with the watch.

Caught two ways: integrating world acceleration over 0.2-0.3 s windows
correlates **-0.76** with the video bar and **+0.76** negated (short window, so
it tests sign not drift); and the floor impact gave a negative velocity step on
all 9 impacts where a floor decelerating a falling bar demands positive. Both
are gates now. Segmentation needed cadence selection afterwards to stay at
44/44.

### A3 — real-data error metrics
`src/metrics.py`. The first measurement of error in this project. Absence of
this is why every stage could pass while the product failed.

`dispersion(reps)` needs no truth and measures rep-to-rep spread on the
normalised-time grid. `vs_truth(result, video)` measures against A2, deadlift
only, and raises on squat and bench rather than returning a number from footage
that is not truth.

**Horizontal, as the pipeline ships it: 5.1, 9.2 and 15.4 cm rms per rep**
against a 1 cm spec. **Vertical: 5.2, 6.8 and 4.9 cm rms** against ±2–3 cm.

Three findings that change the work, not just the record:

- **It is 5–15×, not two orders of magnitude.** The older figure came from
  whole-set excursion, which counts between-rep divergence that per-rep error
  does not. Excursion itself is now 3.4–35.9 cm across the ten captures; the
  "66–253 cm" in the A4 note below predates the acceleration sign fix.
- **Vertical is out of spec too.** "Vertical timing and structure come out
  fine" has been repeated since the first analysis and had never been measured
  per rep. It misses ±2–3 cm on all three deadlifts.
- **The per-rep detrend is not where P2 lives.** `vs_truth` reports the error
  with step 7's closure applied to the *video* as well: it moves the number by
  0.2–0.9 cm. B3 is still a real fix — the tracked bar misses closing by
  1.9–4.3 cm horizontally, which step 7 forces to zero — but it is worth a few
  centimetres, not the fifteen that matter. **This demotes B3 and promotes
  B6.** The error is upstream, in the acceleration reaching the integrator.

A fourth finding, unlooked for. `vs_truth` resolves the fore-aft sign **once
per set**, because that is what step 8 can do — resolving it per rep would let
a mirrored rep be corrected for free and flatter the metric. Doing it properly
then exposes that **4 of 6, 2 of 6 and 1 of 3 reps individually prefer the
opposite sign**. The horizontal reconstruction does not agree with itself about
which way forward is, within a single set. That is B4 evidence nobody had, and
it raises the question of whether a per-set axis is the right object at all.

`analysis/19` shows the shape: horizontal error is a single smooth arch across
each rep, peaking 0.5–0.7 through it. That is P3 seen directly rather than
inferred.

Two gates in `tests/test_real_data.py`: ceilings pinned at today's numbers so
they can only improve, and an `xfail` carrying the actual 1 cm spec so it is
executable and visible on every run.

**dispersion flatters a broken pipeline and the tests say so.** It reports
0.7–1.3 cm on bench and squat, inside spec, where nothing is verified at all —
because error that repeats every rep lands in the mean rep and cancels. Never
quote it alone.

### B5 — accelerometer saturation: there isn't any
**Nothing in `data/raw/` clips.** `deadlift_180x3` peaks at 21.78 g and used to
trip `check_log`'s 16 g threshold, which was an assumption about a sensor
nobody had checked. It is a genuine reading: every per-axis extreme is reached
by exactly one sample and none is a round number. A railed sensor repeats one
value across consecutive samples. `io.clipped_runs` now tests for that instead
of for magnitude, and `check_log`'s warning went with the threshold.

**The impact impulse survives 100 Hz too**, which was the follow-up question
and the more interesting one. A 20–30 ms impact is 2–3 samples and looks
unrecoverable, but measured against video the integrated velocity step comes
out at ratio 0.77–1.19 on both 155 kg captures, median **1.04** over all 15
impacts. See `analysis/20`.

**I got that wrong first and the plot caught it.** The first measurement said
16–27% of the impulse was lost, from two mistakes: predicting arrival velocity
as `sqrt(2gh)` when a touch-and-go deadlift is *lowered under control* and
arrives at ~2 m/s rather than 3.3; and measuring the step as a net change
across a window that spans the rise and the fall into the next descent. Both
are recorded in `io.py` and in the test, because they are easy to repeat.

**What is real: `deadlift_180x3` over-reads the impact step by 58–72%**, alone
among the three, and it is also the worst capture by horizontal error (15.4 cm
against 5.1 and 9.2). Heaviest bar, hardest landing. That is the first specific
hypothesis anyone has had for why that capture is an outlier, and it points at
strap ring — which is what #14's `strap_resonance` was written to detect and
currently detects backwards. Pinned per-capture in the gates rather than
averaged away.

Also killed on the way past: per-rep peak g does **not** predict per-rep error.
Correlation +0.17 across all 15 deadlift reps. A 3-rep pattern in `180x3`
suggested otherwise and did not survive the other 12.

### A4 — end-to-end driver `91ed978`
`src/pipeline.py` + `run.py`. The pipeline had never been executed end to end
against a gym capture; every prior real-data result came from scripts outside
the repo. Does not raise on unimplemented stages — records them as blocked and
returns what worked. Surfaced `io.check_log` and `segment.quality_flags`, both
previously dead code.

---

## To do

Ordered by what unblocks the most. **Re-ordered by A3's measurements:** B6 and
B2 are where the error actually is; B3 dropped because measurement showed it
worth 2–4 cm, not 15.

### B6 — attack the acceleration error itself  ← next
A3 puts the error upstream of the detrend and gives it a shape: a smooth arch
at rep frequency, 5–15 cm of horizontal per rep. The metric B6 was waiting on
now exists, so this is unblocked.

Order from the original entry still stands: per-rep zero-mean-acceleration
constraints first (they hold during motion and need no stillness), then the
two-anchor estimate C1 unlocks, then time-varying correction if those fail.
The cap also still stands — an oracle fitting constant gyro *and* accel bias
directly against the error recovers only ~30% of the residual, so nothing
constant-bias gets to 1 cm. Every attempt is now measurable against
`metrics.vs_truth`, which is the whole point of having built it.

### B7 — use the floor impact as a state anchor
New, and it follows directly from B5 proving the impact is measured correctly.

At the moment the bar is down and settled, its state is *known*: vertical
velocity zero, height at plate radius (22.5 cm to bar centre). The pipeline
currently spends that information on segmentation alone — `impact_anchors`
picks rep boundaries and nothing else uses it.

Using it as a ZUPT plus a position anchor would reset the integration once per
rep against a physical fact, rather than against step 7's assumption that the
bar returns to where it started. The "no closure" error is 199–322 cm on these
captures, which is what the per-rep detrend is currently papering over; an
anchor removes the cause rather than the symptom. It is also the one constraint
in this project that is externally true rather than inferred.

Deadlift only — bench and squat never set the bar down. Worth trying before
B6's solver, because it is simpler and it constrains the same quantity.

### #14 — fix `quality_flags` strap resonance
**Promoted by B5**, which found `deadlift_180x3` over-reading its impact
velocity step by 58–72% — the signature of the strap ringing on a hard landing,
which is exactly what this flag is supposed to catch and currently cannot.

Rejects 12 of 44 real reps, all on quieter lifts, and is backwards: it
thresholds the *fraction* of accel energy above 10 Hz, so a quiet rep fails for
having little signal at all. Rejected bench reps carry 13–18k absolute HF
energy against 0.9–2.9M in accepted deadlift reps — 50–200× **less**. Its own
docstring intends absolute energy.

### B2 — implement step 6, the wrist-to-bar offset
`correct.apply_offset` raises. `R(t)·d` varies by **8–13 cm horizontally on
every lift including deadlift**, contradicting the docstring's claim that
deadlift is exempt — now corrected there. That is the same size as A3's
measured 5–15 cm error, which makes it the largest single unmodelled term and
the best-understood one. Needs A2 to establish `d` against video rather than a
guess, and A3 now says whether it helped.

### B3 — rework the per-rep detrend
**Demoted by A3, from "P2 most likely lives here" to worth 2–4 cm.** Applying
step 7's closure to the video as well moves the error by 0.2–0.9 cm against a
5–15 cm total, so this is a correctness fix rather than the fix.

Still worth doing, and its premise is now measured rather than argued: the
tracked deadlift bar misses closing horizontally by **1.9–4.3 cm**, which step
7 forces to zero, so the constraint destroys that much real motion. Make the
closure axes explicit and keep vertical, where the bar genuinely does return.
`detrend_rep` also fits its line through two endpoint samples, making it
maximally noise-sensitive at exactly those indices.

### B4 — fix step 8
`project_to_plane` and `confidence` raise. `principal_axis` uses `np.linalg.eig`
on a symmetric matrix instead of `eigh`, and the docstring's sign resolution is
unimplemented — so the path can silently mirror, which the docstring itself
calls worse than no path.

A3 confirmed the mirror is not hypothetical — on `deadlift_155x6_2` the axis
came out backwards and had to be flipped against the video. It also found
something the planned fix does not address: **4 of 6, 2 of 6 and 1 of 3 reps
disagree with their own set's sign.** Resolving the sign from wrist attitude at
the pause gives one answer per set, which cannot be right for a set whose reps
point different ways. Whether that is a step-8 problem or just P2 showing
through is open — fix the acceleration first (B6) and re-measure before
designing around it.

### C1+C2 — watch logger protocol
Three-second stillness hold *after* the last rep — no capture has any
end-of-record stillness — giving a second gravity anchor over a ~40 s baseline
where accel-bias tilt error cancels in the difference. Log raw `CMGyroData`
alongside, which exposes Core Motion's internal bias estimate by difference.

### D — replace the remaining synthetic tests
Gates 5 and 6 are already deleted. Keep the algebraic-identity tests; replace
the rest with real-data gates. Largely done incidentally — worth a pass to
confirm nothing behavioural survives.

---

## Capture protocol

Not code, and the highest value per effort available:

- **Measure a plate.** `truth.PLATE_DIAMETER_M` is assumed at 450 mm and sets
  the video scale directly — a 2% error is 1.2 cm on a 60 cm ROM.
- **Step the camera back.** Squat clips the plate at lockout; bench sits the
  plate against clutter. Both become usable truth with no code.
- **Film a plumb line once**, to put a number on lens distortion — currently the
  largest unquantified error in A2.

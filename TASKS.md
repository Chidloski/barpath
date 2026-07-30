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
stationarity segmenter's 0/14 bench and 1/15 squat. *(True as measured. The
2026-07-30 session took it to **51/52** — see P1; `bench_spoto_90x5_1` counts
the re-rack as a sixth rep, and the variant token in its name had kept it out
of the gates entirely.)* Shape matching in a
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
against a 1 cm spec. **Vertical: 6.8, 8.7 and 3.2 cm rms** against ±2–3 cm.

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

### B7 — floor-impact anchor: REJECTED on measurement
Proposed after B5, on the reasoning that the bar's state at the floor is known
(velocity zero, same height every rep) and the pipeline spends that on
segmentation alone. Built, measured against a decision rule stated in advance,
and it lost. `analysis/22`.

| variant | horizontal, per capture | vertical |
|---|---|---|
| shipping | **5.1 / 9.2 / 15.4** | **6.8 / 8.7 / 3.2** |
| anchor + all-axis closure | 10.4 / 7.4 / 10.2 | 15.3 / 18.0 / 4.5 |
| anchor + vertical-only closure | 19.2 / 29.2 / 46.9 | 15.3 / 18.0 / 4.5 |
| vertical-only closure, no anchor | 495 / 522 / 337 | — |

**Why it failed, and it is not the detector.** The A3 error is a smooth arch
peaking mid-rep. An impact anchor acts only at the rep boundaries, where the
error is already ~0 by construction — a true constraint in the wrong place. The
third panel of `analysis/22` is the whole argument in one picture.

**What the ablation settled, which is worth more than the feature.** Row 4 says
the horizontal closure everyone (including me) has been calling false is doing
**metres** of load-bearing work: remove it with nothing in its place and error
goes to 3–5 m. It remains wrong — the bar really does miss closing by 1.9–4.3 cm
— but it is wrong and *essential*, so B3 cannot simply drop it. That reframes
B3 from "remove a false assumption" to "find something that can replace it".

**Kept:** `segment.rest_instants`, which is validated and gated against video
— 13 of 15 impacts within 0.05 m/s of true rest, against 0.4–1.0 m/s at
`impact_anchors`, which marks the spike ONSET rather than rest. The two it
rejects are the final impact of a set, where the lifter releases the bar; the
`max_accel` gate drops them rather than returning them wrong. B6 will want
this.

**A claimed win, since retracted.** This entry originally recorded that fitting
`detrend_rep`'s line through a 5-sample median took horizontal from 5.1/9.2/15.4
to 4.6/7.8/13.4. B2 found that was an artefact: the drift was measured between
the two medians, which sit at t[edge/2] rather than at the ends, then applied
across the full window — a 1.7% under-correction. The gain was that accidental
shrinkage, not the median. With the baseline fixed, `edge=5` gives 10.08 cm mean
against 10.01 at `edge=1`; the median is worth nothing and now defaults off.

**Reverted:** `correct.anchor` and the pipeline wiring, deleted rather than
left behind a flag.

### A4 — end-to-end driver `91ed978`
`src/pipeline.py` + `run.py`. The pipeline had never been executed end to end
against a gym capture; every prior real-data result came from scripts outside
the repo. Does not raise on unimplemented stages — records them as blocked and
returns what worked. Surfaced `io.check_log` and `segment.quality_flags`, both
previously dead code.

### C4 — measured plates and ROM bounds
Two tape measurements turned into gates. Plate diameters (425 notched / 445
bumper / 450 calibrated) replaced `truth.PLATE_DIAMETER_M`'s single assumed 450
and moved A3 by under 1%. Per-rep vertical ROM ceilings (bench 35, squat 76,
deadlift 61 cm) became `truth.VERTICAL_ROM_M`, applied by `pipeline.run` to the
reconstruction and by `metrics.vs_truth` to the video.

Four results, in descending order of how much they change what we believe:

1. **The video's vertical scale is wrong, per capture, by up to ±20%.** The
   referee for P2. Three deadlifts, one lifter: 59.1 / 66.8 / 47.6 cm. Diameter,
   radius quantisation and tracker drift all tested and ruled out.
2. **The reconstruction passes on all 17 captures** bar two known defects, and
   is more self-consistent on vertical ROM than the video judging it.
3. **Rep counting is 51/52, not 44/44** — `bench_spoto_90x5_1` counts the
   re-rack, hidden by a regex that did not match the variant token in its name.
4. **`squat_160x1` reconstructs 18.0 cm at a correct count of 1 of 1** — the
   first right-count-wrong-window failure any gate here has caught.

`analysis/23_rom_bounds.png`, `python run.py --rom`.

### #14 — the strap-resonance flag, REMOVED on measurement (2026-07-30)
It was promoted by B5 and again by B6, on the reasoning that the ringing after a
hard landing is strap compliance and this flag exists to catch it. It does not
catch it, and cannot.

**It rejected 33 of 73 real reps** — worse than the 12 of 44 recorded here, the
gap being captures added since. Rejection rate by lift: bench **26/30 (86.7%)**,
deadlift **6/15 (40.0%)**, squat **1/28 (3.6%)**. Hard landings happen on
deadlift and nowhere else, so the flag was ANTI-correlated with the phenomenon
it claimed to detect, firing hardest on the quietest lift.

**Neither formulation can work.** As a *fraction* of band energy it flags quiet
reps for having little signal at all — the bug recorded above. As *absolute*
energy, which its docstring intended, it separates by lift and nothing else:
squat 3e3–4e4, bench 6e3–1.4e5, deadlift 5.8e5–7.4e6. An absolute threshold is a
deadlift detector, because the floor impact is real broadband signal.

**And there is no resonance to find at 100 Hz.** The spectrum of the 400 ms
after each of the 15 floor impacts peaks at 10, 12.5, 15, 20, 22.5, 27.5, 30,
32.5, 35, 42.5 and 47.5 Hz — no repeatable frequency — with peak/median of
2.7–12.5, which is not narrowband. Nyquist is 50 Hz and a watch-on-strap
resonance is plausibly above it, so whatever exists aliases to an arbitrary bin.
You cannot detect what you cannot resolve.

The ringing B6 measured is still real and still where the deadlift's error
enters. But a broadband transient is not a detectable resonance, and discarding
the rep was never the right response — the fix belongs in the reconstruction.

`clipped` survives and now delegates to `io.clipped_runs`, a real rail test,
instead of thresholding against an assumed 16 g full scale that B5 disproved in
`io.check_log` a day earlier and that this copy outlived. Rejections are now
0 of 73, which is correct: nothing in `data/raw/` clips.

### C7 — the watch workout session, removed on measurement
`watch/`. The app held an `HKWorkoutSession` while recording, on the documented
belief that it was the only thing keeping Core Motion alive once the wrist drops.
That cost the owner their own workout — watchOS allows one primary session per
device, so logging ended whatever the Workout app was running.

The first fix kept the session and made this app *be* the workout: saved to
Health, live metrics, effort rating. It worked, and it imposed a workflow change
to solve a problem nobody had measured.

**Measured, 2026-07-30. The premise was false.** Two captures with no session:
47.08 s with zero gaps over 15 ms, and 58.78 s with **zero gaps at any
threshold** — including a 19.9 s and a 16.5 s span with the wrist still and the
screen dimmed, and a notification raised and dismissed mid-capture. 100.06 Hz
throughout, zero repeated rows, `check_log` clean.

So the session, the workflow change, the metrics screens and the effort rating
are all deleted, and the watch target no longer needs HealthKit or any
background mode. The sources now typecheck at watchOS 9.0.

*Untested, and the thing to check first if captures ever truncate:* the app being
genuinely REPLACED mid-capture — watch face or another app — for longer than the
~6.5 s the first test covered. Return to Clock will not fire inside a single set,
which is why this is judged safe. `watch/README.md` carries the full record.

*(Numbering note: the watch code called this C4, which collides with C4 above.
It is C7.)*

### C6 — the two anchors, measured
`calibrate.anchor_tilt`. The measurement C1 was built for, on the seven captures
that carry both holds. **A set does no lasting damage to Core Motion's
attitude**: tilt error bounds at 0.05° at the opening anchor and 0.14° at the
closing anchor, worst case 0.27°, across 39–56 s with 20 g impacts in it.
Gyro-only propagation over the same span drifts 0.35–1.49°, so the fusion is
working, not being corrupted.

*Two limits, both found by asking whether the watch is in the same posture at
both anchors. It is not — it rotates 3.5–161° between them, mostly yaw.*

- **These are upper bounds and the change between them means nothing.** The
  residual is tilt leak plus body-frame accel bias rotated into the world, and
  0.0025 g of accel bias is exactly g·sin(0.143°) — the closing-anchor median.
  True tilt is between zero and 0.14°.
- **Yaw is unobservable.** Gravity constrains roll and pitch only, and the
  logger uses `.xArbitraryZVertical`. Bounded indirectly at 0.0–1.4° per set,
  which is 2.4 mm on a 10 cm excursion — below spec, so the question closes
  anyway.

Four consequences:

1. **B1's default is confirmed on the evidence its docstring asked for.** The
   two-anchor baseline gives 0.014 °/s of effective drift against a pause
   estimate of 0.1–0.9. Ten to sixty times too large.
2. **P4's two-degree attitude error is retracted.** It converted a *vertical*
   residual with the *horizontal* leak formula — 0.035 g of vertical needs
   15.2°, not 2.0° — and the figure is pre-sign-fix and does not survive anyway
   (`bench_92.5x2` now reads 0.0005 g).
3. **C1 cannot see P3's error, by construction.** The anchors sample the
   attitude when it is most likely right: still, no linear acceleration. P3
   lives during the rep. What sees it is the per-rep mean, which must be zero.
4. **P3 has a location for the first time.** Bench and squat leave 0.003 g per
   rep, the sensor's own floor. Deadlift leaves 0.010–0.030 g, and ±100 ms
   around each impact — 6% of samples — carries three quarters of it.

Plus a defect nobody had recorded: deadlift vertical momentum does not close,
by −0.05 to −2.36 m/s per rep, negative on 15 of 15. Not a contradiction of B5,
whose 1.04 is a local step measurement; the deficit is in the rest of the rep,
and step 7 hides it.

`analysis/24_c6_two_anchors.png`, `python run.py --anchors`.

---

## To do

Ordered by what unblocks the most. **Re-ordered by A3's measurements:** B6 and
B2 are where the error actually is; B3 dropped because measurement showed it
worth 2–4 cm, not 15.

### C5 — fix the segmenter's two new failures  ← from C4
Both are xfailed with their evidence in `tests/test_real_data.py`
(`WRONG_REP_COUNT`, `KNOWN_ROM_FAILURES`), so they cannot be forgotten and a fix
announces itself.

- `bench_spoto_90x5_1`: the re-rack is counted as a sixth rep. Its 88.7 cm of
  vertical is 2.5× the bench bound, so ROM alone would reject it — but rejecting
  on ROM is a patch, not a diagnosis. Why does `_similar_cluster` accept it?
- `squat_160x1`: one rep, correctly counted, window spanning 18.0 cm of a ~65 cm
  squat. A single has no cadence for `_longest_cadence` to work with, which is
  the first thing to check.

### B6 — attack the acceleration error itself  ← next, and C6 aimed it
A3 puts the error upstream of the detrend and gives it a shape: a smooth arch
at rep frequency, 5–15 cm of horizontal per rep. The metric B6 was waiting on
now exists, so this is unblocked.

**C6 narrowed the target sharply, and removed two candidates.** Not attitude:
Core Motion holds 0.05° → 0.14° across a set. Not gyro bias: the two-anchor
baseline gives 0.014 °/s. Not sensor bias on bench or squat, whose per-rep
residual is 0.003 g — the table noise floor, i.e. nothing to remove. What is
left is deadlift's 0.010–0.030 g, three quarters of it injected in the ±100 ms
around each floor impact, plus a vertical momentum deficit of ~1.5 m/s per rep.
Start there; the other three doors are closed.

**The constant-bias family is now measured and rejected, 2026-07-30.** Three
variants against video, all worse than shipping (5.05 / 9.19 / 15.44 cm):

| variant | horizontal rms |
|---|---|
| zero-mean acceleration per rep | 19.63 / 27.14 / 6.55 |
| zero-mean, no position detrend | 136.07 / 94.80 / 34.64 |
| constant bias from rest-to-rest velocity closure | 15.50 / 11.64 / 29.12 |

The arithmetic rules out the family, not just these attempts. A constant bias
`b` leaves `b·T²/8` after a linear detrend. The measured error implies
0.0016–0.0047 g; every closure-derived estimate is 0.0076–0.0266 g, 1.9–7.1×
larger. If the signal really held 0.0266 g it would show 37.7 cm of vertical
error and it shows 5.24. So the constraint is absorbing a **localised** error
and spreading it as a constant, injecting a parabola bigger than what it
removes. That is why the oracle cap sits at ~30%: a constant cannot represent
an impulse.

*The measurement that shows it directly:* cumulative vertical velocity across a
validated rest-to-rest interval is smooth and physical through the pull and the
descent, then rings for several hundred ms at the floor impact and settles
0.4–1.5 m/s short of zero. See `analysis/25`.

**What is left, in order.**

1. **#14 first, not as a side quest.** The ringing after the impact is the watch
   moving when the bar has stopped — strap compliance. `quality_flags` already
   has a strap-resonance detector and it is broken (thresholds a fraction, means
   absolute). Fixing it is now on the critical path.
2. **Integrate across the impact, not through it.** The state on both sides is
   known and validated: `segment.rest_instants` lands where the video says
   |v| < 0.10 m/s. Splice rather than model.
3. Time-varying correction only if those fail.

Bench and squat need none of this — no impact, and a per-rep residual already at
the sensor's noise floor. Their problem, if they have one, is a different
problem, and nothing external measures it yet.

Every attempt is measurable against `metrics.vs_truth`, which is the whole point
of having built it. `analysis/25_b6_bias_models.png`, `python run.py --bias`.


### B2 — step 6 implemented; the term is 3× smaller than we thought
`correct.apply_offset` works and step 6 is no longer a blocked stage. It is
**off by default** because `d` is unmeasured, and B2's main finding is that it
cannot be measured from what we have.

**The 8–13 cm figure was wrong.** This entry and `pipeline.py` both claimed
`R(t)·d` varies by 8–13 cm horizontally on every lift, and called it the largest
unmodelled term in the system. Measured properly — within a rep, after step 7,
swept over every possible direction of `d` at |d| = 14 cm:

| lift | worst direction | typical |
|---|---|---|
| bench | 4.2 cm | 1.2 cm |
| squat | 4.4 cm | 1.3 cm |
| deadlift | 6.4 cm | 2.4 cm |

The rotation premise is fine — the watch turns 18–22° through a rep, so the ~16°
assumed in `correct.py` is right. Two things shrink it at the output: only the
arc component perpendicular to the rotation axis sweeps at all, and step 7 runs
afterwards and removes the linear part of what is left. Deadlift is the
*largest* of the three, which is the opposite of the old "deadlift is exempt".

**`d` is not identifiable from the video.** Fitting it against `vs_truth` is
ill-conditioned — joint optimum at |d| = 31 cm, per-capture fits at 21, 64 and
60 cm, against a real wrist-to-bar distance of 10–15 cm. Those are the optimiser
absorbing P3, which is also a body-frame constant swept by the same rotating
forearm and so nearly degenerate with `d`. Leave-one-out confirms it: one fold
returns |d| = 129 cm and makes the held-out capture worse, 5.1 → 16.2 cm.

**So `d` wants a tape measure**, watch centre to bar centre in watch axes, once.
Same class of thirty-second fix as measuring a plate. Expected payoff, from the
table above: ~1 cm on bench and squat, ~2 cm on deadlift.

### B3 — rework the per-rep detrend
**The endpoint-median fix was tried and is worth nothing.** `edge=5` gives
10.08 cm mean horizontal against 10.01 at `edge=1`. The reasoning behind it is
still sound — a line through two samples is maximally noise-sensitive at
exactly the indices it depends on — but on these captures it does not show, so
it defaults off with the measurement recorded next to it.

**A lead worth following, found by accident.** A buggy version of that change
under-corrected the drift line by 1.7%, and *that* improved horizontal by ~15%.
Sweeping the shrinkage deliberately: λ=0.99 gives 4.8/7.5/13.1 against
5.1/9.2/15.4 at λ=1. So **the closure over-corrects**, which is exactly what A3
predicted — the bar misses closing by 1.9–4.3 cm and step 7 forces that to
zero, so leaving ~1% of a ~2 m drift in puts back about the right amount.

Not usable as it stands: the optimum is sharp and inconsistent (capture 1 wants
0.99, capture 3 wants 0.97, λ=0.90 costs 39 cm), so a global λ is a fudge factor
tuned on the validation set. The principled version estimates the true
non-closure per rep and leaves that in — which needs a source for it other than
the video being validated against. That is the real B3.

**And harder than it looked.** The horizontal closure is false — the bar
misses closing by 1.9–4.3 cm — but B7's ablation showed it is also carrying
**metres**: drop it with nothing in its place and error goes to 3–5 m. So the
task is not "remove a false assumption", it is "find a constraint that can
replace it". The floor-impact anchor was the obvious candidate and it lost.

`axes` is now a parameter on `detrend_rep`/`detrend_set` so the next candidate
can be measured against the same numbers rather than re-deriving them.

### B4 — step 8 implemented; the SIGN is still open  (2026-07-30)
`project_to_plane` and `confidence` no longer raise, and `principal_axis` uses
`eigh` — the `eig` call on a symmetric matrix was why every caller wrapped the
result in `np.real`. All nine steps now run on all 17 captures.

`confidence` is derived rather than tuned: `min_ratio(n_reps)` inverts
Anderson's asymptotic angular error for a principal eigenvector to find the
eigenvalue ratio that pins the axis to 20 degrees. The one judgement in it —
effective sample size is the REP count, not the sample count — is stated as a
judgement and checked by a bootstrap in `tests/test_projection.py`, which is
written as a distribution statement because it does not hold on every capture.

It vouches for 9 of 17 sets, and it discriminates without having been tuned to:
it rejects both captures with a known segmentation defect
(`bench_spoto_90x5_1`'s 91.6 cm excursion, `squat_160x1`'s single rep) and the
two deadlifts with the worst measured error (35.9 and 30.0 cm excursion, 9.19
and 15.44 cm rms), while accepting `deadlift_155x6_1`, the best at 5.05 cm.

**Vouching for the axis is not vouching for the path**, and the code says so in
three places. An error at rep frequency (P3) lands in the covariance as variance
and makes the ratio look BETTER, so no function of ratio and excursion could
detect it. `analysis/27_bar_paths.png` labels every panel with what external
evidence exists for that lift.

**Still open — the sign.**

A3 confirmed the mirror is not hypothetical — on `deadlift_155x6_2` the axis
came out backwards and had to be flipped against the video. It also found
something the planned fix does not address: **4 of 6, 2 of 6 and 1 of 3 reps
disagree with their own set's sign.** Resolving the sign from wrist attitude at
the pause gives one answer per set, which cannot be right for a set whose reps
point different ways. Whether that is a step-8 problem or just P2 showing
through is open — fix the acceleration first (B6) and re-measure before
designing around it.

### C1 done, C2 abandoned, C3 added — watch logger
`watch/WatchApp/`. Typechecks clean against the watchOS 26.5 SDK.

**C1 and C3 are validated on lifts as of 2026-07-30.** Seven captures came off
the new logger — `squat_160x1`, `squat_140x4_1/2/3`, `bench_spoto_90x5_1/2/3` —
and every one carries a clean `phase` column: 4.2–4.8 s opening hold, the reps,
and a 3.0 s closing hold, exactly as designed. **The two-anchor measurement
C1 exists for has not been made.** The data is no longer the blocker; comparing
the attitude solution across phase 0 and phase 2 on those seven captures is the
next piece of work, and it is what answers P5's replacement question.

**C1 — closing stillness hold. Built.** "Finish Set" starts a 3 s countdown and
saves itself, driven off the device-motion callback rather than a Timer because
that callback keeps firing when the screen sleeps. Its *purpose* changed once P4
was re-measured: it is no longer about estimating gyro bias over a long
baseline, because there is barely any gyro bias. It is about answering whether a
SET perturbs Core Motion's attitude solution — two anchors bracketing 40 s of
lifting. That is now the live question.

**C2 — abandoned. `CMMotionManager.isGyroAvailable` is FALSE on watchOS.** Raw
gyro is not offered by the OS; tried on one motion manager and on two, and the
on-screen badge reported no hardware. There is no public-API route, so **P5 is
closed as permanently unobservable**. Two diagnostic captures carry the four
empty columns; `io.load_log` still reads them so those files load.

The loss is small, and P4's measurement is why: the residual *after* Core
Motion is 0.002 °/s, so its internal estimate has almost nothing to explain.

**C3 — a `phase` column. New, and the useful one.** `0` opening hold, `1` reps,
`2` closing hold. It tells the pipeline where the anchors are instead of making
`stillest_window` guess from quietness — which matters because the guess is
contaminated: the opening 3 s it searches is exactly when a finger is on the
Calibrate button. **The cleanest stillness in any capture is the tail of phase
2**, the only quiet window not followed by a screen tap. Using it is the first
thing to try on a capture that has a real closing anchor. `check_log` now
verifies the hold exactly where the column exists.

Also fixed: "Discard" used to write a CSV.

`synth.py` gained `settle_pause` so it models the protocol, not just the
sensors — otherwise every synthetic log trips the C1 warning.

**And it exposed a fake test.** `test_accel_bias_removal_meets_horizontal_spec`
asserted a 1 cm threshold on synthetic data and broke once the longer record
moved the noise draw. Across 12 seeds it spans 0.29–1.86 cm — it was **failing
on 5 of 12 and passing only because seed=0 landed at 0.39**. A threshold sitting
inside the generator's own spread constrains nothing; that is gates 5 and 6 in
miniature. Rewritten as a comparison — bias removal must beat no removal, 12/12.

### D — replace the remaining synthetic tests
Gates 5 and 6 are already deleted. Keep the algebraic-identity tests; replace
the rest with real-data gates. Largely done incidentally — worth a pass to
confirm nothing behavioural survives.

---

## Capture protocol

Not code, and the highest value per effort available:

- ~~**Measure a plate.**~~ **DONE 2026-07-30.** Black notched 425 mm, black
  bumper 445 mm, blue calibrated 450 mm. `truth.PLATE_DIAMETER_M` is now a
  per-lift table keyed on the largest plate in shot. It moved A3's numbers by
  under 1% — a useful negative result, since this was flagged for months as a
  scale risk and the real scale error is 20× larger and elsewhere.
- **Re-shoot with a vertical reference in frame** — a metre rule against the
  rack, in shot for the whole clip. **Now the highest-value item here.** The
  video's vertical scale is wrong by up to ±20% per capture (per-rep ROM 59.1 /
  66.8 / 47.6 cm against a 61 cm ceiling) and the plate cannot fix it, because
  it calibrates at the bottom of frame for travel reaching the top. The referee
  for P2 is mis-scaled and no amount of code repairs footage. See `analysis/23`.
- **Step the camera back.** Squat clips the plate at lockout; bench sits the
  plate against clutter. Both become usable truth with no code. Squat is worth
  more than it was: `squat_160x1` reconstructs 18.0 cm for a 160 kg single and
  there is nothing to check it against.
- **Film a plumb line once**, to put a number on lens distortion — the leading
  candidate for the scale error above.
- **Tape the lockout height.** Deadlift bar centre at lockout, once. It would
  turn `VERTICAL_ROM_M`'s deadlift ceiling from a bound into a measurement and
  let the video be calibrated against it rather than flagged by it.

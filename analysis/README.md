# analysis — real-data diagnostics (2026-07-26/27)

**This directory holds PNGs and this file. Nothing else** — owner's rule,
2026-08-25. Twenty-one measurement scripts, six JSON caches, six working notes
and a generated HTML page were deleted that day. Each entry below states what
was measured and what it cost, which is what a reader comes for; the code that
produced it is in `git show c29ec71:analysis/<name>.py` if a method ever needs
checking.

**The consequence, stated because it is real: a figure here is no longer
reproducible from the repo.** That was the trade — the scripts were one-off
measurements whose results are written down, and the numbers in this file are
the record. Anything that must stay RUNNABLE belongs in `src/`, which is where
`src/gallery.py` went rather than being deleted with the rest.


Graphs from running the current pipeline on the first real watch captures, plus
an off-pipeline reconstruction experiment. Generating scripts live in the
session scratchpad (not the repo). Data in `data/raw/`.

> **READ BEFORE QUOTING ANY NUMBER FROM FIGURES 01–47 (C33, 2026-08-06).**
> **Step 6 — the wrist lever `R(t)·d` — was OFF for the entire history of this
> directory and is now ON by default** (C31, `70b2a63`;
> `pipeline.run(wrist_offset="auto")`). Every figure numbered below 48 shows the
> reconstructed **watch** path, not the bar path the pipeline now produces, and
> every horizontal and vertical figure in them changes under `d`. Regenerating
> one without passing `wrist_offset=None` will not reproduce its caption. Figure
> 48 is the first that shows both arms. See `CLAUDE.md`, *Reading a number*.

## Room mimics (2026-07-26, no barbell)
- `01_room_captures_accel_vel_pos.png` — vertical accel / velocity / position for
  the room deadlift + squat. Reps present but buried in drift.
- `02_room_stationarity_diagnostic.png` — rolling accel/gyro variance vs the
  stationarity thresholds. Only the calibration hold is quiet.
- `03_room_relaxed_thresholds.png` — segmentation with relaxed thresholds:
  deadlift marginally recovers 3, squat does not.

## Loaded lifts (2026-07-27)
- `04_loaded_squats_roughvert_segmentation.png`,
  `05_loaded_benches_roughvert_segmentation.png` — rough vertical with detected
  ZUPTs (blue) and rep bounds (red). Squats: 1 rep, wrong place. Benches: 0.
- `06_loaded_squats_velocity_vs_truth.png`,
  `07_loaded_benches_velocity_vs_truth.png` — drift-removed vertical velocity per
  set with truth rep count vs pipeline count. Reps are clear velocity
  oscillations the segmenter misses.

## Paused bench (`bench_92.5x2`, 2 reps, 2-count chest pause)
- `08_paused_bench_overview.png` — velocity + position, poly-detrended.
- `09_paused_bench_zoom_raw.png` — 22–36 s, minimal processing; shows drift
  dominates locally.
- `10_paused_bench_highpass_reps.png` — high-pass isolates the reps; the two
  paused reps sit at ~27 s and ~32 s (peak → pause → trough).
- `11_paused_bench_residual_bias.png` — reconstructed vertical velocity doesn't
  return to 0 at the holds: ~−0.35 m/s² (−0.035 g) residual accel bias.
  **This is the 0.035 g that P4 later reinterpreted as a 2° attitude error, and
  C6 retracted. Two things to know before quoting it: it is VERTICAL, and
  vertical leaks g·(1−cos θ) not g·sin θ; and it predates the acceleration sign
  fix (`3c2cbed`), which this reconstruction is upstream of. Through the current
  pipeline the same capture reads 0.0005 g. See the C6 section.**
- `12_paused_bench_motion_energy.png` — under load the only quiet window is the
  pre-set pause; stationarity can't find the holds.
- `13_paused_bench_reconstruction.png` — off-pipeline best-effort recon: vertical
  velocity, vertical displacement, and side-on path (two reps coloured).
  Vertical timing/structure recovered; side-on is drift-dominated (~1 m fore-aft
  vs ~0.1–0.2 m real) and NOT trustworthy.

See the session memory notes `segmentation-real-data-anchors` and
`drift-residual-orientation-dependent` for the conclusions.

## Pipeline rebuild (2026-07-28)
- `14_b1_gyro_bias_harm.png` — B1. Applying `calibrate.gyro_bias` was worse than
  bias=0 on every capture. Median per-rep-scale horizontal residual 71.5 cm ->
  4.2 cm (17x), better on 10/10, worse on 0/10. The correction is now opt-in.
- `15_a1_rep_segmentation.png` — A1. Rep windows (green) and floor impacts (red
  dotted) on all 10 captures. 44/44 reps, zero false positives, against the old
  segmenter's 0/14 bench and 1/15 squat. Note the setup burst at 5-15 s in every
  capture is correctly rejected despite being LARGER than the reps.

Caveat on both: measured with the 2 s tiled-window proxy in
`tests/test_real_data.py`, which conflates real bar movement with error. It
ranks two pipelines reliably; the absolute centimetres are not error. Rep
BOUNDARY accuracy is likewise unvalidated — counts cannot confirm placement.
Both need the video ground truth (A2).
- `16_a1_rep_windows_inspection.png` — A1 rep windows for inspection, 3 captures
  per lift, start/end marked. Every rep now contains both a concentric and an
  eccentric phase of comparable size (0/44 unbalanced, was 9/15 deadlift reps
  holding only the pull). Reps 2..n are well placed; the FIRST rep of each set
  over-extends backwards because its own eccentric is under-measured — on
  squat_130x5 rep 1 the descent registers -12.8 cm against a +57.8 cm ascent, so
  the balance search runs back to the walkout. Not a filter artefact: the median
  eccentric/concentric ratio at the 0.12 Hz corner is 0.9-1.3 across captures.
  Unresolved, and left for A2.
- `17_a2_video_ground_truth.png` — A2. Plate tracked from video on all three
  deadlifts (red), against IMU floor impacts (orange) and A1 rep windows
  (green). Sync residual 11-16 ms rms, clock drift <0.25%. This is the first
  external truth for the horizontal axis in the project.

  **It immediately found a bug in A1.** The rep windows start at the video
  lockout peak every time (16.42 vs 16.23, 19.21 vs 19.23, 22.64 vs 22.33,
  25.91 vs 25.70, 29.48 vs 29.23, 34.60 vs 34.27 on deadlift_155x6_1), so each
  window runs lockout to lockout — the descent of one rep followed by the
  ascent of the next. Half a rep out of phase, i.e. what the pipeline calls the
  concentric is the eccentric. Owner predicted this from the plots before the
  video existed. Not yet fixed.

## A4 — the driver (2026-07-28)
`python run.py` runs every capture and prints what happened; `--plot` writes
per-run diagnostics (gitignored). Two things it made visible on its first run:

- **`quality_flags` rejects 12 of 44 reps for strap resonance, wrongly.**
  *(Later 33 of 73, and the flag was removed entirely on 2026-07-30 — see #14
  in TASKS.md. It fired hardest on bench, which has no floor impact at all.)* It
  thresholds the FRACTION of accel energy above 10 Hz, so a quiet rep fails for
  having little signal at all. The rejected bench reps carry 13-18k of absolute
  high-frequency energy against 0.9-2.9M in accepted deadlift reps — 50-200x
  LESS. Its own docstring intends absolute energy.
- **Horizontal excursion is 66-253 cm** where real is 10-20 cm, quantifying the
  drift problem through the actual pipeline rather than a proxy.
  **Superseded — this number predates the acceleration sign fix (`3c2cbed`),
  which changed segmentation and so changed the reps this is measured over. It
  is 3.4-35.9 cm now.** Excursion is also a whole-set quantity that counts
  between-rep divergence, so it overstates per-rep error; use `metrics.vs_truth`
  for error and read excursion as "how much fore-aft travel the pipeline
  claims" (18-36 cm on deadlift, where the video says 8.5-15 cm).

`io.check_log` and `segment.quality_flags` were both dead code before this —
written, sound, and called by nothing but a test.

## Rep-window phase (2026-07-28)
The A2 video showed A1's windows were half a rep out of phase. Root cause is
not segmentation: band-passed IMU vertical correlates **-0.82** with video bar
height, with **145 cm of in-band error against a 69 cm signal**, and the
correlation is already only -0.16 at the ACCELERATION stage. That is P3 —
body-frame accel bias through a rotating forearm lands at rep frequency, where
no filter can reach it. The segmenter was finding genuine structure in the
error signal, which is why 44/44 counts coexisted with wrong phase.

Deadlift boundaries now come from floor impacts alone (raw acceleration
magnitude, no attitude, no integration, matched to video at 13.5 ms rms). All
15 windows contain exactly one video lockout. Bench and squat still segment on
the corrupted velocity.

*Updated 2026-07-31 (C9): that is not the same as their phase being wrong.
Bench segments on the corrupted velocity and comes out IN PHASE anyway — 29 of
29 windows hold exactly one chest touch, once C10 admitted all seven captures.
Squat remains unverified. See the C9 and C10 sections.*

## The sign inversion (2026-07-29)
**Core Motion's `userAcceleration` is the negative of physical acceleration.**
`io.load_log` now negates it at the boundary.

Missed for months because at rest `userAcceleration` is zero, so its sign is
invisible — and every check that had been run was at the calibration pause, or
averaged over a whole pull, where the term vanishes or nets to zero. `synth.py`
encoded the same wrong convention and `orient.to_world` was built to match it,
so generator and pipeline agreed with each other and disagreed with the watch.
Exactly the failure a synthetic gate cannot see.

Caught two independent ways:
- integrating world acceleration over 0.2-0.3 s windows correlates **-0.76**
  with the video-tracked bar and **+0.76** negated. The short window is the
  point: bias contributes ~0.07 m/s there against true steps of 0.5-1.5 m/s,
  so it tests SIGN, not drift.
- the floor impact gave a **negative** velocity step on all 9 impacts across
  two captures, where a floor decelerating a falling bar demands positive.
  After the fix, 14 of 15 are positive.

Owner called this from the velocity plots — squat and bench begin with an
eccentric and deadlift with a concentric, and all three showed the opposite
sign. An earlier session had attributed it to bias instead; that was wrong,
and the tests it rested on could not have distinguished the two.
- `18_a1_rep_windows_corrected.png` — rep windows after the sign fix, same
  layout as `16`. The physical structure is now visible directly: squat and
  bench reps begin with a NEGATIVE velocity lobe (the descent) and deadlift reps
  begin POSITIVE (the pull), each closing on a floor impact. Under the old
  inverted sign every one of these was the wrong way round, which is what the
  owner spotted from plot 16. 44/44 on all ten captures.

## A3 — error, measured at last (2026-07-29)
- `19_a3_metrics.png` — `metrics.vs_truth` on all three deadlifts. Top row:
  reconstructed rep paths (grey) against the video (red), same axes, equal
  aspect. Middle row: horizontal error against the video across each rep, with
  the ±1 cm spec band. Bottom row: the three numbers side by side.

**Horizontal error as the pipeline ships it: 5.1, 9.2 and 15.4 cm rms per rep**
against a 1 cm spec. **Vertical: 6.8, 8.7 and 3.2 cm rms** against ±2–3 cm.

The middle row is the one to look at. The error is not noise and not a ramp —
it is a **single smooth arch across each rep, peaking 0.5–0.7 of the way
through**. That is P3 made visible: a body-frame accel bias projected through a
rotating forearm arrives at rep frequency, which is the one shape a per-rep
line cannot subtract and no filter can reach. It had been inferred from a
correlation before; here it is the plot.

Three things this changed:

- **The scale of the failure was overstated.** 5–15×, not two orders of
  magnitude. The older figure was whole-set excursion, which includes
  between-rep divergence that per-rep error does not.
- **Vertical is out of spec too**, on all three captures. "Vertical timing and
  structure come out fine" had been repeated since plot 13 and had never been
  measured per rep.
- **The per-rep detrend is not the problem.** Applying step 7's closure to the
  *video* as well moves the error by 0.2–0.9 cm. Its premise really is violated
  — the tracked bar misses closing horizontally by 1.9–4.3 cm — but fixing that
  buys a few centimetres out of fifteen. B3 demoted, B6 promoted.
- **The fore-aft direction is not stable within a set.** `vs_truth` picks one
  axis sign per set, as step 8 would, then counts reps preferring the other:
  **4 of 6, 2 of 6, 1 of 3**. Near a coin flip on the first. This is not a path
  with a scale error; rep to rep it disagrees with itself about which way is
  forward. New evidence for B4, and a reason to doubt that a per-set axis is
  the right object.

And the trap this metric is built to expose: **dispersion reports 0.7–1.3 cm on
bench and squat**, comfortably inside spec, where nothing whatsoever has been
verified. Error that repeats every rep lands in the mean rep and cancels out of
every deviation from it, so a pipeline dominated by P3 scores well on
rep-to-rep spread. On deadlift, where there is truth to check against,
dispersion says 4.3 cm and the video says 5.1 cm.

## The pipeline, stage by stage (2026-07-29)
- `21_pipeline_stages.png` — one column per lift, one row per stage, raw
  acceleration through to the bar path. Regenerate with `python run.py
  --stages`; it lives in `plot.plot_stages` rather than a scratch script
  because B2/B3/B6 will all change what the middle rows look like.

Read top to bottom. Four things it makes obvious that no table does:

- **Row 0 — nothing is "up" yet.** The watch's axes are glued to the case and
  tumble with the wrist, so all three body-frame traces look alike. The blue
  band is the pre-set calibration hold, where every bias estimate is made.
- **Row 2 — reps are unmistakable in velocity**, on all three lifts, which is
  why A1's segmenter works at 44/44. The deadlift's trace sliding to −6 m/s
  across the set is the drift, in plain view.
- **Row 3 — the runaway.** Two integrations turn a ~0.02 m/s² bias into 4.6 m
  of position on the squat, 1.5 m on the bench and **57.7 m** on the deadlift,
  against a lift that travels 0.6 m. The video truth is on the deadlift panel
  and looks like a flat line because the reconstruction is 82× its size.
- **Rows 4–5 — what step 7 buys back.** After the per-rep detrend the reps are
  recognisable lifts again. That is the detrend doing real work, and it is also
  why the pipeline looked fine for months: this row is convincing and the
  horizontal error is still 5× the spec.

## The watch logger, second pass (2026-07-30)
C1 (closing hold) and C3 (`phase` column) are built and typecheck clean; neither
is validated on a lift yet. **C2 is abandoned: `isGyroAvailable` is false on
watchOS**, so raw gyro cannot be logged at all and P5 is closed as permanently
unobservable. Two diagnostic captures carry its four empty columns.

## The stationary table captures (2026-07-30)
`stationary_table_20260730_000757.csv` and `stable_2_20260730_003335.csv` — a
watch on a table, recorded to verify the new logger. C2 failed on both, and they
turned out to be the most informative captures in the project anyway: the first
measurement of the sensor's own noise floor with no wrist involved, and it
**replicates across the two**.

Quiet window 6–16 s, away from the button presses at each end:

| quantity | on a table | on a wrist, calibration pause |
|---|---|---|
| gyro \|mean\| | **0.002 / 0.001 °/s** | 0.93–1.05 °/s |
| gyro p-p | 0.18 °/s | 4.2–6.0 °/s |
| block SEM | 0.0012–0.0015 °/s | 0.07–0.32 °/s |
| \|mean\|/SEM | 1.80 / 0.57 | — |
| body-frame accel bias | **0.0025 / 0.0029 g** | 0.003 g per rep, bench/squat (C6) |
| attitude drift | 0.018° / 0.071° per 8 s | — |

**Two conclusions, and they reframe P3, P4 and P5.**

The residual gyro bias is ~500× smaller than the on-wrist figure this project
has been treating as bias. It is not resolvable above its own noise. So the
0.1–0.9 °/s in P4 is the lifter's own rotation, and B1's "never apply it" is
right for a stronger reason than B1 recorded.

~~The 0.035 g on-wrist "accel bias" equals g·sin(2.0°). It is the size of a **two
degree attitude error**, not of an accelerometer bias measured at 0.0025 g. That
points the dominant error at attitude, which no constant-bias estimator can fix
— consistent with B6's oracle recovering only ~30%.~~

**RETRACTED by C6 the same day.** Two independent errors. The 0.035 g is the
*vertical* residual from `analysis/11`, and vertical leaks g·(1−cos θ), not
g·sin θ — so it implies 15.2°, not 2.0°. And it is a pre-sign-fix off-pipeline
number that does not survive: `bench_92.5x2`, the capture it came from, now
reads 0.0005 g. Core Motion's attitude measured directly at the holds is 0.05°
and 0.14°. See the C6 section below.

**A near miss worth recording.** `calibrate.stillest_window` searches the first
3 s, which is exactly when a finger is on the Calibrate button. It picked
1.55–2.54 s here, with 1.8× the motion of the genuinely quiet part, and the
resulting ~0.002 m/s² bias error produced **38 cm of horizontal drift over 19 s
on a watch that never moved** (0.48 m → 0.07 m with a clean window). On the real
deadlifts, though, it changes nothing: 5.1/9.2/15.4 → 5.1/9.1/15.1, because
step 7's per-rep detrend already absorbs exactly that quadratic. Left alone —
one capture improving is not evidence.

## B7 — the floor-impact anchor, rejected (2026-07-29)
- `22_b7_anchor_rejected.png` — the detector, the ablation, and the reason.

The idea: the bar's state at the floor is *known* (velocity zero, same height
every rep), so anchor the integration to it instead of to step 7's assumption
that the bar returns where it started. Built, measured against a decision rule
fixed in advance, and rejected.

| variant | horizontal, per capture (cm) |
|---|---|
| shipping | **5.1 / 9.2 / 15.4** |
| anchor + all-axis closure | 10.4 / 7.4 / 10.2 |
| anchor + vertical-only closure | 19.2 / 29.2 / 46.9 |
| vertical-only closure, no anchor | 495 / 522 / 337 |

**The detector is fine** (left panel). `rest_instants` puts 13 of 15 anchors
within 0.05 m/s of true rest, against 0.4–1.0 m/s at `impact_anchors` — which
marks the spike *onset*, not rest, a distinction worth 500 ms.

**The constraint is in the wrong place** (right panel). The A3 error is a
smooth arch peaking mid-rep; an impact anchor acts only at the rep boundaries,
where the error is already ~0 by construction. No amount of tuning fixes a
constraint that is true but does not reach the error.

**And the ablation found something worth more than the feature.** Row 4: the
horizontal closure that A3 called false is carrying **metres**. Remove it with
nothing in its place and error goes to 3–5 m. It is wrong *and* essential, so
B3 cannot simply drop it — the task is finding a replacement, not a deletion.

A win was claimed here and has been retracted. Fitting the detrend line through
a 5-sample median appeared to take horizontal from 5.1/9.2/15.4 to 4.6/7.8/13.4;
B2 found the gain came from a 1.7% scale error in how the drift baseline was
measured, not from the median. With the baseline fixed the median is worth
nothing. What the accident did reveal is that the closure OVER-corrects — a
deliberate 1% shrinkage gives 4.8/7.5/13.1 — which matches A3's 1.9-4.3 cm of
true non-closure. Sharp and inconsistent across captures, so not usable as a
global constant, but it is a lead for B3.

## B5 — no saturation, and a correction (2026-07-29)
- `20_b5_impact_impulse.png` — the floor impact examined four ways.

**The accelerometer does not clip.** `deadlift_180x3` peaks at 21.78 g and used
to trip a 16 g threshold that was an assumption about a sensor nobody had
checked. Bottom-right panel: the magnitude tail thins out smoothly and the peak
is hit by exactly one sample. A rail piles up at one value. `check_log` now
tests for an actual rail (`io.clipped_runs`) rather than for a large number.

**The impact impulse survives 100 Hz.** Top-left shows the whole event spanning
2–3 samples, which looks unrecoverable. It isn't: the IMU/video velocity-step
ratio is 0.77–1.19 on both 155 kg captures, median 1.04 over all 15 impacts.

**This corrects a wrong result recorded earlier in the same session.** The
first measurement claimed 16–27% of the impulse was lost, from two mistakes:
predicting arrival velocity as `sqrt(2gh)` — a touch-and-go deadlift is lowered
under control and arrives at ~2 m/s, not 3.3 — and measuring the step as a net
change across a window spanning the rise *and* the fall into the next descent.
The top-right panel is what refuted it: the IMU tracks the video straight
through the impact. Drawing the thing settled in seconds what the table of
ratios had got confidently backwards.

**What is real: `deadlift_180x3` over-reads its impact step by 58–72%**, alone
among the three, and it is also the worst capture by horizontal error. Bottom
left: its impacts sit well above the agreement line while the other two scatter
around it. Heaviest bar, hardest landing, and the first specific hypothesis for
why that capture is an outlier — pointing at strap ring, i.e. #14.

Also checked and rejected: per-rep peak g does not predict per-rep error
(correlation +0.17 across all 15 deadlift reps).

## The ROM bounds — the reconstruction passes, the referee does not (2026-07-30)
- `23_rom_bounds.png` — per-rep vertical ROM against what the lifter can
  actually move a bar through. Regenerate with `python run.py --rom`.

Two things arrived on 2026-07-30: seven more captures, and tape measurements
that replaced two standing assumptions. Plate diameters are black notched
425 mm, black bumper 445 mm, blue calibrated 450 mm — so `PLATE_DIAMETER_M`,
assumed at 450 for everything, was wrong on bench and deadlift. And per-rep
vertical ROM has ceilings for this lifter: bench 35 cm (32 typical), squat 76,
deadlift 61.

**The plate diameters were not where the error was.** Correcting deadlift to
445 mm moves the A3 numbers by under 1% — horizontal 5.1/9.2/15.4 → 5.05/9.19/
15.44, vertical 5.2/6.8/4.9 → 5.24/6.60/5.24. Worth fixing, and a useful
negative result: the scale assumption this project has flagged as a risk since
`truth.py` was written is not what makes the reconstruction 5–15× out of spec.

**The reconstruction passes the bounds** (top row). Post-step-7 per-rep ROM is
bench 24–31 cm, squat 61–68, deadlift 53–61 — inside every band, and tight
within each capture. This was the first external check bench and squat had ever
had; every other gate in the project needed floor impacts or trackable video and
they had neither. It is weak, but it is not self-referential, and they clear it.

*(As of C8, 2026-07-31, that is no longer bench's only external check — bench
video tracks and syncs, so bench has a horizontal error measurement too. It
remains squat's only one. See the C8 section.)*

Where it is measured matters. Run the same check *before* step 7 and the
numbers are absurd — `deadlift_155x6_1` climbs from 100 cm on rep 1 to 1939 cm
on rep 6. The detrend is what makes vertical dimensionally sane at all, so this
result vouches for the output of step 7 and for nothing upstream of it.

**The video ground truth fails them** (bottom row). Per-rep video ROM on the
three deadlifts, same lifter, same lift:

| capture | video ROM | plate radius | pipeline h_rms |
|---|---|---|---|
| deadlift_155x6_1 | 59.1 cm | 64 px | 5.05 cm |
| deadlift_155x6_2 | **66.8 cm** | 64 px | 9.19 cm |
| deadlift_180x3 | **47.6 cm** | 56 px | 15.44 cm |

A 19 cm spread on a range of motion set by the lifter's own limbs. Three
explanations were tested and none survives:

- **Plate diameter.** Captures 1 and 2 found the *same* radius, so no diameter
  explains a 13% gap between them.
- **Radius quantisation.** `find_plate` searches a 4 px grid. Re-run at 1 px the
  radii are 64/65/54 and the ROMs 61.2/69.2/50.8 at 450 mm — under 2% of
  movement. Not it.
- **Tracker drift.** The floor baseline holds to 0.4 cm across every clip and
  the per-capture lockouts are internally consistent (61/60/60, 70/69/64,
  49/49/48). `deadlift_180x3` has the *best* median NCC, 0.94, and the worst ROM.

What is left is the geometry. The scale is calibrated on a plate sitting on the
floor and then applied to travel reaching the top of frame — which is exactly
the assumption `truth.py`'s docstring used to state outright ("pixels to metres
is one number, not a function of height in frame"). That claim is now marked
false in the module.

**Why this matters more than it looks.** `vs_truth` is the only external judge
of P2, and on one of its three captures it measures the bar moving through
66.8 cm of a 61 cm range. Its vertical numbers on that capture are measured
with a bad ruler. The horizontal and the sync are not implicated — sync still
matches the IMU to 11–16 ms, and fore-aft travel is a few centimetres, well
inside the frame region the plate calibrates — so P2's horizontal result stands.
But P2's *spread* across captures is partly this rather than the IMU, and the
error ranking tracks the ROM error exactly: the capture nearest a plausible ROM
scores best, the two flagged ones score 1.8× and 3× worse.

The fix is footage, not code: re-shoot with a known vertical reference in frame
— a metre rule against the rack — and calibrate the scale over the travel
rather than at the bottom of it.

**One-sided in practice.** `deadlift_180x3` reads 47.6 cm, about 20% low, and
is *not* flagged: the sanity floor is 40 cm and nothing measured justifies
raising it to 50. So a capture can still referee P2 with a scale 20% too small.
That capture is also the worst by horizontal error and the one that over-reads
its impact velocity step by 58–72% (B5). Three independent complaints about the
same capture, still undiagnosed.

**Three defects the bounds found in the pipeline, all in the new captures.**
Two were fixed by C5 on 2026-07-31 — see `28` below — and are kept here as the
record of what the bounds were able to catch.

- `bench_spoto_90x5_1` segmented a 5-rep set into **6** windows; the extra one
  ran 88.7 cm of vertical against a 35 cm bench bound, so it was the re-rack
  being counted, not a rep split in two. It had gone undetected because
  `REP_LABEL`/`REP_COUNT` did not match the `spoto` variant token — so
  `expected_reps` was `None` and *every* count gate silently skipped all three
  of the 2026-07-30 benches. P1's "44/44 with zero false positives" was true
  when measured, went to **71/72**, and is **72/72** since C5.
- `squat_160x1` reconstructed **18.0 cm** for a single at 160 kg, a quarter of
  the ~65 cm the other squat captures give. The count was right, 1 of 1 — this
  is the failure mode P1 warns about, a window in the right number and the
  wrong place, and it is the first time a gate here caught one. **It reads
  67.0 cm since C5.**
- `deadlift_180x3` rep 2 lands at 61.1 cm against the 61 cm bound. A 0.2%
  breach is inside the precision of the bound itself; it is reported and does
  not fail the gate, which allows 2 cm of slack. **This one is not fixed and
  was not touched by C5** — it is the same capture that is worst by horizontal
  error and over-reads its impact step, so treat a drift past ~63 cm as that
  capture degrading rather than as the bound being tight.

## C6 — the two anchors, and the error they cannot see (2026-07-30)
- `24_c6_two_anchors.png` — four panels. Regenerate with `python run.py --anchors`.

C1 built a closing stillness hold so that two anchors 40 s apart could measure
what a working set does to Core Motion's attitude. Seven captures now carry both
holds. This is that measurement.

**The physics, so the number means something.** During a still hold the
world-frame acceleration must be zero. Core Motion removed gravity using its own
attitude, so a tilt error θ leaves g·sin(θ) in the world horizontal — the same
relation `orient.py`'s docstring derives. The anchors therefore read the
attitude error directly, in degrees, at each end of the set.

**Answer: a set does no lasting damage** (top left).

| | opening hold | closing hold | gyro alone over the same span |
|---|---|---|---|
| median | **0.05°** | **0.14°** | **0.69°** |
| worst | 0.07° | 0.27° | 1.49° |

Over 39–56 s of loaded lifting with 20 g impacts in it. Propagating the logged
gyro alone from the opening anchor drifts 0.35–1.49°, so Core Motion's fusion is
doing real work and winning — through the impacts, not despite them.

**Two limits on how far that table can be read, both from the watch not being in
the same posture at the two anchors.** It rotates 3.5–161° between them, mostly
yaw:

*The tilt figures are upper bounds, and the change between them is not a
result.* The world residual is the tilt leak plus the body-frame accel bias
rotated into the world, so a posture change alters the bias term's contribution
at each end. And 0.0025 g of accel bias is g·sin(0.143°) — the closing-anchor
median itself. The body-frame residual is 0.0012–0.0050 g at both anchors, at
that floor throughout. True tilt error is between zero and 0.14° and nothing
here separates them. The conclusion is unaffected, since it is small either way;
an earlier version of this section read the 0.05 → 0.14 as degradation and that
was wrong.

*Only two of three degrees of freedom are measured.* Gravity constrains roll and
pitch. The logger requests `.xArbitraryZVertical`, so no absolute yaw reference
exists anywhere in the system and yaw error is unobservable. It is bounded
indirectly by the gyro-vs-Core-Motion yaw divergence, 0.0–1.4° per set. That is
enough to close it: 1.4° of frame rotation moves a point on a 10 cm excursion by
2.4 mm, under the 1 cm spec — and it is not the 180° disagreement P2 reports on
fore-aft sign, so yaw does not explain that either.

**This confirms B1 on the evidence B1 asked for.** `calibrate.py`'s docstring
named this exact test: two anchors 40 s apart, a baseline over which real
rotation cancels and bias does not. 0.69° over ~50 s is **0.014 °/s** of
effective drift, against a pause estimate of 0.1–0.9 °/s. The pause estimate is
10–60× too large, and "never apply it" now rests on a long-baseline measurement
rather than on an A/B comparison of two bad options.

**It also retracts P4's two-degree attitude error, twice over.** The 0.035 g
that inference rested on is the *vertical* residual from `analysis/11`. Vertical
leaks g·(1−cos θ) where horizontal leaks g·sin θ; converting a vertical number
with the horizontal formula is what produced "2 degrees". Correctly, 0.035 g of
vertical needs **15.2°**, and a real 2° tilt puts 0.0006 g into vertical — 58×
less. Separately, that figure is off-pipeline and pre-sign-fix, and does not
survive: `bench_92.5x2` now reads 0.0005 g. Both 15° and 2° are excluded by the
anchors by two orders of magnitude.

**And C1 cannot see P3's error, by construction.** The anchors sample the
attitude at the two moments it is most likely to be right: still, with no linear
acceleration to corrupt the gravity reference. P3 lives during the rep.

**What does see it** (top right). A rep starts and ends at rest, so its mean
world acceleration must be zero, and whatever remains is error in the same units
as the hold:

| lift | still hold | per rep |
|---|---|---|
| bench | 0.0011 g | **0.0034 g** |
| squat | 0.0009 g | **0.0025 g** |
| deadlift | — | **0.0270 g** |

Bench and squat sit at the 0.0025 g accel bias measured on a table. There is
nothing on those lifts to explain beyond the sensor itself, which is a stronger
statement than this project has been able to make about them before.

**Deadlift's error enters at the floor impact** (bottom left). Excluding ±100 ms
around each impact — **6% of the samples** — takes the per-rep residual from
0.015–0.031 g to 0.006–0.010 g. Three quarters of it is injected in a fifth of a
second per rep, at the moment the signal is largest and the gravity reference
most corrupted. The residual points the same way rep after rep (direction
coherence 0.60–0.88), which is P3's signature: error that repeats with the rep,
and which a rep-to-rep comparison preserves perfectly.

Note this is not an argument for discarding those samples. The impulse there is
real and B5 measured it against video at a ratio of 1.04.

**A new defect, on the axis assumed to be fine** (bottom right). Deadlift
windows run impact to impact and each contains exactly one impact, so the bar is
at rest on the floor at both ends and ∫a_z dt across a window must be zero. It
is **−0.05 to −2.36 m/s, negative on 15 of 15 reps**, median about −1.5. The
reconstruction loses ~1.5 m/s of upward impulse every rep.

B5's 1.04 is not contradicted: that is the velocity step measured locally across
the impact, over a few hundred milliseconds, and it is right. The deficit is
what the rest of the rep does. Step 7's detrend hides it entirely, which is why
vertical ROM comes out at a plausible 53–61 cm either way — and it is the
sharpest available statement of why the detrend is carrying vertical.

*Both numbers here have since been superseded, and the reasoning refined twice.*
The −0.05 to −2.36 range inherits its rep-window boundary placement; measured
between validated rest instants it is −0.37 to −1.48 on 8 of 9 (see the B6
section below). And "the deficit is what the rest of the rep does" is wrong —
**C11 localised it to the landing alone**, with the deadlift's own pulls closing
at 0.0008 g. The B5 reconciliation is also sharper than "local versus global":
B5's is an AMPLITUDE and the deficit is in the NET. See the C11 section.

## B6 — the constant-bias family is dead, and the error is an impulse (2026-07-30)
- `25_b6_bias_models.png` — three panels. Regenerate with `python run.py --bias`.

B6's stated first move was the per-rep zero-mean-acceleration constraint, and it
looked like the right one. A rep starts and ends at rest, so its mean world
acceleration must be zero — **velocity closure is physically true where step 7's
position closure is measurably false** (A3: the real deadlift bar misses closing
horizontally by 1.9–4.3 cm). Replacing a known-false assumption with a known-true
one is exactly what B3 was looking for.

**It makes things much worse** (left panel), horizontal rms against video:

| variant | deadlift_155x6_1 / _2 / 180x3 |
|---|---|
| shipping | **5.05 / 9.19 / 15.44** |
| zero-mean acceleration per rep | 19.63 / 27.14 / 6.55 |
| zero-mean, no position detrend | 136.07 / 94.80 / 34.64 |
| constant bias from rest-to-rest velocity closure | 15.50 / 11.64 / 29.12 |

A useful control first: per-rep re-integration from v=0 with the existing
detrend reproduces the shipping numbers to the digit. It has to — the two differ
by a linear-in-t term and the detrend removes exactly that — and it confirms the
comparison is measuring the constraint rather than the rebuild.

**Why, and it rules out the family rather than one attempt** (middle panel). A
constant bias `b` leaves `b·T²/8` of position error after a linear detrend
(residual `½b(t²−Tt)`, worst at `t = T/2`). Invert it against what was measured:

| capture | bias implied by the measured error | bias the closure estimates | ratio |
|---|---|---|---|
| deadlift_155x6_1 | 0.0037 g | 0.0266 g | 7.1× |
| deadlift_155x6_2 | 0.0047 g | 0.0089 g | 1.9× |
| deadlift_180x3 | 0.0016 g | 0.0076 g | 4.6× |

The signal does not contain a constant bias of the estimated size. If it did,
0.0266 g over a 3.4 s rep would leave **37.7 cm** of vertical error after the
detrend and the measured vertical is 5.24 cm. So the closure constraint is
absorbing an error that is **localised**, and representing it as a constant
spreads it over the whole rep — injecting a parabola larger than the error it
removes. That is also why TASKS.md's oracle cap holds at ~30%: a constant-bias
model cannot represent an impulse.

**Where the localised error is, shown directly** (right panel). Cumulative
vertical velocity through one rest-to-rest interval, on all three captures. The
bar is validated at rest at both ends (`segment.rest_instants`, |v| < 0.10 m/s
on video), so the trace must return to zero. It rises through the pull to
+0.8 m/s, falls through the descent to −1.2, and is smooth and physical
throughout — then at the floor impact it rings violently for several hundred
milliseconds and settles **0.4–1.5 m/s short of zero**.

The error is injected at the impact and in the ringing that follows it, not
distributed through the rep. The ringing is the signature to chase: the watch is
not rigidly coupled to the bar, so it keeps moving after the bar has stopped and
the accelerometer faithfully records motion the bar did not make. That pointed
at #14, strap resonance, which P6 already suspected for `deadlift_180x3` on
independent evidence — **but #14 was then measured and removed.** The
post-impact spectrum has no repeatable peak (10-47.5 Hz across the 15 impacts,
peak/median 2.7-12.5) and Nyquist here is 50 Hz, so a watch-on-strap resonance
aliases to an arbitrary bin. The ringing is real; it is not resolvable as a
resonance at this sample rate.

**One capture dissents, informatively.** `deadlift_180x3` is the only one the
zero-mean constraint helps, 15.4 → 6.6 cm. It is also the capture that over-reads
its impact velocity step by 58–72% (B5). A constraint that removes part of an
unusually large impact error helping exactly there is consistent with the
diagnosis, not against it.

**Correction to C6, from the same measurement.** C6 reported deadlift vertical
momentum closing at −0.05 to −2.36 m/s, negative on 15 of 15 reps, measured over
impact-to-impact rep windows. Those are the wrong windows: every rep boundary
sits **exactly 10 ms after its impact**, one sample into a 2–3 sample spike, so
part of one impulse falls outside the window and the figure inherits the boundary
placement. Measured between validated rest instants it is **−0.37 to −1.48 m/s,
negative on 8 of 9** intervals, with one +1.19. The defect is real and the
direction holds; the range overstated it.

**What B6 should do instead.** Not a constant, and not a per-rep constant. The
two live candidates are modelling the impact and its ringing directly (#14 was
tried as the way in and removed — the ring is not resolvable at 100 Hz, so this
has to work on the transient itself rather than on a detected resonance), and
integrating across the
impact using the known rest state on both sides instead of through it. Bench and
squat need neither — they have no impact, and their per-rep residual is already
at the sensor's noise floor.

*The second candidate was built on 2026-07-31 and rejected — see the B6 splice
section at the end of this file. It removed the vertical deficit completely and
still lost, and its failure applies to the first candidate too: any correction
localised in time injects `e·T/2` of position that step 7's LINEAR detrend
cannot remove. B3 has to come first.*

## Where the pipeline stands (2026-07-30)
- `21_pipeline_stages.png` — regenerated on the current pipeline. `run.py --stages`.
- `26_pipeline_scorecard.png` — how well it performs, per lift. `run.py --scorecard`.

Read the two together: 21 is how the pipeline works, 26 is how well.

**The scorecard's uncomfortable shape is the point.** Row 1 is the product —
what step 9 would draw. Squat and bench produce clean, tightly-overlaid,
entirely plausible bar paths. Deadlift produces a mess of rectangles that
nobody would mistake for a bar path.

That ordering is exactly backwards from the evidence. Deadlift is the lift with
the best external truth, and row 2 says what that truth says: **2–8 cm of
horizontal error per rep against a 1 cm spec, and 2–7 cm vertical against 3 cm.**
When 27 was drawn, bench and squat had no video truth at all — bench tracking
raised, squat tracked at ~0.40 median NCC — so their clean-looking output was
unfalsified, not verified, and row 1 labels them as such. "It looks plausible"
is precisely how this project would convince itself a broken pipeline works.

**C8 changed that for bench on 2026-07-31, and the panel labels are now wrong
for it.** Bench has a measured horizontal error of 2.63–3.67 cm on three of its
seven captures; the "NO external horizontal check" annotation still applies to
squat and to the four unsynced benches. Redraw 27 to pick up the change.

Row 3 is the one check that reaches all three lifts: per-rep vertical ROM
against `truth.VERTICAL_ROM_M`, every rep of every capture. When 27 was drawn,
two captures fell outside the bands — `bench_spoto_90x5_1`'s spurious sixth
window and `squat_160x1`'s 18 cm fragment. **C5 fixed both on 2026-07-31**, so
all 72 reps now sit inside the bands bar `deadlift_180x3` rep 2 at 61.1 cm,
which is inside the gate's 2 cm slack. Redraw 27 to see the current state.

**What 21 shows on the current pipeline.** Rows 3 and 4 are the drift: vertical
velocity ramps to −6 m/s on the deadlift and position spans **57.7 m** against a
0.6 m lift, so the video-truth line drawn beside it is visually flat. Row 5 is
what step 7 buys back — and on deadlift the per-rep curves disagree with each
other in the floor-resting portion, which is where B6 found the error enters.

## Step 8 and 9 finally run (2026-07-30)
- `27_bar_paths.png` — the product, every capture. `python run.py --paths`.

`project.project_to_plane` and `project.confidence` raised `NotImplementedError`
until now, so the pipeline had never completed and **every bar path anyone had
looked at was projected by hand inside the plot code**. Both figures that showed
one — `21_pipeline_stages` row 5 and `26_pipeline_scorecard` row 0 — did
`rep[:, :2] @ axis` themselves. Step 8 was the only stage whose output was on
screen while the stage had never executed.

`principal_axis` also called `np.linalg.eig` on a symmetric covariance instead
of `eigh`, which is why every caller wrapped the result in `np.real`. A
workaround that hid the wrong routine being called.

**`confidence` is derived, not tuned.** `min_ratio(n_reps)` inverts Anderson's
asymptotic angular error for a principal eigenvector to get the eigenvalue ratio
that pins the display axis to 20°: 10.1 at one rep, 3.8 at four, 3.0 at six. The
one judgement is that the effective sample size is the REP count rather than the
sample count — the samples in a rep are one smooth excursion at 100 Hz, not
independent draws. That is stated as a judgement and checked by a bootstrap in
`tests/test_projection.py`, written as a distribution statement because it does
not hold on every capture.

**It vouches for 11 of 17 sets** (9 when this was written, before C5).

**Half the evidence for "it discriminates without having been tuned to" has
since evaporated, and that is worth stating rather than quietly restating the
claim.** It used to reject both captures with an independently known
segmentation defect — `bench_spoto_90x5_1` at 91.6 cm excursion and
`squat_160x1` at one rep. C5 fixed both defects on 2026-07-31 and both now pass
comfortably: `bench_spoto_90x5_1`'s excursion falls 91.6 → **9.4 cm** at a ratio
of 20.2, and `squat_160x1` reaches a ratio of **69.7**. So confidence was
agreeing with the segmenter's failures, and when the segmenter stopped failing
it stopped objecting — which is consistent with it working, but is no longer
independent evidence that it does.

What survives intact is the half that was always the stronger one: it rejects
the two deadlifts with the worst measured error (35.9 and 30.0 cm excursion,
9.19 and 15.44 cm rms) and accepts `deadlift_155x6_1`, the best at 5.05 cm.
That comparison is against video, not against another part of this pipeline.

**And treat `squat_160x1`'s 69.7 as weak.** It is a single-rep PCA, where
`min_ratio(1)` is 10.1 — one smooth excursion has little to disagree with
itself about, so a high ratio there is close to structural. Passing on one rep
is not the same evidence as passing on six.

**Vouching for the axis is not vouching for the path.** An error at rep
frequency (P3) lands in the covariance as variance and makes the ratio look
*better*, so no function of ratio and excursion could detect it. Every panel of
27 is therefore labelled with what external evidence exists for that lift —
"NO external horizontal check" on bench and squat, the measured rms on deadlift
— and low-confidence sets are drawn without the 4× stretch, because stretching
noise is how you invent faults.

## C5 — both segmentation defects fixed, and neither by the same mechanism (2026-07-31)
- `28_c5_segmentation.png` — band-passed vertical velocity for the two
  defective captures, old windows above the axis and new below, each labelled
  with its centimetres of vertical.

Counting is **72/72** and every rep of all 17 captures is inside its ROM band
except `deadlift_180x3` rep 2 at 61.1 cm, which is inside the gate's slack and
is a different problem. Fifteen captures are unchanged rep for rep.

**The two defects looked alike and were not.** That was the first useful finding
and it is why no single criterion was allowed to fix both.

`squat_160x1`'s bad window was **1.26 s** against 2.8–3.1 s for every other
squat — anomalous in duration, at a correct count. `bench_spoto_90x5_1`'s two
spurious windows were **2.1 and 2.6 s** against real reps of 2.5–2.9 s, so
duration is blind to them and only their 45.7 and 88.7 cm of vertical gives them
away. Mirror images, and a criterion covering both would have been fitted to the
pair rather than derived from either.

**Bench: a cadence tolerance that was 8% too loose.** The five reps sit 2.78,
2.88, 2.86 and 2.94 s apart (ratio 1.058) and the first post-set movement
follows 4.50 s after the last, so admitting it needs 4.50/2.86 = **1.573**.
`_longest_cadence`'s tolerance was 1.6. That admitted the re-rack and grew a run
of six which beat the true run of five **on length alone**. The plot shows the
consequence the counts hid: the old run of six was *shifted*, missing the real
rep 1 at 26–29 s entirely. It was four real reps plus two spurious, not five
plus one.

*The margin, swept over all 17 captures and confirmed independently.* Every
value in **1.35–1.55** gives 17/17. Below 1.30 `squat_140x4_3` splits to 3 reps,
because its four reps genuinely vary 5.00/5.60/6.55 s (ratio **1.310**) — real
sets vary cadence by a third. At 1.60 the bench failure returns. 1.45 is the
middle: 11% clear of the worst real set, 8% clear of the failure. **This is a
plateau, not a wide one.** A rest-pause or cluster set would have a real mid-set
gap above 1.45 and would be split; no such capture exists in `data/raw/`.

**Squat: a tie-break resting on half an argument.** `_similar_cluster` ranks by
`(size, median_time)`, and the lateness rule encodes "set up first, lift
second". That correctly rejects everything *before* the reps and says nothing
about what follows them — and something always does. On a multi-rep set it never
bites, because size decides first. On a **single** there is no cluster to be
largest: every candidate is size 1, lateness decides alone, and the latest
movement in any capture is by construction the re-rack. Singletons now rank by
concentric displacement — an argmax, no threshold — and the capture reads
**67.0 cm**, separating 0.602 m against 0.384 for the runner-up.

**That rule is unfalsified on bench, not verified there.** It claims a working
rep moves the bar further than the movements bracketing it, and that is
measurably false on bench: `bench_92.5x2`'s unrack carries 0.433 m against 0.295
and 0.239 for its two real reps. Clustering saves every bench capture held
(winning cluster size 4+) and `squat_160x1` is the only one of 17 whose winning
cluster is size 1 — but **a bench single would enter this branch and pick the
unrack**, and duration does not rescue it (area×duration also prefers that
capture's setup, 0.302 against 0.280). A gate pins the containment so a future
capture entering the branch announces itself.

**`phase` cannot help either defect, and this was checked rather than assumed.**
The lifter re-racks *before* pressing "Finish Set", so both spurious windows sat
entirely inside `phase == 1` — `squat_160x1`'s re-rack ends at 38.3 s against
phase 1 running to 39.3 s. **The C3 column marks the closing hold, not the end
of lifting.** Both fixes are therefore phase-independent and apply equally to
the ten older captures.

**What this does not do.** It fixes how many windows there are and how far each
spans. It says nothing about **phase** — whether a bench or squat window starts
where the rep starts. A window half a rep out of step has the right count, the
right duration and the right amplitude.

*Written as "unverifiable until those lifts get an external anchor". Bench got
one within the day — C8's video sync — and C9 then ran the test: bench windows
are in phase, 15 of 15. See the C9 section. Squat's half stands, and squat is
now the only lift whose phase is unverified.*

## C8 — bench video truth (2026-07-31)

- `29_bench_video_truth.png` — three panels on why a bench clock sync can be
  believed. **Left:** the correlation run on the three deadlifts, plotted
  against the offset `truth.sync` already knows from landings matched to floor
  impacts. The peak sits +3, −14 and −18 ms from it — the method recovers a
  known answer, which is the whole licence for using it where there is no known
  answer. Note the peaks are only 0.774, 0.708 and **0.595** high. **Middle:**
  the same correlation on all seven bench captures. Three clear the floor,
  four do not, and the four that do not are genuinely flat-topped — there is no
  lag to read off them. **Right:** the gap the threshold lives in, 0.509 to
  0.595, with `SYNC_MIN_CORR = 0.55` at its midpoint and ~0.04 of margin either
  side. The dotted line is the 0.70 the function originally shipped with, which
  rejects `deadlift_180x3` — a sync correct to 18 ms.

**The rejected half, kept because it was convincing.** The intended independent
check was the re-rack: video sees the bar stop dead, IMU sees a transient. On
bench it disagreed with the correlation by 53–706 ms, which read as evidence
against the sync. Run on deadlift, where the offset is known, the anchor itself
misses by **+615, +660 and +510 ms** — a systematic half-second, because "last
tracked motion" and "last acceleration transient above 3 g" are not the same
event. The disagreement was almost entirely the check's own error.
`truth.rack_impact` was deleted; a comment marks where it was.

**What bench then measures.** Horizontal 3.67, 2.69 and 2.63 cm rms per rep,
against deadlift's 5.05/9.19/15.44. And `reps_disagreeing_on_sign` is 0 on all
fifteen bench reps, against 4 of 6, 2 of 6 and 1 of 3 on deadlift — the fore-aft
instability in `19_a3_metrics.png` does not reproduce on bench.

**Sensitivity, measured rather than argued.** Offsetting the fitted lag by
±100 ms moves per-rep horizontal rms by 0.11, 0.27 and 0.33 cm, and vertical by
0.83, 0.63 and 1.00 cm. So a sync error costs little horizontally and about a
centimetre vertically — and the lag was fitted on the vertical channel, so bench
vertical is the number to distrust.

**The weakest part, found by reading the middle panel rather than the numbers.**
The bench curves oscillate: their best rival more than 0.4 s from the peak
reaches **0.80, 0.81, 0.80** of it, against **0.74, 0.66, 0.51** on the three
deadlifts where the peak is known correct. Bench is outside the range the method
has been shown to work in. The cause is structural — the rival lags are −2.81,
+0.85 and −3.465 s against a rep cadence near 2.9 s, so the alternative
alignment pairs rep *n* with rep *n+1*, and touch-and-go reps genuinely do
resemble each other. `bench_spoto_90x5_2`'s peak at −2.32 s, which looks like an
outlier beside its siblings' +0.04 and −0.585, is this.

**And what that costs, which is the useful part.** Scoring at the rival lag
instead of the peak gives horizontal **3.11, 3.23 and 2.44 cm** against 3.67,
2.69 and 2.63 — no worse, and *lower* on two of three. The bench horizontal
number does not depend on resolving the ambiguity.

That is not a bench excuse. Shift a **deadlift** by a full 3 s and its
horizontal rms goes 5.05 → 4.62, 9.19 → 7.23, 15.44 → 15.17, while its vertical
explodes from 5.24 / 6.60 / 5.24 to **19.08 / 20.19 / 32.41**. So:
**`vs_truth`'s horizontal rms is not testing time alignment on any lift** — the
fore-aft signal is a few centimetres and looks much the same rep to rep, so
mis-pairing reps barely moves it. It is a magnitude comparison between two paths
that happen to be paired in time. Phase evidence comes from `17` and the
lockout-containment gate, not from this number.

## C9 — bench rep-window phase (2026-07-31)

- `30_bench_window_phase.png` — the question P1 called the one that matters,
  answered for bench. **Top row:** the tracked bar height on the IMU clock, with
  the IMU's own rep windows shaded. Every window contains exactly one chest
  touch (red), sitting past the middle. **Bottom:** where the touch falls in
  each window (blue) against the descent fraction measured in the video alone
  (green), with 0.0 and 1.0 marked — that is the half-a-rep-out failure mode,
  and it is where deadlift's old 44/44 segmenter actually sat.

**The result.** 15 of 15 windows, one touch each, phase 0.567–0.648. Bench
windows are in phase with the bar.

**Why 0.60 and not 0.50, checked rather than rationalised.** The obvious worry
is a systematic late bias in where the windows sit. So measure the same quantity
in the video with no IMU, no sync and no reconstruction: lockout to touch, over
lockout to lockout. It reads **0.573 / 0.590 / 0.582** against the IMU windows'
**0.593 / 0.613 / 0.619**. A bench descent is controlled and a press is not —
1.6–1.9 s down against 1.2–1.3 s up — and the segmenter is tracking that. The
two agree to 0.02–0.04 of a rep, which is 60–100 ms on a 2.8 s rep.

*Rep 1 of every set reads 0.69–0.73 and is excluded from the medians rather than
explained away: its "descent" starts at the unrack, so it includes the lift-off
and settle. That is a property of the video landmark, not of the rep.*

**This survives C8's weakest point instead of depending on it.** `bench_sync`'s
peak is only weakly isolated, its rivals one rep period away — but a
whole-rep-period error is invisible to a phase test **by construction**, since a
periodic set looks identical shifted by one rep. The ambiguity the sync cannot
resolve is exactly the one that cannot corrupt this measurement. A
fractional-period error *would* show, and does not: the three captures agree to
0.03 despite offsets of +0.040, −2.320 and −0.585 s.

**What it does not say.** It constrains where the window sits relative to the
bar, not whether the reconstructed path inside it is right — that is P2's
2.63–3.67 cm. And it says nothing about squat, which has no external anchor of
any kind and is now the only lift whose phase is unverified.

## C10 — the null model, and the threshold that was measuring the wrong thing (2026-07-31)

Started as "why do four of seven benches refuse the sync?" and found something
bigger on the way. No new figure; `29` is redrawn.

**The null model. Six of ten captures lose to a flat line.** `metrics.vs_truth`
now reports `null_h_rms` — the error you get by drawing NO fore-aft motion at
all — and `beats_null`, that over the pipeline's error:

| capture | pipeline | null | |
|---|---|---|---|
| `bench_90x4_2` | 0.64 cm | 3.08 | **4.80× better** |
| `bench_90x4_3` | 0.76 | 3.06 | **4.03× better** |
| `bench_92.5x2` | 2.75 | 3.13 | 1.14× |
| `bench_90x4_1` | 1.88 | 2.07 | 1.10× |
| `bench_spoto_90x5_3` | 2.63 | 2.42 | **0.92× worse** |
| `bench_spoto_90x5_2` | 2.69 | 2.16 | **0.80× worse** |
| `bench_spoto_90x5_1` | 3.67 | 2.63 | **0.72× worse** |
| `deadlift_155x6_1` | 5.05 | 3.55 | **0.70× worse** |
| `deadlift_155x6_2` | 9.19 | 3.23 | **0.35× worse** |
| `deadlift_180x3` | 15.44 | 1.96 | **0.13× worse** |

**All three deadlifts are worse than useless on the horizontal**, by up to 7.9×.
P2's "5–15× outside spec" measures against the spec; this measures against doing
nothing, and it is the harsher and more useful number. It is one line of
arithmetic and it had never been run.

**Two bench captures meet the 1 cm spec**, the first in the project — 0.64 and
0.76 cm. Tested for the obvious artefact, since a bar that barely moves is easy
to predict: those two have the *largest* video fore-aft travel of the seven
(5.41 and 5.61 cm) and beat the null by 4×. A flat-line artefact gives small
error on small travel; this is the opposite.

**Why four benches were being refused.** C8's `SYNC_MIN_CORR` was a peak-height
threshold, and peak height conflates agreement with what fraction of the record
contains lifting, since the correlation runs over the whole overlap. Bench clips
are 20–30% reps; deadlifts are 50–56%. The tell was that the correlations
ordered perfectly by rep count: 2 reps → 0.367, 4 → 0.496/0.498/0.509,
5 → 0.682/0.691/0.696. Restrict the correlation to the rep span and every bench
rises to 0.886–0.996 while deadlift moves only to 0.883–0.892 — the gap that
justified 0.55 disappears.

**Restricting is not the fix, and that is the part worth keeping.** The non-rep
time is what breaks the degeneracy. Restricted, bench sidelobes climb to
0.86–0.99 — `bench_90x4_1` reaches 0.985, a coin flip — because "align rep *n*
with rep *n*" stops being distinguishable from "align rep *n* with rep *n+1*".
Deadlift survives restriction (sidelobes 0.55–0.76) because it is genuinely
aperiodic. Dilution is the price of identification.

**The rule now accepts on the SHAPE of the curve.** Every rival above 0.70 of
the peak must sit within 0.15 of a whole rep period. Measured across all seven,
as offsets from the peak in each capture's own cadence:

    bench_90x4_1        2.13 s   0.80@-1.03P   0.78@+1.05P
    bench_90x4_2        2.46 s   0.80@+1.05P   0.73@-1.05P
    bench_90x4_3        2.31 s   0.75@-1.04P
    bench_92.5x2        4.55 s   0.80@+0.97P
    bench_spoto_90x5_1  2.96 s   0.81@-0.96P   0.76@+0.96P
    bench_spoto_90x5_2  3.23 s   0.81@+0.98P
    bench_spoto_90x5_3  2.76 s   0.80@-1.04P   0.78@+1.04P

**Eleven rivals, seven captures, every one within 5% of exactly one rep period.**
So the lag is identified modulo one rep and never worse, and both quantities
measured through it are invariant to a whole-rep shift. All seven sync.

**And C9's phase result got stronger by being extended.** All seven now: 29 of
29 windows hold exactly one chest touch. C9 had three captures all near 0.60,
which a constant bias would also produce; the four added here run 0.42–0.56, and
the video's own descent fraction tracks each one. `bench_92.5x2` is decisive —
its 2-count chest pause puts the touch at 0.431 by video and 0.424 by IMU.

## C11 — the vertical deficit is the landing, and only the landing (2026-07-31)

- `31_c11_momentum_closure.png` — three panels: every interval grouped, the
  duration control, and where the impulse goes. `python run.py --closure`.

The impact-free control the C6 deficit had needed since it was found. The
measurement is an identity rather than a comparison: between two instants where
the bar's velocity is zero, the integral of its vertical acceleration must be
zero. No model, no assumption about how lifting behaves, nothing tunable.

**It is also immune to the defect that flags half the vertical numbers in this
project.** The video's per-capture vertical scale can be 20% wrong and still
cannot move a zero crossing, so the video is used only to say *when* the bar was
still, never how far it went. A flagged capture's closure is quotable where its
ROM is not.

| intervals | n | median | worst |
|---|---|---|---|
| bench, real lifting | 44 | −0.013 m/s | 0.102 |
| deadlift, floor→lockout (the pull) | 8 | −0.010 m/s | 0.063 |
| deadlift, interval containing a landing | 9 | −0.589 m/s | −1.428 |

**The middle row is the result.** Those are 55–66 cm loaded pulls *from the same
captures as the failing row* — the dwell detector splits a deadlift rep at the
lockout, so the concentric and the descent-plus-landing are separate intervals
of the same thirty seconds of tape. Same lift, load, wrist, calibration. Only
the landing differs. That is a within-capture control, which the
bench-versus-deadlift comparison this was built to make is not; bench then
confirms it on a lift with no landing anywhere in it. As residual acceleration,
0.0019 g and 0.0008 g against 0.0300 g — the first two being the 0.0025 g
measured on a table.

**Two wrong readings on the way, both kept.** First "deadlift closes too, except
across an impact", which over-claimed until the middle group was shown to
contain lifting at all. Then "the bar is sitting on the floor", from a
max-|accel| of 0.6–1.1 g in those intervals. **A 155 kg pull leaves the wrist's
total acceleration barely above 1 g, indistinguishable from resting** — peak
acceleration cannot separate pulling from rest, and the video's bar travel can.

**Where it enters.** Split each failing interval at the impact. Before it the
reconstruction tracks the video's descent velocity to +0.14…+0.71 m/s — small,
and the *opposite* sign to the deficit. The error in the step across the impact
is −0.11…−1.54 and tracks the interval total. Injected at the landing, not
accumulated through the descent.

**B5 reconciled, not contradicted.** B5's 1.04 is min-to-max AMPLITUDE within
±0.3 s, and its docstring explicitly warns off net-change windows; this is the
NET, which is what the identity constrains. Same 15 impacts: amplitude 1.10,
net 0.41. The spike's size is captured and where the velocity settles
afterwards is not — B6's ringing, promoted from a described wobble to the whole
deficit. A fix must preserve the amplitude while correcting the settling point.

A fixed post-impact offset oscillates with the ring (0.72, 0.49, 0.76, 0.54 at
50, 100, 150, 200 ms), which is why B5 was right to refuse that window and why
the gate asserts the amplitude-to-net separation rather than either alone.

**What it closes.** The integrator, the attitude and the calibration are not the
problem on the vertical: 52 intervals of loaded lifting close at the sensor's
own noise floor.

## B6 — the impact splice, measured and rejected (2026-07-31)

- `32_b6_splice_rejected.png` — three panels: it works, it does not help, and
  it breaks a bound it was not aimed at. `python run.py --splice`.

The last item in B6's own plan, aimed by C11: the vertical deficit is injected
at the landing, the bar's velocity there is zero and externally validated, so
stop integrating *through* the impact and splice across it. Built, measured
against a rule fixed in advance, and rejected. The splice lives in `run.py` and
in the test that pins the result, deliberately not in `correct.py` — B7's
precedent is to delete rather than leave a flag.

**It does exactly what it was built to do.** Vertical momentum closure across a
landing goes from −0.778 / −0.522 / −0.339 to **−0.049 / −0.004 / −0.019 m/s**.

**And it loses on every variant tried:**

| splice | detrend | horizontal rms, cm |
|---|---|---|
| none | xyz | **5.05 / 9.19 / 15.44** ← shipping |
| z only | xyz | 5.05 / 9.19 / 15.44 ← bit-identical |
| xyz | xyz | 10.09 / 5.90 / 14.61 |
| xyz | z only | 28.51 / 18.00 / 61.36 |

**Row 2 is a fact about metrics, not about the splice, and it is worth
internalising.** `pipeline_h_rms` reads columns 0 and 1. A correction confined
to column 2 leaves it bit-identical to twelve decimal places. So **no
vertical-only fix can ever satisfy a horizontal decision rule** — which means
the rule set for this experiment was partly mis-specified, and the honest
reading is that the splice was never able to pass it.

**Row 4 is the real test and the real result.** It is the last live hypothesis:
that the splice should *replace* the horizontal detrend rather than stack on it,
since B7 showed the detrend is knowingly false. Splice all three axes, then
close vertical only. It gives 28.51 / 18.00 / 61.36 against shipping's
5.05 / 9.19 / 15.44 — 3–5× worse, though far better than the 495 / 522 / 337 of
closing vertical-only with nothing in its place.

**The reason generalises past this attempt.** The detrend constrains position
across a whole rep; the splice constrains velocity at one instant per rep. **A
sparse true constraint does not substitute for a dense false one.** That is
exactly B7's "a true constraint in the wrong place", arrived at from the
opposite direction and now measured on the vertical as well.

**The obstacle that changes the plan.** The splice breaks a bound it was never
aimed at: per-rep vertical ROM reaches **82.6 / 65.4 / 64.1 cm against a 61 cm
ceiling**. Removing an error `e` over a window `T` injects about `e·T/2` of
position — 15–23 cm here — and step 7's detrend is **linear**, so a quadratic
bump survives it. Panel 3 shows it directly. Every correction localised in time
inherits this, including the time-varying models B6 has left. **B6 is blocked on
B3**, and B3's value is no longer its own 2–4 cm but that it unblocks
everything after it.

## The reconstruction against the truth, drawn (2026-07-31)

- `33_reconstruction_vs_truth.png` — every capture with video, pipeline in
  colour over the video in grey. `python run.py --vstruth`.

The figure that says what the error NUMBERS mean. "0.64 cm rms" and "15.44 cm
rms" are abstractions until you see that one is a bar path with a wobble in it
and the other does not resemble the movement at all.

Read it alongside `27_bar_paths.png`, which draws the same reconstructions with
NO truth beside them — which is what a user would see. The pair is the argument
for why this project measures: several panels in 27 look entirely plausible and
are wrong by 5–15 cm.

**What it shows that a table does not.** On deadlift the video traces cluster
tightly while the pipeline draws 10–30 cm rectangles that wander fore-aft across
the set — the `beats_null` numbers of 0.70/0.35/0.13 made visible. On bench the
two families have broadly the same diagonal shape, and `bench_90x4_2` and `_3`
genuinely track. The fore-aft axis is LABELLED here, which `plot_paths` refuses
to do and is right to refuse: this panel shows the truth beside the claim, so a
reader can see how far the claim goes, where a product plot shows only the claim.

`metrics.vs_truth` now carries `curve_video` and `curve_pipeline` per rep so the
plot draws the real comparison rather than re-projecting by hand — the mistake
`plot.py`'s docstring records, where step 8 was on screen in two figures while
the stage had never executed.

## Capture inventory, corrected (2026-07-31)

`data/raw/` holds **17 rep-labelled captures totalling 72 reps** — bench 7/29,
deadlift 3/15, squat 7/28 — plus four diagnostic logs (two stationary, two drop
tests). All 72 segment correctly.

**This corrects a figure that had been wrong across six files.** The docs said
52 reps and "52/52" counting. The arithmetic: 10 captures held 44 reps, the
2026-07-30 session added 7 captures carrying 28 more, and 44 + 28 = 72. The
44/44 figures from before that session are correct and are left alone; every
post-session total was understated by 20 reps. Counting is **72/72** and the
pre-C5 state was **71/72**.

## C12 — the deadlift referee is lost at lockout (2026-07-31)

- `34_video_truth_lost_at_lockout.png` — NCC against bar height, where the bad
  frames sit in the path, and what correcting for them does to `beats_null`.

**Found by eye, from `analysis/33`.** The owner read the deadlift panels and
objected that the video truth traces a flat ~10 cm horizontal line at the top of
the pull, which is against the logic of a deadlift: at lockout the bar is held
against the thighs and is very nearly still. Nothing in the project had measured
whether the referee was right anywhere in particular — only on average.

**It is total, and stratified perfectly by height.**

| capture | median NCC | NCC over top 15% | top-10cm frames < 0.60 | bottom-10cm |
|---|---|---|---|---|
| deadlift_155x6_1 | 0.830 | **0.371** | 166/166 (100%) | 1/743 (0%) |
| deadlift_155x6_2 | 0.846 | **0.395** | 149/149 (100%) | 0/780 (0%) |
| deadlift_180x3 | 0.937 | **0.440** | 146/150 (97%) | 0/588 (0%) |

Bench is the control and holds up: top-of-travel NCC 0.563–0.850, and on the
three spoto captures it is HIGHER than the whole-clip median, because the paused
rep at the top is the best-tracked part of those clips.

**Why nothing caught it.** `truth.validate` checked the whole-clip MEDIAN
against `GOOD_SCORE`, and lockout is 8–15% of a clip, so all three passed at
0.83–0.94. The same failure shape as the milestones, as the ROM bound before C4,
and as C8's peak-height threshold: an aggregate that passes while the thing
fails exactly where it matters. `truth.top_of_travel_score` measures it now and
`validate` warns on it separately, because the two fail independently.

**What it costs, and it runs the opposite way to intuition.** The invented
fore-aft motion is part of the video's fore-aft signal, and `null_h_rms` is the
rms of exactly that signal — so the referee's failure INFLATED the yardstick
`beats_null` divides by, flattering the pipeline. Restricted to frames scoring
above `GOOD_SCORE` (56–67% of each rep):

| capture | h rms | null | beats_null |
|---|---|---|---|
| deadlift_155x6_1 | 5.05 → 4.00 | 3.55 → 2.36 | 0.70 → **0.59** |
| deadlift_155x6_2 | 9.19 → 9.76 | 3.23 → 2.03 | 0.35 → **0.21** |
| deadlift_180x3 | 15.44 → 16.91 | 1.96 → 1.18 | 0.13 → **0.07** |

Horizontal magnitude is roughly unchanged, so P2's 5–15× stands. The deadlift
`beats_null` figures do not — they are too generous by 15–45%.

**Not the template size.** First guess, and worth recording so it is not
repeated: `bar_path` only applies `template_half` for `SEEDS` (bench) captures,
so deadlifts use `track`'s default half=48 against plates of radius 64/64/56 px,
whose inscribed squares are 45/45/39. Shrinking the template raises NCC steadily
(0.37 → 0.69 at half=16) and makes the track WORSE: whole-clip ROM inflates from
60.5 to 74.1 cm against a 61 cm ceiling. A smaller template matches more things,
not the right thing. The fix is a wider shot, not code.

**And it probably explains the ±20% vertical scale error** that C4 could not
account for. Per-rep ROM is lowest-to-HIGHEST tracked point, so the highest
point is measured exactly where the tracker is least reliable. C4's surviving
guess — "the scale is calibrated on a plate resting on the floor and applied to
travel reaching the top of frame" — was right in location and now has a
mechanism. Not proven: testing it needs footage that tracks at lockout.

- `33_reconstruction_vs_truth.png` is where C12 was spotted. Regenerate it after
  any change to the tracker: the flat lines at the top of the deadlift panels
  are the failure, and they are visible without measuring anything.

## 35, 36 — the sticker tracker (C15, 2026-08-01)

`data_v2/` is a new capture set: five clips shot from a tripod with
retroreflective markers on the plate — three near the rim about a third of the
way round from each other, one on the bar's end cap. **No IMU data**; the
session did not produce any, so these are video-only and `data_v2/video_only/`
is named for it. `src/markers.py` tracked them — **the module was deleted on
2026-08-19 (H21), five days after `src/vtrack/` replaced it as the referee, so
every figure in this section is history and none of it can be re-rendered.**

`35_markers_detection.png` — what is detected and that it survives lockout.
Columns: the plate at its lowest and at lockout with the fitted constellation
drawn (green circle, green cross at the reported bar centre, orange square on
the end-cap marker, cyan dots every candidate `detect` returned); then vertical,
fore-aft, apparent size and fit residual against time.

Three things to read off it. **The constellation is held at lockout on all five
captures** — that is the whole point, and it is the failure `truth.py` cannot
avoid, because a black plate against a dark ceiling has no contrast and a bright
marker does not care what is behind it. **Apparent size is rigid to 1.028-1.059x
over a clip**, which is the check that the tracker is on a steel plate and not
wandering. And the **rep counts read straight off the vertical trace are 5, 5,
1, 6 and 1, matching all five labels** — an independent confirmation nobody
designed for.

`36_markers_vs_plate.png` — the same footage through both trackers.

| capture | stickers | plate template | old top-of-travel NCC |
|---|---|---|---|
| deadlift_150x5 | 54.0 cm | 54.5 cm | 0.35 |
| deadlift_160x5 | 57.1 cm | 58.6 cm | 0.27 |
| deadlift_190x1 | 52.3 cm | 47.9 cm | 0.45 |
| bench_85x6 | 29.7 cm | **0.2 cm, raises** | 0.95 |
| bench_110x1 | 23.8 cm | 33.3 cm | 0.38 |

**Row 3 is C12 reproduced on footage it was never measured on.** The old
tracker's NCC is plotted against the bar's height, and on every deadlift it
falls monotonically from ~0.85 at the floor to ~0.3 at lockout, crossing
`GOOD_SCORE` partway up. The failure is not a property of the three 2026-07-28
captures; it is a property of tracking a dark plate against a dark background,
and it recurs the moment you point the camera at another deadlift.

**`bench_85x6` is the other failure shape, and it is the worse one.** The old
tracker scores its *highest* median NCC there, 0.95, while reporting 0.2 cm of
travel over a 6-rep set — confidently tracking a motionless piece of gym. It is
the exact failure `truth.validate` was written for, and `validate` does catch
it; the point is that the score says nothing.

Deadlift whole-clip travel spans **4.8 cm** across the three sticker tracks
against **10.7 cm** through the plate template, on a range of motion fixed by
one lifter's limbs. That is the same disagreement `truth.VERTICAL_ROM_M` records
as the largest known error in that module, roughly halved — not eliminated, and
not yet measured per rep.

**What these plots do not show.** No sync, no `vs_truth`, no `beats_null`,
because there is no IMU capture to compare against. Nothing here says the
*pipeline* got better; it says the referee did.

## 37 — old versus new tracker, in one figure (C15, 2026-08-01)

`37_old_vs_new_tracker.png` — what `35` and `36` say, arranged so the comparison
is readable without reading the prose. Same five clips, same footage, both
referees.

Row 1 is bar height over each clip with the anatomical `VERTICAL_ROM_M` band
shaded. The two agree closely on the first two deadlifts and diverge exactly
where `36` predicts: `deadlift_190x1`'s lockout (47.9 against 52.3 cm),
`bench_85x6` where the plate template reports a flat 0.2 cm through six visible
reps, and `bench_110x1` where it emits square-wave jumps to 33.3 cm.

Row 2 is why, and the third panel is the one worth reading carefully.

**The plate template degrades with height and crosses its own threshold.**
Pooled over the three deadlifts, median NCC goes 0.86 at the floor to 0.33 at
lockout, correlation with height −0.706. **100%** of frames in the top 10 cm sit
below `GOOD_SCORE`, against 31% at the floor.

**The sticker tracker degrades with height too, and that is a correction to how
this was first drawn.** The panel was drafted captioned "no height dependence",
which the scatter falsifies: median fit residual runs 0.16 px at the floor to
0.81 px at lockout, correlation +0.54. Per capture the lockout medians are 0.78,
0.71 and **1.60** px — the last above the 1.5 px gate, though that gate is on the
whole-clip median (0.15 px there) and still passes.

*That last clause was a defect being written down rather than fixed, and C17
fixed it on 2026-08-02.* `markers.top_of_travel_residual` measured the fit
over the top `truth.TOP_FRAC` of travel and `tests/test_markers.py` gated on it.
*(Both moved on 2026-08-19 when `markers.py` was deleted: the function and its
threshold are `vtrack.top_of_travel_residual` and `vtrack.MAX_TOP_RESIDUAL_CM`,
unchanged, gated by `tests/test_vtrack.py`. `truth.TOP_FRAC` became
`capture.TOP_FRAC` and then `vtrack.path.TOP_FRAC`; the value never moved.)*
Measuring it across all five captures rather than the three deadlifts sharpened
the finding: **`deadlift_190x1` is the best capture held by the old statistic and
the worst by the new one** — 0.150 px whole-clip against 1.595 px at lockout,
a 10.6x spread, where the other four sit between 1.0x and 1.5x. It is also worth
converting before alarming anyone, which the pixel figures invite: through each
frame's own scale those lockout medians are 0.177 / 0.168 / **0.333** / 0.279 /
0.226 cm, so the worst is a third of the 1 cm spec. The gate is in centimetres
now, at half the spec, because that is the unit of the thing being refereed.

So the honest claim is not that stickers are immune to height. It is that they
degrade **within tolerance while never losing the bar**, where the template
degrades **past the point its own module says to stop believing it**. Coverage is
the difference that matters: 100% of frames tracked at every lockout, against a
template that is untrusted in all of them.

Left panel: deadlift travel across the three sets, which one lifter's limbs fix.
The plate template spans 10.7 cm and the stickers 4.8 cm, so whatever is left is
still referee error — halved, not removed.

**What this does not show**, as with `35` and `36`: no sync, no `vs_truth`, no
`beats_null`. There is no IMU capture beside this footage. The referee got
better; nothing here says the pipeline did.

---

## `38_b3_detrend_oracle.png` — B3: the detrend has headroom, and it is not in the order (C19, 2026-08-02)

`python run.py --b3oracle`. Three panels, because the result is a ceiling, a
rejection and a mechanism, and any one alone misrepresents it.

**Panel 1 is the finding worth keeping, and it is an ORACLE.** The best line and
the best line-plus-quadratic, fitted per rep *against the video being scored
on*. That is forbidden in the pipeline and is exactly the point: it bounds every
possible estimator rather than being one, the way B6's oracle capped
constant-bias correction at ~30% and saved building it. Step 7 subtracts one
particular line, so `err` minus the *best* line is a floor no linear detrend can
beat however cleverly it picks that line.

Median over the ten scoreable captures, per-rep horizontal rms: shipping
**2.72 cm**, best line **1.04**, best quadratic **0.33**, null **2.85**.

Two things follow, and the split by lift matters more than the median.

- **There is real headroom** — +1.67 cm, where this project has been describing
  B3 as worth 2–4 cm. The linear family alone holds ~10 cm on the worst capture:
  `deadlift_180x3` goes 15.44 → 4.89. Today's endpoint line is not the best line.
- **But it is a bench result, not a P2 fix.** On bench the best quadratic reaches
  0.25–0.55 cm, inside the 1 cm spec. On deadlift the best *line* is
  3.64 / 3.78 / 4.89 against nulls of 3.55 / 3.23 / 1.96 — **no per-rep line,
  however estimated, beats a flat vertical line on any deadlift** — and the best
  quadratic only just does. Note panel 1 is log-scaled; the deadlift bars are
  nowhere near the spec line and the gap is larger than it looks.

**Panel 2 is the buildable version, rejected.** `detrend_rep(order=2)` adds one
quadratic term pinned by a second closure the rep already supplies — a rep is
periodic in velocity as well as position, so the reconstructed `dv` is drift
exactly as `dp` is. No new anchor, no video, no threshold, and it degenerates to
today's line when `dv` is zero. Deadlift per-rep vertical travel goes to
78.2 / 68.4 / 116.4 cm against a 61 cm physical ceiling.

*Read the rejection carefully*: **vertical and ROM reject it on 3 of 3, and
horizontal does not.** `deadlift_180x3` improves fore-aft, 15.44 → 12.17. And
the median over all ten captures *improves*, 2.72 → 2.23, because bench has no
landing and barely moves — which is the aggregate-that-hides shape this project
keeps repeating, and the reason the decision rule was fixed per-rule and
committed before any number was read.

**Panel 3 is why.** One deadlift's reps, shipping against order=2. C11 localised
the velocity deficit to the landing and nowhere else, so a quadratic removes it
correctly *in total* by smearing it across the whole rep — `dv·T/8` at mid-rep,
~31 cm at `dv` = 1 m/s. The red traces dive to −100 cm on a lift whose bar
travels 60 cm upward.

**The durable conclusion.** B6 measured that a constant acceleration correction
cannot represent an impulse. This measures that a quadratic cannot either, so
the obstacle was never the detrend's *order* — any basis smooth across the whole
rep spreads a landing-localised error across the whole rep. Rule 3, the reason
B3 was promoted to first at all, fails directly: under an order=2 detrend the
splice breaks the ROM ceiling *harder* and loses more horizontally. **B6 is not
unblocked by B3**, and the two may be one problem.

**What this does not show.** The deadlift numbers are measured through a referee
C12 showed is lost at lockout, and restricting to well-tracked frames shrinks
the null further — so "no line beats the null on deadlift" is, if anything,
understated. Nothing here is evidence the reps line up in time: `vs_truth`'s
horizontal rms is insensitive to gross time misalignment.


## 39 — the marker seeder, and where it actually fails (C21, 2026-08-03)

`analysis/39_marker_seeding.png`. Six captures arrived with an IMU log beside a
marker clip — the pairing this project has been waiting for — and
`markers.bar_path` seeds on none of them. `bench_95x2` reports 0.4 cm of travel
against a 29.5 cm rep.

**Panel 1 — the failure is confident, not noisy.** The seeder's constellation at
frame 450 is not the plate, and it reports three markers matched at a sub-pixel
residual while being wrong. **The seeder's triple is one REAL sticker plus two
things that are not**, one of them outside the frame — which is why it can look
plausible to every check the module runs.

Each constellation is drawn as the circle through its own three markers. Two
earlier versions of this panel were wrong and the owner caught both: the first
used fixed-size markers, drawing the plate far smaller than it is; the second
used the tracker's `circumradius`, which is the MEAN distance from the
centroid, so the circle visibly missed the markers. On frame 450 the three
stickers sit at 89.8, 89.8 and 102.9 px from the centroid — that 13 px spread
is the error term in the module's equal-spacing assumption, made visible, and
it is what `calibration_report` reports as `spacing_bias`. A rigid triple of gym fixtures fits a rigid model
exactly, so no quality number the module computes can see this. Only the fact
that furniture does not MOVE distinguishes it, which is what `static_points`
now measures.

**Panel 2 — `track` is not what is broken, and this is the panel to read.** The
same tracker, the same clip, seeded by hand on the plate: 100% coverage, three
markers in 1229 of 1235 frames, median residual **0.11 px**. That is better than
it manages on any capture it was originally tuned against. The whole failure is
`seed_frame`'s choice of hypothesis. Note the red trace follows the bar's shape
about 60 px displaced before breaking up — the seeder is not tracking nothing,
it is tracking a constellation that is not the plate.

**Panel 3 — every gate was already at zero margin.** Three admission gates in
`candidates` each rejected the true constellation, and on the footage they were
tuned against each passed by a hair: the third sticker at rank 24 of a 30 cap,
the hub at 0.41 of a 0.45 gate, the triple 3rd against a top-5 cut. The new
captures crossed all three at once. This is the same shape as C12 and C17 — a
threshold that has never been stressed is not a threshold that is known to work.

**What this does not show, and what happened next.** The three gates were
necessary and not sufficient — after C21 the six captures still did not track.
The open defect was that `seed_frame` grouped hypotheses by circumradius alone
and then reselected the group's representative by appearance score. Shape
rigidity, trajectory smoothness and a 120-frame trial track were each measured
as replacements and none separated.

**C23 settled it by trial-tracking the shortlist over the WHOLE clip**, which
does separate: on `bench_95x2` the plate scores 0.87 against the best impostor's
0.24. All four benches now track. Both squats did not, and that turned out not
to be a seeding problem at all — the squat plate's stickers are at
94.9/111.4/153.7 degrees, so the centroid the whole method rests on sits 18.4%
of the radius off the plate centre. Those two captures were deleted on
2026-08-03. See TASKS.md C23.

**This figure depicts pre-C23 behaviour and cannot be regenerated from current
code** — the seeder it calls "shipped" now finds the plate, so re-running the
script would draw two identical constellations. It is kept as the record of the
diagnosis, which is what made the fix findable.


## 40 — the pipeline, the bar path, and the referee, in one figure (2026-08-03)

`analysis/40_overview.png`, `python run.py --overview`. Three captures, one per
column: a deadlift and a bench refereed by `truth.py`'s plate template, and a
`data_v2` bench refereed by `markers.py` — **the first capture in this project
scored by markers rather than a template.**

Six rows, and the split between them is the point. Rows 1-4 are the
reconstruction talking about itself: world-frame vertical acceleration, the
velocity where reps are obvious, the position that runs away to 57.7 m on a
deadlift and 10.2 m on a bench, and what step 7's detrend claws back. Row 5 is
the product, drawn under step 9's rules. **Row 6 is the only one where anything
outside the IMU gets a vote**, and reading it directly beneath the drift that
produced it is the reason to have one figure instead of three.

    column                       tracker    h rms     null    beats_null   sign
    deadlift 155x6  data/raw     plate      5.05 cm   3.55      0.70x       4/6
    bench 90x4      data/raw     plate      0.64 cm   3.08      4.80x       0/4
    bench 95x2      data_v2      markers    1.46 cm   4.33      2.96x       0/2

**What the three columns are for.** The deadlift is what P2 looks like: the
pipeline loses to a flat vertical line, and four of its six reps disagree with
each other about which way forward is. The two benches are the same lift under
the two referees — and the marker column is the better-founded one, since
`markers.py` tracks 100% of frames where the template loses the plate at the
top of travel.

**What it does not show.** `bench 90x4`'s 0.64 cm is the best number in the
project and it is one capture; the seven benches run 0.64 to 3.67 cm. Nothing
here is evidence the reps line up in time — `vs_truth`'s horizontal rms is
insensitive to gross time misalignment. And the marker column's scale rests on
`STICKER_RATIO`, transferred from the deadlift bumpers.


## 41 — per-rep video ROM on the four paired benches (2026-08-03)

`analysis/41_paired_bench_video_rom.png`, `python run.py --v2rom`. The same
quantity measured three ways on all four `data_v2` captures, and the gaps
between them are the finding.

  * **IMU** — the reconstruction after step 7.
  * **window** — the video's vertical range inside the IMU's rep window. This is
    what `metrics.vs_truth` reports, so it inherits the sync.
  * **own** — the video's own trough-to-shoulder range, from peak detection on
    the height trace with **no IMU input and no sync at all**. That is what lets
    it referee the other two, and it is the bar to read.

**It retracts C23's headline.** C23 compared whole-clip marker travel against
per-rep IMU ROM, got -1.6 / -1.8 / -1.6 / -6.1%, and called it the first
independent confirmation in the project. Those are not the same quantity: the
whole-clip range spans the un-rack, where the bar is held ~3 cm above lockout,
and that ~3 cm is about the size of the disagreement it was covering. Per rep
the video says **23.3-26.7 cm** where the reconstruction says **28.4-30.7** —
**~20% apart on all 14 reps**, not 1.6%.

**Unassigned, deliberately.** `markers.calibration_report` declares a spacing
bias of **7.3-11.2 cm** on these same four clips — the rim centroid sits 63-94
px off the detected plate centre and the plate turns 32-33° across the clip —
which is bigger than the ~5 cm in dispute. The marker path is not clean enough
to convict the reconstruction, and this figure does not try to. What it settles
is that the agreement was an artefact of the comparison.

**And it caught a one-rep sync error on two of four, which C25 then fixed
(2026-08-03).** A red window is one holding no video chest touch. As first
drawn, `bench_92.5x4_2` and `_3` had window 0 holding none while the video's
last rep fell outside every window. The figure now has no red window: all 14
hold exactly one touch, at 0.53-0.69 through. Touch minus window-centre per
rep, corrected:

    bench_95x2       +0.47 +0.57                 mean +0.52 s   (period 4.75)
    bench_92.5x4_1   +0.25 +0.09 +0.41 +0.19     mean +0.24 s   (period 2.83)
    bench_92.5x4_2   +0.47 +0.12 +0.11 +0.32     mean +0.26 s   (period 2.63)
    bench_92.5x4_3   +0.23 +0.32 +0.17 +0.53     mean +0.31 s   (period 2.68)

The bad two read +2.97 and +3.35 — 1.10 and 1.14 rep periods out, with ~0.3 s
of spread inside each capture. That rigid shift correctly told C24 the
segmenter was not at fault, and counting was and is 14 of 14. **Where C24 went
wrong was the next step:** it called this the whole-rep ambiguity
`metrics.bench_sync`'s docstring says it cannot resolve. The real cause was
`max_lag_s`, then 5.0 s, excluding both captures' true correlation peaks at
-6.37 and -7.08 s; given the whole curve those peaks beat the sidelobes the
sweep had settled for by 50% and 76%. Not an ambiguity — a truncated search.
See `metrics.bench_sync`'s search-window section for the 10.00-13.50 s plateau
and the boundary guard that now refuses rather than guesses. All four captures
now sit at +0.24 to +0.52 s, which is correct rather than small: C9 put the
chest touch at 0.567-0.648 through a window, not 0.5.

*One more check falls out of the redraw, and it is not the correlation curve
again.* `window` inherits the sync and `own` does not, so on a correct
alignment they should measure the same rep and agree. Per capture they now sit
at 24.8/24.1, 24.7/24.5, 25.4/25.0 and 26.2/25.7 cm — **0.2-0.7 cm apart**.
Before, window 0 on the two bad captures read 2.4 and 1.4 cm against ~24.

**The figure could not have assigned that itself, and no redraw of it can.** A
whole-rep sync error and a whole-rep segmentation error produce the identical
offsets table — C24 read this panel as the sync's inherent ambiguity, the owner
read it as the segmenter dropping the last rep, and the picture is the same
either way. What separates them is an anchor outside the periodicity: here the
correlation curve, once swept wide enough to contain its own peak.

**What it does not show.** Nothing about the horizontal, which is the axis the
spec is about — this is a vertical-extent figure. It cannot say which
instrument is right about the 20%; `own` and `IMU` never depended on the sync,
so the fix leaves the 20% exactly as it was. The `window` bars did depend on
it, and on the two mis-synced captures window 0 had been reporting 2.4 and
1.4 cm of a ~25 cm rep, having landed on the un-rack.

---

## 42 — the first 8-sticker footage: conic referee vs the reconstruction (C27, 2026-08-04)

`python run.py --dlconic` -> `analysis/42_conic_deadlift.png`.

**THE DRIVER IS GONE AS OF 2026-08-19 (H21) AND THIS FIGURE CANNOT BE
REGENERATED. THE FIGURE ITSELF STANDS.** `--dlconic` was the last caller of
`markers.bar_path` anywhere in the repo, so it was deleted with that module when
`src/vtrack/` became the only tracker that can run; `plot.plot_v2_deadlift_conic`
went with it. It was deliberately NOT repointed at `vtrack`: that would produce
a different measurement under an old figure's name, which is exactly the mistake
G5 named. Recover both with `git show 0e87f28:run.py` and
`git show 0e87f28:src/plot.py` if a marker-era figure ever has to be redrawn.

Three deadlifts,
`deadlift_160x6_1`, `_2` and `deadlift_185x3`, 15 reps. Everything is measured
through `layout="auto"` — the path a caller gets by default — because C27's
whole finding is that `auto` had been silently taking the wrong one.

**Row 1** puts both instruments' vertical on one clock; they lie on top of each
other. **Row 2** is per-rep vertical ROM. **Row 3 is the figure.** **Row 4** is
the referee's own health, and it is the one that licenses the rest.

*Read row 4 first, because C12 is the reason it is drawn.* Median markers
matched per decile of travel, floor to lockout, is the **full count in every
decile on all three captures** — 7/7, 8/8, 8/8. The plate template that P2's
older deadlift numbers were measured through is below `truth.GOOD_SCORE` in
166/166 top-of-travel frames, i.e. it fails exactly where the measurement is
taken. This referee does not, so row 3 can be believed in a way its predecessor
could not.

*Row 3 is the project's actual question and the answer is bad.* The video keeps
the bar inside 4.3-6.2 cm of fore-aft; the reconstruction sweeps **20-35 cm**.
`beats_null` is 0.23 / 0.34 / 0.14, so all three are **3-7x worse than drawing
no fore-aft motion at all**, against a ~1 cm spec on the axis the display
stretches 4x.

**These replace the old 0.70 / 0.35 / 0.13 rather than confirming them.** The
old figures were measured through a tracker inventing ~10 cm of fore-aft at
lockout, which goes into `null_h_rms` and therefore FLATTERED the pipeline. C12
already said the deadlift `beats_null` figures were too generous by 15-45%;
these are the first that mean what they say.

*What row 2 shows and what it cannot.* Per-rep video ROM is 51.4 / 51.9 /
51.5 cm — a **0.5 cm spread** — against 59.1 / 66.8 / 47.6 for the three
template-refereed deadlifts, a 19 cm spread on a range of motion fixed by the
lifter's own limbs. That is the "do not quote the spread" defect in P2, fixed by
the referee rather than by code. But the reconstruction reads 54.0-56.7, so the
two instruments differ by 4.6-9.3% and **row 2 cannot say which is right**: the
absolute scale still rests on `STICKER_RATIO = 0.858`, borrowed from a different
plate. A ratio of ~0.92 would close the gap exactly, which is physically
ordinary and must not be adopted by fitting it.

> **ANSWERED 2026-08-17 (H14), AND THE PREDICTION ABOVE WAS RIGHT.** The owner
> tape-measured the sticker geometry: a 2.0 cm sticker with its outer edge on
> the plate rim, so the sticker circle is the plate diameter less 2.0 cm.
> On deadlift that is a **+6.07%** correction — inside the 4.6-9.3% gap this
> paragraph measured from the other side, and arrived at without fitting
> anything. The equivalent ratio is 0.953 on a 425 plate rather than ~0.92,
> and the difference is that this ratio is not the same number on the 450 blue
> disc (0.956), because the inset is an absolute 1.0 cm. **Every metre figure
> on this page predates the correction.** See `analysis/67`. `beats_null` barely moves under
that change (0.24/0.35/0.15 at 445 mm, 0.23/0.34/0.14 at 425), so row 3 does not
depend on the open question and row 2 does.

**What it does not show.** Nothing about phase beyond the shading — the sync is
19.2 / 16.0 / 9.3 ms and the windows hold their reps, but a whole-rep check of
the kind C25 had to make on bench has not been run here. And nothing about
whether a landing found on marker footage falls at the same instant as one on
template footage: these are the first captures that COULD answer it, and it is
undone rather than blocked.

---

## 43 — the ceiling on constant error models (C28, 2026-08-04)

Branch `c28-imu-video-oracle`. `src/oracle.py`. Four panels, and the top-left
one is the answer to "how close can the IMU be fitted to the video".

**Top left — the ladder.** Blue is each model fitted ON the capture it is scored
on, so it is a CEILING no estimator can beat. Red is leave-one-out. The null is
the dashed line at ~1.6 cm. Read the gap between the bars, not the blue bar:
fifteen physically-named parameters fitted against the answer reach 1.23 cm, and
every one of them collapses to 3.3-4.6 when asked to transfer to a capture it
was not fitted on. **P3's error is not a constant in any frame.**

**Top right — which frame the pause bias belongs in.** `calibrate.accel_bias`
subtracts a world-frame constant; its own docstring says the bias is body-frame.
Correcting that helps deadlift (orange, 5 of 6) and hurts bench (purple, 10 of
11, including `bench_90x4_2` going 0.64 -> 2.32). That split is the figure's
second finding: the pause residual is a MIXTURE of a world-frame tilt leak and a
body-frame offset, so neither pure correction is right.

**Bottom left — separating them needs the two holds to DIFFER.** Recovered
body-frame |b| against how far the wrist rotated between the opening and closing
C3 holds. Above ~30 degrees it lands on P4's table measurement of 0.0245 m/s^2
(the blue line) — the first on-wrist measurement of the accelerometer bias.
Below, the solve is amplifying hold-mean noise by 4-16x and returns 0.1-0.4.

**Bottom right — and two holds can never be enough.** The third singular value
of `R_open - R_close` is zero at every separation, because
`R_1 - R_2 = R_1(I - R_1^T R_2)` and a rotation fixes its own axis. Rank <= 2,
exactly, forever. The body-bias component along the axis the wrist turns about
is unobservable from two postures. **Three holds at least 30 degrees apart close
it** — a five-second change to the capture protocol, no code.

**What it does not show.** Nothing about time-varying error, which is what is
left once this family is excluded, and nothing about whether the marker referee
itself is right in absolute scale — C27's sticker-circle measurement is upstream
of every number here, though `beats_null` is nearly invariant to it. *(That
measurement CLOSED on 2026-08-17, H14: the referee was reading 4.9-11.4% small.
`beats_null`'s invariance held — median 1.25 -> 1.26 across the corpus — so this
page's conclusions stand and its absolute metre figures do not.)*

---

## 44 — the jump state at the impact (C29, 2026-08-05)

Branch `c29-jump-state`, cut from `c28-imu-video-oracle`. `oracle.jump_correction`.

**Left — the sweep, and the flat left edge is the finding.** The same observable
velocity error is removed over a window of decreasing width at the impact. At
0.02 s the curves sit on the shipping line: a pure jump changes NOTHING, because
`rep_bounds` ends each rep at an impact, so a step there is constant within a rep,
linear in position, and `detrend_rep` removes a line. The correction is in the
detrend's null space, exactly. The right-hand end is C28b's whole-interval spread,
which is worse than shipping. Note the null (green) sits far below everything.

**Middle — the apparent optimum, per rep.** At ~1 s the per-capture median looks
16% better. Per rep it is a coin flip: 10 of 20 improved, median 6.15 -> 6.62 cm.
The points above the diagonal are as numerous as those below.

**Right — why the per-capture win is not real.** The improvement correlates with
the observable (+0.523) AND with the baseline error (+0.551). Partial out one at
a time and the observable does not survive (+0.184) while the baseline does
(+0.272). **The inverse of C28b**, where the observable screened off the confound
and that is what made it believable. The three captures that improved were the
three worst.

**What it does not show.** Nothing about the vertical, which is untouched by
construction — horizontal-only, so ROM stays at 56-57 cm where B6's vertical
splice pushed it to 82.6 against a 61 ceiling. And nothing about a detrend whose
boundaries avoid the impacts, which is what this figure argues is the only move
left.

---

## 46 — the horizontal channel is EMPTY, not noisy (C30, 2026-08-05)

Branch `c29-jump-state`. The first measurement of the acceleration error as a
time series. Differentiate the marker path twice (Savitzky-Golay, 0.70 s, order
3) and put the reconstruction's position through the IDENTICAL filter, so both
sides carry the same bandwidth. Noise floor where the bar is provably still:
0.00125 g, ~15x below the signal — only possible because C27's conic tracker
holds 0.28 px residual at 100% coverage.

**Left is the positive control and it is why the right panel can be believed.**
Vertical acceleration, video against reconstruction, r = 0.976. Same clip, same
filter, same code path.

**Middle: the same thing horizontally, r = -0.176.** Optimised post-hoc over all
90 projection directions it reaches only -0.23, so B4's unresolved axis is not
the explanation. The reconstruction's fore-aft acceleration is uncorrelated with
the bar's while being the same size.

**Right: why this axis and not the other.** The bar's true fore-aft acceleration
is the smallest real quantity in the system — 6-7x below its own vertical. Any
wrist-versus-bar term is therefore 6-7x more damaging horizontally, and that
ratio holds without knowing `d`. The lever bar is an order-of-magnitude estimate
for |d| = 12 cm over random directions; the vertical's r = 0.976 bounds the true
term below it.

**What it does not show.** It does not prove the lever arm is the term — only
that a plausible one is the right size, and that P3's stated mechanism is not
(17-23% of variance at a bias 170-500x the measured one). Deadlift only. And it
says nothing about bench, where the horizontal error is already 0.6-3.7 cm and
two captures beat the null 4x — this is a deadlift diagnosis.

**CORRECTION, C30b (2026-08-05).** Figure 46 is a DEADLIFT result and its title
overgeneralises. Run on bench, the same test gives |r| = 0.79-0.94 on the
horizontal against deadlift's 0.10-0.23 — the channel is not empty. The wrist
lever arm named in the right-hand panel is also not the discriminator: wrist
swing per rep is 17.3 deg on bench against 21.8 on deadlift, nearly the same.
What separates the lifts is the floor impact, 15-22 g against 2-6 g. See
TASKS.md C30b.

**SECOND CORRECTION, C31 (2026-08-06) — the title is wrong and so is C30b's
correction of it, in different ways.** The owner tape-measured `d` the next day.
Re-run with step 6 ON, the deadlift best-direction horizontal correlation goes
**0.118-0.232 -> 0.432-0.641** while bench moves only 0.798-0.919 -> 0.814-0.937
and the vertical control is unmoved at 0.967-0.994. So:

- C30's **title** ("EMPTY") is wrong — the channel was masked, not empty.
- C30's **right-hand panel** is right after all. The lever arm it names as the
  candidate IS the dominant term on deadlift, which is what C30b denied.
- C30b's symmetry argument is the part that failed: it inferred equal DAMAGE
  from equal absolute contamination (3.6 vs 4.5 cm of sweep), and damage is
  contamination against what survives it. The `|d| = 12 cm` in that panel is
  9.5 cm by the tape, so its lever bar is ~20% oversized.

The floor impact remains a live suspect for the residual, which is now 0.43-0.64
against bench's 0.81-0.94 rather than 0.12 against 0.92. See figure 48 and
TASKS.md C31.

---

## 47 — the paused squat's cadence drifts, and no constant could see it (C31a, 2026-08-06)

`python run.py --pausedsquat`. Branch `c29-jump-state`. Four panels: band-passed
vertical velocity — the signal `segment.rep_bounds` actually works on — for the
two paused squats that counted 3 of 4 and the one that counted 4 of 4, then the
tolerance each capture admits under each rule.

**The first three panels exist to make one thing visible: the dropped rep is a
REAL rep.** It sits in `_similar_cluster`'s winning cluster with its siblings at
0.75-0.97 shape correlation and reconstructs 65.4 / 69.7 cm, and it is discarded
purely because the gap before it is longer than the others.
`squat_pause_140x4_3` drops its LAST rep and `squat_pause_140x4_2` its FIRST —
which is why panel 4 matters: the mechanism is the gap ratio, not a position in
the set.

**Panel 4 is the negative result and the reason a re-tune was not the fix.**
Under the old global-spread rule `bench_spoto_90x5_1` counts correctly only
below 1.572 and `squat_pause_140x4_3` only above 1.576, so the two grey bars
**never overlap and no constant satisfies both**. The green bars — local drift
admission with an evenness tie-break — do overlap, over 1.460-1.528. Ships at
1.50.

**What it does not show.** Whether the new margin holds: 2.4% either side,
against the 8-11% the old constant enjoyed, and the plateau's two edges are two
different captures on two different lifts. A capture that pauses harder will
push the floor into the ceiling. It also does not show the discriminator C31a
noticed and did not pursue — both paused squats have a rejected low-velocity
lobe INSIDE the long gap where `bench_spoto_90x5_1`'s post-set gaps have none,
which would separate the two cases without any tolerance at all.

---

## 48 — the bar path with `d` measured, step 6 off and on (C31, 2026-08-06)

`python run.py --dpaths`. Branch `c29-jump-state`. The first figure in this
directory drawn with step 6 ON. Three captures, each scored **twice against ONE
tracked video path**, so the only thing differing between the two curves is
`wrist_offset` — no re-track, no re-sync.

`d` comes from `correct.WRIST_OFFSET_M`, the owner's tape of 2026-08-06. It is
not fitted; B2 established that fitting it against the video is ill-conditioned
and returns |d| = 129 cm under leave-one-out, and C31 re-confirmed that by
fitting `lever` on top of the tape and landing 108/74/4 degrees away from it.

**Read the three panels as a disagreement, not a result**, which is why they
were chosen: a deadlift, the bench where `d` clearly helped (`bench_95x2`,
1.46 -> 0.80 cm) and the paused bench where it clearly hurt
(`bench_spoto_95x5_1`, 1.17 -> 3.54). `d` helps the ACCELERATION correlation on
6 of 6 benches and the POSITION rms on only 3 of 6. A figure showing only the
wins would be the exact failure this project keeps repeating.

**Stale label, FIXED (C31, after C33 recorded it):** the orange series read
"step 6 OFF (ships)", which named the *old* default once step 6 shipped ON in
`70b2a63`. It now reads "step 6 OFF (was the default)".

**What it does not show.** Why the two referees disagree about `d` — it helps
uniformly under `truth.py`'s template and is mixed under `markers.py` — which is
the highest-value open question in the project. See `FINDINGS.md` P2.

## 49 — does a PAUSE let Core Motion re-reference gravity mid-rep?

`python run.py --pauseattitude`. Branch `c29-jump-state`. The owner's hypothesis,
2026-08-06: a pause holds the watch quasi-static long enough for the
accelerometer to serve as a gravity reference, so Core Motion corrects
accumulated tilt DURING the rep — a step at the same phase every rep, which is
P3's signature and is exactly what step 7's boundary-anchored linear detrend
cannot remove.

**The observable needs no video and no sync**, which is why this was cheap:
Core Motion's attitude increment minus the gyro's, per sample (midpoint rule —
a left-endpoint one makes fast motion look like fusion, and contaminated the
first pass). Decomposed in the world frame into TILT and YAW, because **gravity
can correct tilt and is geometrically incapable of correcting yaw about
gravity, while numerical error has no such preference.** The RATIO is therefore
the decisive statistic, not the magnitude.

**Verdict: half right, and the half that fails is the useful half.**

*The mechanism is REAL.* Tilt/yaw exceeds 1.0 on every one of the 30 labelled
captures and RISES when quasi-static on 22 of them (typically 2.0-3.1 still
against 1.0-2.4 moving). Core Motion visibly leans on the accelerometer for
gravity, and leans harder when the watch is still.

*But it separates the two LIFTS, not the two STYLES.*

    lift    peak/min of the within-rep tilt profile   peak phase
    squat   paused 3.84  vs continuous 2.34           0.62  <- the bottom hold
    bench   paused 2.17  vs continuous 2.28           0.28  (no concentration)

A paused SQUAT concentrates the correction mid-rep, about 2x, right at the
bottom hold. A paused BENCH does not, and its absolute correction is LOWER than
a touch-and-go bench throughout.

**Why the general hypothesis fails:** continuous lifts already spend **34-57%
of their samples quasi-static** — between reps, at lockout, in the setup — so a
pause adds no gravity-reference opportunity the lift did not already have. It
changes WHERE the correction lands, not how much there is, and only on squat.
So it does **not** explain the paused-bench `d` dissent, which C32 had
nominated it for.

**What it does suggest, and this is the part worth chasing.** The differential
within-rep tilt correction is 0.5-0.9 degrees accumulated across a rep. A tilt
error theta leaks `g*sin(theta)` into the horizontal, so double-integrated with
step 7's endpoint line removed that is **4-10 cm of surviving horizontal
error** — the same order as P2's entire budget. Treat it as an
order-of-magnitude bound rather than a measurement: it assumes worst-case
geometry with the whole leak on one axis. But it says Core Motion's *mid-rep
fusion corrections* are a plausible major contributor to P3 **regardless of the
pause**, and nothing in this project had looked at them. Gated in
`tests/test_real_data.py` — both halves, so the refuted half is not
re-proposed.

## 50 — what the branch pipeline produces, all three lifts

`python run.py --pipelinenow`. Branch `c29-jump-state`. The product view rather
than a diagnostic: step 9's output, reps overlaid and start-aligned, fore-aft
stretched 4x as the display would draw it, with the video over the top wherever
a referee exists. **Every figure in this directory numbered below 48 shows a
different quantity**, because step 6 was off when they were drawn.

Six captures, chosen to span what the corpus can and cannot check, and the
spread across them is the point:

    bench_95x2           2/2 reps   h 0.80 cm   BEATS the flat line 5.39x
    bench_spoto_95x5_1   5/5 reps   h 3.54 cm   loses 0.88x
    deadlift_155x6_1     6/6 reps   h 4.57 cm   loses 0.78x
    deadlift_160x6_1     6/6 reps   h 6.65 cm   loses 0.25x
    squat_pause_145x4_1  4/4 reps   no referee
    squat_170x1          1/1 reps   no referee

`bench_95x2` is what the project is trying to build: the reconstruction sits on
the video for the whole rep, inside the 1 cm spec. `deadlift_160x6_1` is the
distance still to go — it sweeps 35 cm of fore-aft where the bar moved a few,
and the shape is not the bar's. Both are the same code on the same day.

**Counting and extent are clean on all six** — 24 of 24 reps, every ROM inside
`truth.VERTICAL_ROM_M`. What fails is the horizontal, and only the horizontal.

The two squat panels are drawn without a referee because `metrics.vs_truth`
still refuses squat. That refusal is now **stale rather than wrong-headed**: its
stated reason is about the old template footage. But the replacement claim
first made here — that the 8-sticker plate tracks at 100% — was measured on ONE
capture and generalised, and is corrected (C31, 2026-08-07): two of the four
squat clips track cleanly and two do not, `squat_170x1` and
`squat_pause_140x4_3` reporting 14.0 and 24.7 cm of travel against 65-70 cm
squats. Replacing the refusal needs a validated squat sync, which nobody has
built, AND half the footage fixed. Until then the squat panels show a
reconstruction nothing has checked, and should be read that way.

*Both conditions were met and the refusal is gone (G2, 2026-08-15). F1's
`src/vtrack/` fixed the footage — all four squats track — and `bench_sync`
turned out to work better on a paused squat than on any bench, corroborated by
`metrics.pause_landmark`. Squat panels drawn after that date carry video. See
`analysis/55`.*

## 51 — do the impact correction and the wrist lever COMPOSE?

`python run.py --jumpd`. Branch `c29-jump-state`. **No.** They correct the same
thing.

P6 was measured entirely before `d` existed: C29's rest-window jump correction
took deadlift horizontal rms from 10.66 to 3.93 cm with step 6 OFF, on the axis
`d` most affects. Four arms on all six deadlifts, sharing the same rest-to-rest
windows so the comparison is internal:

    arm       median h rms   median beats_null
    control       10.66            0.21          <- C29's honest baseline
    C29            3.93            0.69
    d              9.82            0.22
    both           3.89            0.68

The control and C29 rows **reproduce C29's own numbers exactly**, which is what
licenses reading the new ones. `d` alone buys 8%; C29 alone buys 63%; together,
nothing beyond C29 — three captures better with `d` added, three worse.

Why, and the first version of this paragraph got the mechanism wrong. It said
"the largest wrist rotation in a deadlift IS the turnaround at the floor". The
owner challenged it: the arms hang near-vertical through a deadlift, so nothing
reorients and the only available motion is a twist. Correct, and measured
rather than argued (C31, 2026-08-07):

    swept angle per rep                          193-311 deg
    net wrist swing per rep (C30b)               ~22 deg
    share of swept angle in the outer 20% of phase   53-67%
    peak of |d/dt(R.d)|                          phase 0.03, 7.8x rep median

So the lever term really does move most at the floor — but ~90% of the angular
motion is BACK-AND-FORTH, not reorientation. There is no turnaround. It is
**strap ringing**, which B6 already identified: the watch still moving after the
bar has stopped. The *watch* rotates; the wrist does not. The conclusion stands
— `d` and C29 overlap because both act at the impact — but the stated mechanism
was wrong twice over.

**And the corrected mechanism carries something the wrong one did not.** Step 6
assumes `d` is a rigid constant in BODY coordinates. During ringing the watch is
not rigidly indexed to the wrist, so at exactly the instant `R(t).d` moves most,
step 6's premise is false. Applying it there may be actively wrong rather than
merely useless. Nobody has followed that up.

*Two corrections to the record, both against earlier claims of ours.* C29
reported `deadlift_155x6_1` and `deadlift_180x3` crossing `beats_null = 1.0`;
re-run here only `155x6_1` does, at 1.21, with `180x3` reaching 0.89. And this
does **not** argue against step 6's default — C29's correction is not in the
pipeline, and against the shipping detrend `d` still improves all three
marker-refereed deadlifts.

---

## G1 — two segmentation defects, and the whole corpus against the cached tracks (2026-08-15)

### `53_segmenter_fixes.png`

The two defects the 2026-08-08 captures exposed, evidence on the left and the
rule on the right. Both were invisible to a rep count and both were settled by
the cached video track — which is the reusable lesson, not the fixes.

**A/B — `deadlift_150x4_1` segmented five windows for four reps.**
`impact_anchors` read acceleration MAGNITUDE alone, and the extra anchor at
7.03 s is a 250 ms RAMP: |a| climbing 0.7 → 1.6 → 3.6 → 6.9 g while |ω| climbs
to 27 rad/s and then snaps to a stop. The watch sits ~9.5 cm from the wrist
axis, so `α·r` = 6.3 g against the 6.9 g measured. It is the lifter setting
their grip, and the video has the bar flat on the floor at 1.4–1.5 cm from 0 to
11 s. No threshold separates it: the counterfeit peaks at **7.01 g** and the
weakest real landing in the corpus is **6.69 g**. Panel B is the discriminator
that does — the median wrist rate in the second BEFORE the spike, measured on
every candidate above 4 g in all sixteen captures:

    28 real floor landings, 6 captures        0.39 - 0.98 rad/s
    5 genuine rack collisions (bench, squat)  0.33 - 0.56       kept, correctly
    4 setup wrist swings, 4 captures          1.65 - 2.83       rejected

The rack collisions are the control: the rule rejects a ROTATION, not a quiet
impact. Counts are correct for any gate in [0.98, 2.83] and 1.3 ships.
**Three other discriminators were measured and are worse**, recorded so they
are not re-tried: peak-to-precursor ratio separates by only 1.41×; the
high-frequency energy fraction looks good on deadlift and INVERTS on the
control, flagging the squat rack collision at 0.030 while passing all four
swings; and the rotational term evaluated AT the peak does not separate at all
(0.45–1.64 real against 0.53), because the impact itself spins the wrist.

**C/D — `bench_117.5x1`, the corpus's first bench single, segmented two.** The
real press at 21.9 s and a setup arm movement at 10.6 s correlate **0.80** in
fixed-duration shape and carry 0.290 against 0.304 m, so shape, size and
cadence all tie; the video has the bar in the rack until 16 s. Panel D is the
rule: a loaded bench or squat rep is a closed kinematic chain and is CONSTRAINED
to vertical, where setting up is an arm reaching freely.

    36 real bench and squat reps, 9 captures   3.64 - 15.08
    setup movement, bench_117.5x1 at 10.6 s    1.00

Correct for any gate in [1.02, 3.62] — a 255% plateau — and 2.0 ships. The amber
point is `deadlift_200x1`'s real pull at 2.59: a pull sweeps the bar to the
shins and also carries C12's invented lockout excursion, so a deadlift has the
corpus's thinnest margin — 2.59 against a 2.13 runner-up, where bench and squat
run 4.4× and 12.6× clear. The rule abstains when no member of a cluster passes;
nothing exercises that today.

**Verticality does a second job this figure does not draw, and it caught a third
defect.** It also ranks a DEGENERATE cluster, replacing a displacement rule that
had put `deadlift_200x1`'s only window on the DROP — 18.97–19.92 s at a
plausible 43.8 cm, where the video has the pull at 15.7–17.5 s. On the three
singles the corpus holds, displacement is right once and verticality three
times. With `_full_cycles`'s `sets_down` also fixed (it was hardcoded `False`,
so a lift resting on the floor got the bench convention), that window is now
15.51–19.43 s at 55.0 cm. See TASKS.md G1 defect 3.

**The tempting fix is a trap and it is drawn here so nobody re-tries it.**
Raising `similarity` from 0.7 to 0.83 does break the false pair — and then the
singleton fallback picks the 5.4 s unrack at 0.455 m. Right count, wrong window,
`squat_160x1`'s failure again, and invisible to every count gate.

### `54_pipeline_vs_tracked.png`

All sixteen `data_v2` captures against `data_v2/tracked/`, step 6 ON, drawn as
step 9 would: reps overlaid, start-aligned, fore-aft stretched 4×. Counting is
**16/16 captures, 64/64 reps**. The reconstruction is a different question and
this figure is about that.

**Six of sixteen could not be scored at all**, and they were not six arbitrary
captures:

    squat x4              `vs_truth` refuses squat outright
    bench_117.5x1         `bench_sync` needs a rep cadence; a single has none
    deadlift_200x1        the clock fit needs >=2 landings for offset + slope

*G2 removed the squat refusal on 2026-08-15 and the four squats now score, so
this figure was re-rendered and reads THREE unscored — and they are exactly the
three singles. See `analysis/55`.*

So **two of the three captures G1 repaired are singles that cannot be checked
against the video at all** — the segmenter is weakest exactly where the referee
cannot reach. Of the ten that scored when this was written:

    bench_92.5x6_1        h 1.23 cm   v 2.21   beats null 3.05
    bench_92.5x6_2        h 1.61      v 1.67   beats null 2.55
    bench_spoto_95x5_2    h 2.41      v 2.13   beats null 1.52
    bench_spoto_95x5_1    h 3.64      v 2.11   LOSES 0.89
    deadlift_150x4_1      h 2.66      v 4.14   LOSES 0.81
    deadlift_160x4_2      h 3.98      v 4.90   LOSES 0.38
    deadlift_160x6_2      h 4.40      v 3.69   LOSES 0.35
    deadlift_170x4_3      h 5.54      v 12.14  LOSES 0.25
    deadlift_160x6_1      h 7.52      v 3.54   LOSES 0.20
    deadlift_185x3        h 10.72     v 1.69   LOSES 0.14

**All six deadlifts lose to drawing no fore-aft motion whatsoever**, and the
picture says why: the blue reconstructions sweep 20–35 cm of fore-aft where the
grey video paths stay inside ±5 cm. Three of four benches beat the flat line and
the best capture in the corpus is still 1.23 cm against a 1 cm spec.

---

## G2 — the squat refusal lifted, and the sync corroborated (2026-08-15)

### `55_squat_sync.png`

Squat is refereed for the first time. The refusal in `metrics.vs_truth` was
never really about squat being unmeasurable — it described the v1 plate template
on footage F1 deleted — so what actually had to be established was that a squat
video can be put on the IMU clock at all. The four panels are that argument.

**A — the correlation curve, bench against paused squat.** Bench's has rivals a
whole rep away above `RIVAL_FRAC`; the squat's does not. That is `bench_sync`'s
documented ambiguity, and the pause is what breaks it. Read the sidelobe
heights rather than the rival counts: bench 0.720–0.794, squat 0.578–0.693, so
`squat_pause_145x4_1` is **one percent** from having a rival. The rival test
would not have survived a noisier capture.

**B — the corroboration, which is what the claim actually rests on.** The bottom
of each rep is named twice by instruments that cannot see each other: the raw
IMU through `segment.dwell_instants`, and the tracked video height. Seven
captures, agreement 0.003–0.083 of a rep against a 0.25 gate. This is also the
first on-lift evidence any BENCH sync has had — its validation was transferred
from deadlift until now.

**C — one capture's alignment, drawn.** A scatter of offsets is still a number,
and this project's recurring failure is a number that looks fine. Every video
bottom sits inside exactly one IMU rep window, at phase 0.41–0.52.

**D — the guard, tested by breaking it.** A whole-rep sync error injected in
both directions on every capture with a cadence: 14 injected, 14 refused, 0
missed, with the real captures clustered two orders of magnitude below the gate.

Scored: **h 1.88 / 2.97 / 2.65 cm, beats_null 1.71 / 1.24 / 1.50** on the three
paused squats — all three beating the flat line, which no deadlift does, and
second only to `bench_92.5x6_1/2` on horizontal. `squat_170x1` is still refused,
because it is a single and has no cadence; the three unscored captures in the
corpus are now exactly the three singles. *(All three scored the same day by
G3 — see 56.)*

## 56 — singles and doubles: the sync, not the segmenter, refused them (G3)

`56_singles_doubles.png`, `run.py --shortsets`. The corpus reaches **16 of 16
scored**: `bench_117.5x1`, `deadlift_200x1` and `squat_170x1` had never been
refereed, and they are one single per lift.

**A — why the sweep must be bounded by overlap, not by lag.** `bench_sync`
widens until its peak is interior, which is right for a long set and fatal for a
single. On `deadlift_200x1` the shipping 11.75 s window picks a lag **10.5 s
wrong** and a 20 s window picks one **18.8 s wrong** — and both score HIGHER
than the true peak (0.490 and 0.688 against 0.335). A single is a flat record
with one event in it, so sliding the records apart correlates flat against flat
on ever less of it. The shaded band is where the two records still share 80% of
the shorter one; the dashed line is what that capture's own floor impact says.

**B — accuracy against answers the module did not supply.** Twelve singles and
nine doubles cut out of the multi-rep captures, each scored against the offset
its own full capture fits: **median 7.5 ms / worst 103.9 ms** for singles,
**5.0 / 15.0 ms** for doubles. The shaded band is the multi-rep deadlift sync's
own 8.4–9.7 ms residual — the best-validated clock in the project.

**C — what it buys.** The three singles drawn against video that could not
previously be put on their clock at all. h **0.96 / 2.66 / 2.05 cm**, and all
three beat the flat-line null (**3.31 / 1.08 / 2.01**). `deadlift_200x1` is the
first deadlift in the project to beat the null — but its `beats_null` is a
median over ONE rep, so it is far weaker evidence than the six-rep figures it
sits beside.

**D — the owner's proposed rule, measured and NOT shipped.** "Maximum
displacement between IMU dwells" loses to the existing segmenter on every
reading tried (median IoU 0.00 and 0.29 against 0.70). The cause is one number:
integration drift produces more apparent displacement than a rep does, so the
criterion prefers the longest admissible window — the window it picks on
`bench_92.5x6_1` claims 86.8 cm on a 27 cm bench press. Recorded rather than
deleted: on a drift-free position estimate it would very likely work.

*Not shown, and it is the honest gap: **deadlift doubles are not validated.** A
deadlift set has no gap between reps (measured 0.00 s on all six), so truncating
to two reps ends the record exactly at the second landing and cannot imitate a
real double. Bench and squat doubles are validated, 7 of 7.*

---

## 57, 58, 59 — why the deadlift horizontal is large (H1, 2026-08-15)

`python` scratch, not a `run.py` driver; the full record is
**`analysis/H1_STATE.md`** and the numbers below are all measured with step 6
ON, against the `vtrack` referee, through `metrics.vs_truth`.

**57 `57_deadlift_horizontal_origin.png` — the mechanism.** The invented
fore-aft is a constant-acceleration parabola per rep whose size GROWS through
the set (5.2 → 34.9 cm on `deadlift_160x6_1` while the video's own stays at
4.2–5.4). Every stage after acceleration is linear, so candidate error fields
are pushed through the real pipeline and scored leave-one-rep-out: a growing
horizontal acceleration explains 84–91% of the error out of sample on the three
captures where it is largest and the sync is sound. Panel D is the reason to
believe it — a tilt must leak first-order into horizontal and second-order into
vertical, and the same fitted parameters score 0.84–0.91 on horizontal and
−1.63 to −0.02 on vertical. **It is not a gyro bias of the watch**: in watch
axes the six fitted directions scatter 27–149° apart.

**58 `58_deadlift_display_axis.png` — the bigger lever.** Step 8 picks the
display axis by maximum variance, and on a deadlift the variance is the
invented drift, so the pipeline displays the axis along which it is most wrong.
Swept over every azimuth: on four of six captures the shipping axis is worse
than 72–97% of all axes and sits 60–89° from the best one, and on the best axis
two deadlifts beat the null (1.19 and 1.03 cm against 1.54) — which no deadlift
has ever done. The shipping axis sits on or beside the *peak* of the error
curve on four panels.

**59 `59_deadlift_horizontal_fixes.png` — four trials, none shipped.**
Removing only the GROWTH of the per-rep curvature (V2) is the only one that
helps both groups — deadlift median 4.97 → 3.20, bench+squat 2.41 → 2.04, 10 of
13 captures — and it fails on the worst capture. Removing the curvature
entirely (V3, D1's `parabola_detrend`) and taking the axis perpendicular to the
drift (R4) are the two best deadlift results (2.17 and 2.64) and both regress
bench and squat, for the same reason: there the per-rep curvature IS the real
J-curve. No gate separates the two groups — deadlift growth runs 1.2–35.0 %/rep
against bench+squat's 1.3–22.8. **Panel D is the floor under all of it: the
shipping `vtrack` referee reports a median 3.0 cm of fore-aft while the bar is
STILL at lockout**, so every fix above lands inside the referee's own
resolution and the ranking between them is not established. C12 found this on
the v1 template tracker; F1 deleted that tracker and this is the first check of
`src/vtrack/` at lockout, which has the same defect.

## 60 — step 8's axis is the bias's axis, on all three lifts (H2, 2026-08-16)

`60_display_axis_is_the_drift.png`. Follow-on to H1, on the owner's question:
in taking maximum variance, is step 8 picking the bias rather than fore-aft?

**Yes, and not only on deadlift.** Against the video-identified fore-aft
direction (the azimuth whose projection best *correlates* with the video, so
direction is not confounded by amplitude), the axis error is 45–84° on deadlift,
10–84° on bench and 32–49° on squat — **11 of 13 captures outside the 20°
`AXIS_TOLERANCE_DEG` the module declares for itself.** Panel B is the mechanism:
step 8's axis sits **4° from the axis of the invented parabola alone**.

Panels C and D are why no gate can catch it. The drift-owned axis is *better*
conditioned than a bar-owned one — bootstrap spread over reps is 1–10° on every
capture, 2° on an axis 84° wrong — and the eigenvalue ratio `confidence` gates
on is uncorrelated with the error (Spearman rho +0.03). The drift is smooth and
common-mode, so every rep votes for the same wrong direction. **Precision
without accuracy**, and the same shape as C31's `_trial_merit` rewarding
rigidity when furniture is maximally rigid.

Removing the drift does not help: the residual's axis is 50° from the video
direction against the drift's 47°. The true fore-aft is not the dominant
horizontal variance on *any* capture here. Two rotation-based estimators are
measured in `analysis/H1_STATE.md`; only "a barbell stays level" moves deadlift
(64° → 36°), and it costs bench. **Caveat**: the reference direction moves 38°
between odd and even reps, so single-capture angles are soft — but adjacent sets
of the same lift agree to 1–17°, which is the evidence for locking a
per-session, per-lift axis.

## 61, 62 — the deadlift side-on view, and a single-set fix (H8, 2026-08-16)

**61 `61_deadlift_side_on_now.png` — the current state, at TRUE aspect with no
4x stretch.** Top row is the side-on view the product would show, reconstruction
and bar on the same axes; bottom row is the horizontal channel alone against rep
phase. Every rep bows the SAME WAY to −10 to −20 cm at mid-phase while the bar
stays inside ±5 cm. Reconstruction sweeps 2.8–34.8 cm against a bar sweeping
3.1–11.2.

**62 `62_deadlift_single_set_fix.png` — a fix that uses ONE set and nothing
else.** No history, no prior sets, no video at runtime: a world-horizontal tilt
ramp fitted against the set's own REP-TO-REP DISPERSION, anchored to vanish at
the first rep. Median 4.97 → 3.78 cm, and the three fastest-growing sets take
the three largest gains (`160x6_1` 7.52 → 1.97, `160x6_2` 4.40 → 1.74). Panel A
draws it: the corrected paths hug the bar where the shipping ones sprawl.

Two things the figure is careful to show rather than hide. `deadlift_185x3` does
not move at all (10.72 → 10.69) because its drift does not grow — its best axis
on the same path is 1.89 cm, so its whole error is the AXIS. And `150x4_1` grows
2.1x yet REGRESSES 2.66 → 5.03, so growth alone does not predict the outcome; it
is also the capture nearest its own null, with least to win.

The objective is the design: "minimise horizontal excursion" would collapse to
the flat-line null and score well by drawing nothing, and unanchored dispersion
equalises the reps in the wrong direction (`150x4_1` 2.66 → 8.17 while its
dispersion fell). Full record in TASKS.md H8.

## 63 — the deadlift plane from attitude alone (H9, 2026-08-16)

`63_deadlift_anatomical_axis.png`. The owner's observation, and it holds: on a
deadlift the forearm hangs vertical — the watch's crown sits at −80° elevation —
so **the watch's y–z plane IS the horizontal plane**, and the display axis
collapses to ONE angle, where the bar sits around the wrist. That is a constant,
like `d`, not a per-capture estimate.

Panel A sweeps it. The best single value over the six deadlifts is 20° off the
screen normal, **the four bench captures put it at 26° independently**, and the
basin is 20° wide (11–31° within 0.5 cm) — so a shipped constant will do, unlike
`d`, which had no interior optimum at all.

Panel B: combined with H8's path fix, median **4.97 → 2.26 cm, within 0.20 cm of
the best axis that exists**. The halves compose because they fix different
things — `deadlift_185x3` is the proof, immovable by any path fix (10.72 → 10.69)
and taken to 2.02 by the axis alone against a best-possible 1.89.

Read the limits with it: nothing crosses `beats_null` yet (0 of 6, though
`160x6_2` is at 1.72 against 1.54 where it was 4.40); `170x4_3` and `150x4_1`
regress; the 20° optimum is in-sample and the out-of-sample evidence is bench's
26°; and **every corrected number is now inside the referee's own 3.0 cm
fore-aft error at lockout**, so this corpus can no longer measure the deadlift
horizontal. Full record in TASKS.md H9.

## 64, 65, 66 — the product display layer (H13, 2026-08-16)

Three figures for `src/display.py`, which is a layer AFTER step 9 rather than
a change to any of the nine steps. Nothing upstream moved and no shipped
reconstruction number changed; these measure how a path should be DRAWN.

**64 `64_smoothing_methods.png` — four smoothers, swept.** Panel A draws one
real rep at three levels, and 0.50 is visibly the wrong answer: it overshoots
the lockout by ~5 cm. B and C are the decision — what each level costs the
REAL BAR, measured by putting the video path through the identical smoother —
against a rule fixed before the level was chosen: stay inside half of each
axis's spec. **Savitzky-Golay costs least at every level on both axes**
(0.17 cm / 0.65 cm at the shipped 0.20, against a boxcar's 0.50 / 2.79).

Panel D is the finding, and it is a flat line: **smoothing does not change
accuracy at any level or by any method**, 2.07 cm throughout. That is a
diagnosis rather than a null — the reconstruction's horizontal error is at rep
frequency (P3), so there is no high-frequency component for a smoother to
remove. Smoothing buys legibility; it costs nothing and it fixes nothing.

**65 `65_average_paths.png` — the average rep, and which rep to leave out.**
Panel B is the result: **the ALIGNMENT is everything and the averager is
nearly nothing.** Resampling each rep about its own turnaround rather than on
a uniform time grid takes the vertical error against the video's own average
from 8.30 cm to 3.00; mean, median and trimmed sit at 1.56/1.52/1.52
horizontal. Panel C: averaging buys what smoothing did not, 1.95 -> 1.52 cm.

Panel D is the part to read carefully. The anomaly flag is scored against the
video rep by rep: **5 IMU flags, 6 video flags, 4 the same rep**, and on every
set where the IMU fires the video fires on that rep too. One false positive,
two misses. So the odd rep is usually REAL — on the deadlifts it is the last
rep of the set — which is exactly why EXCLUDING it does not improve the
average (1.52 -> 1.70): the deviation is shared, so dropping it removes signal.
The feature's value is the label, not the deletion. `deadlift_170x4_3`'s video
scores are inflated by its own 22.8% clock drift, a defect G3 recorded and
nobody has fixed.

**66 `66_product_view.png` — what the app would draw.** One column per lift:
the smoothed average path coloured by speed, the set's reps faint behind it,
the flagged rep dashed rather than hidden, and a per-rep mean-concentric-
velocity strip with the video's own value beside each bar. The fore-aft axis
carries NO scale, which is the one deliberate omission in the figure: of
everything drawn here, fore-aft MAGNITUDE is the only quantity the video
refuses to corroborate (r = -0.03 over 61 reps, against +0.97 for velocity and
+0.99 for ROM).

**67 `67_sticker_circle_scale.png` — the sticker circle, measured with a tape
(H14, 2026-08-17).** The referee's absolute scale stopped being a fitted
constant. Panel A is the whole argument and it is geometry, not statistics: a
sticker is 2.0 cm across and is stuck with its outer edge on the plate rim, so
its centre sits 1.0 cm inboard and the circle the tracker fits is the plate
diameter **less 2.0 cm**. That retires `STICKER_RATIO = 0.858` and, more
usefully, retires the ratio FORM — the inset is an absolute distance, so no
single fraction of the plate can be right for a 425 notched plate and a 450
blue disc at once (0.953 against 0.956). Two entries of `vtrack.PLATE_M` were
also wrong against that table's own definition: bench held 0.45 for a 425 plate
and deadlift 0.445, the BUMPER rather than the notched plate the stickers are
on. Net: **+4.9% bench, +6.1% deadlift, +11.4% squat.**

Panel B is the corroboration, and it is independent of the tape. The video's
per-rep vertical ROM over the IMU's sat **below 1.0 on 16 of 16 captures**,
median 0.926/0.924/0.936 by lift — a systematic ~7% with no per-lift story.
C27 had measured the deadlift third of it from the other side (video 4.6-9.3%
below the reconstruction, "~0.92 would close it exactly") and the tape predicts
+6.07% there without being fitted to it. After: 0.971/1.029/0.993, and the
median |ratio - 1| falls 0.068 -> 0.029.

Panels C-E are what it costs and buys. **The vertical is the axis this repairs:
median 3.92 -> 2.71 cm, better on 14 of 16** — a third of the vertical error
against the video was the ruler. The horizontal is untouched, 2.17 -> 2.26 cm
median and `beats_null` 1.25 -> 1.26, which is what P3 predicts: the horizontal
error is not a scale error, so rescaling the referee cannot reach it. **Read the
residual honestly** — the correction removes a COMMON bias and leaves a wider
spread BETWEEN lifts (0.012 -> 0.058), bench now 2.9% low and squat 2.9% high.
If the truth were instead "the IMU reads ~7% high on ROM", this would be
double-counting; the answer to that is that the tape measures the referee's own
geometry directly and the 0.858 never did. Verified as a pure rescale: all 16
seeds are unchanged, every clip moving by exactly its lift's factor, so the
before/after is like-for-like. *Two defects found in passing and recorded in
TASKS.md H14: `tracked.ensure(force=True)` never re-tracked, and `run.py`'s
clip list globs `data_v2/video` twice.*

## 68 — every set in the corpus, on one page (H17, 2026-08-17)

`68_corpus_scorecard.png`, from `analysis/68_corpus_scorecard.py`. All 29
captures scored as the pipeline ships — step 6 on, H14's tape scale, B4's
derived sign — with the five singles routed through `shortset.run` as G3 does.
**27 of 29 are scored**; the two 2026-08-13 spoto benches are not, because their
footage does not track. The script caches its sweep to
`68_corpus_scorecard.json`; `--cache` re-renders from it in a second.

**Panel A is the headline and it is a lift split, not a capture split.** Bench
beats the flat-line null on 6 of 7, squat on 9 of 10, deadlift on **1 of 10**.
The one deadlift that wins is `deadlift_200x1`, a single — every multi-rep
deadlift in the corpus loses. That is P2 restated on the whole corpus at once,
and it is better than the 0.14–0.38 `FINDINGS.md` records for deadlift (now
0.19–0.93) because `d`, H14's scale and B4's sign have all landed since.

**Panel B is new, and the reason to care about it is that no video enters it.**
Mean concentric velocity against bar load, one point per set, from **rep 1** so
within-set fatigue cannot confound it. Heavier bar, slower bar is the most
robust relationship in strength training, and it is an external check the IMU
can be held to with no camera, no tracker and no sync — the first such check in
this project that does not route through `vtrack`. Bench **r = −0.92**
(p = 0.0004), deadlift **r = −0.91** (p = 0.0006), squat −0.55 (p = 0.10, n.s.).

The fatigue control is what makes it a measurement rather than a coincidence,
and it was predicted before it was run. On the set-median MCV the fits are
−0.77 / −0.93 / −0.18; taking rep 1 instead moves bench to −0.92 and squat to
−0.55 while **deadlift barely moves** (−0.93 → −0.91). Panel C says why: the
deadlift is the lift whose MCV does not decay within a set (median −2.4%, where
bench sheds −26%), so it had nothing for the control to remove. Squat stays
weakest and its confound is visible in the table — its two 170 kg points are
singles, taken fresh, against x4 medians below them.

**The contrast between A and B is the finding.** Deadlift has the best velocity
channel in the corpus and the worst horizontal position channel, on the same
captures, the same sensor and the same nine steps. So P2's deadlift failure is
specific to fore-aft POSITION — it is not the sensor, the attitude, or vertical
integration in general. P6 and C11 reached that from the momentum side; this
reaches it from a direction that never touches the video.

**Test-retest, free from three repeated set specs.** `bench_spoto_95x5_1`,
`bench_spoto_95x5_2` and `squat_170x1` were each performed twice, a week apart.
Rep-1 MCV agrees to **4.6% / 0.7% / 0.6%** and median ROM to 7.4% / 2.3% / 1.9%.
Note where two of those three sit: the 2026-08-13 spoto benches are exactly the
captures with no video score at all, so the velocity channel returns a sane and
repeatable number on captures the referee cannot grade. **n = 3, and identical
load is not identical effort** — suggestive, not decisive.

**Panel D is the red list: 7 cells over 6 captures, 23 of 29 fully clean.**
Three rep-count misses (`deadlift_210x1` 2/1, `squat_140x4_1` 3/4,
`squat_140x4_2` 2/4 — P1, reopened by H15), two ROM-band failures
(`deadlift_170x4_3`, and `deadlift_210x1` as a consequence of its miscount) and
the two untrackable clips. Panel E is the sobering one: **not one capture is
inside the 1 cm horizontal spec**, the best being `bench_117.5x1` at 1.08 cm.

*One doc correction falls out of this and is recorded rather than acted on.*
CLAUDE.md still calls the IMPACT/SMOOTH fore-aft growth split "the sharpest
lift-level split in the project" on +29.2 %/rep deadlift against +0.3 bench and
+1.9 squat. Measured on this corpus with a fitted per-rep slope it is **+6.6
deadlift, +5.7 bench, −2.1 squat** — overlapping, and deadlift 6 of 8 positive
rather than 6 of 6. **H1 found the same collapse independently** with a
different definition (TASKS.md:630, `H1_STATE.md`: deadlift 1.2–35.0 %/rep
against bench+squat 1.3–22.8, "overlapping completely"). Two measurements, two
definitions, one conclusion, and CLAUDE.md carries none of it.

**H18 then found the cause, and H17's guess above at "corpus turnover" is
WRONG for the deadlift row** (2026-08-17). Re-run with `drift_tilt=False` — the
pipeline as it stood when the table was taken — the deadlift compounding
reproduces at **+21.5 %/rep, 8 of 8 positive**, and `deadlift_160x6_1` returns
to the recorded shape. **Step 5b removes it**, which is what 5b is for. So the
original measurement was sound and the pipeline moved under it; the statistic
stopped separating because the defect was fixed, not because it was noise. The
smooth rows do not reproduce either way, so corpus turnover is the right
explanation only for those. Full argument and the circularity caveat in
`FINDINGS.md` H18 and its Part 5, IMPACT/SMOOTH.

## 69 — fixes for the deadlift horizontal, explored (H19, 2026-08-18)

`69_deadlift_fixes.png`, from `analysis/69_deadlift_fixes.py`. Measurement only,
no `src/` module written. Full argument in `analysis/H19_STATE.md`.

**Closes `C31b_STATE.md` item B, open since 2026-08-06.** C29's rest-to-rest
window + impact correction was measured with step 6 OFF and before H8's step 5b
existed, and 5b also removes a drift-shaped error — so either 5b had already
taken what C29 was taking, or they compose. **They compose, and C29 is worth
MORE after 5b than before it:** median deadlift horizontal, all arms on
identical windows, control 9.34 cm -> C29 with 5b off 4.08 -> C29 with 5b on
**2.88**, `beats_null` 0.21 -> 0.83. Inside its own frame the correction is
better on **10 of 10** captures, paired Wilcoxon **p = 0.002**, and four
captures cross `beats_null = 1.0` — which no multi-rep deadlift has done.

**And it still cannot ship, now for a measured reason rather than an untested
one.** Against the shipping pipeline the median goes 3.31 -> 2.88 cm, better on
**7 of 10** — nominally significant on a paired magnitude test (Wilcoxon
**p = 0.049**) and not on the sign test (p = 0.34). *That verdict moved during
the task:* at the eight deadlifts held that morning it was 5 of 8, **p = 0.195**,
and two captures arriving at 14:03 carried it across the line on their own. Ten
cannot settle it any more than eight could. Two confounds sit on the comparison
and they pull in OPPOSITE directions, so both have to be quoted. The rest-to-rest
frame scores **30 of 46 reps** — pairing consecutive rests gives n-1 windows from
n impacts, so rep 1 is never scored and `deadlift_185x3` falls to a single rep —
and its windows carry a **27% larger null** (larger on 9 of 10). The
bigger null *flatters* `beats_null`, whose numerator it is (C12's shape), while
*penalising* the raw `h_rms` comparison, because those windows hold 27% more
real fore-aft travel to get right.

Three sub-results worth not repeating. Recovering the lost rep by prepending the
segmenter's own first-rep start **fails**, worse on 5 of 5 (`160x4_2` 1.64 ->
4.66): the bar starts dead on the floor there and the window carries the setup.
Decoupling "detrend windows" from "rep windows" **cannot be built**, because C29
itself established that step 7 is load-bearing through per-rep INDEPENDENCE, so
the detrended position is only defined piecewise inside its own windows. And the
rep-1 selection effect, which could have explained the whole gain, **runs the
other way**: rep 1 beats its set average on 3 of 5, and dropping it makes
SHIPPING worse on 3 of 5.

Finally, C29 is **not** D1's degenerate case. D1 was rejected for converting
every capture into approximately the null (`beats_null` 0.13-5.39 -> 0.76-1.16);
under C29 the spread *widens*, 0.19-0.93 -> 0.48-1.65. It is adding information
rather than deleting a channel. Two implementation notes: pass
`axes=(0, 1, 2)`, since the default `(0, 1)` leaves vertical rms at 5.83 cm
against shipping's 2.88, and the width has an interior optimum at 0.20-0.40 s
that degrades sharply beyond it (0.60 s 3.59 cm, `width_s=None` — C28b's
rejected whole-interval spread — 4.41), so the correction is genuinely local.

**Two deadlifts arrived mid-task, taking the corpus to 31** (`CLAUDE.md` still
says 29): `deadlift_160x6_1_20260818` and `deadlift_190x3_20260818`, both
tracking cleanly at 99.8%/99.7% coverage with rep counts matching their names.
**The first reconstructs at 14.91 cm, the worst horizontal in the corpus, where
the same lift/load/reps on 2026-08-04 gives 1.97** — a 7.6x session-to-session
difference on a clean track, which is H17's velocity-repeats/position-does-not
split showing up inside a single set spec. Not explained. **Explained the same
day by the owner and measured in `70` — he wore straps. See below.**

---

## 70 — the owner's straps hypothesis, tested (H20, 2026-08-18)

`70_straps_hypothesis.py`, `--cache` to re-render from the JSON beside it.

`69` left the 7.6x gap on `deadlift_160x6_1_20260818` unexplained. The owner
then supplied what no measurement here could: **he wore straps for it**, putting
the watch further up the forearm and letting it move. Six panels, because the
phrasing contains two hypotheses that make different predictions and only one
survives.

**Straps are a per-CAPTURE fact.** `160x6_1_20260818` is the only strapped
deadlift in the corpus; `190x3_20260818` was shot the same day on the same rig
without them, which makes it a **within-day control**. An earlier version of
this entry read the two as a session effect, and the owner corrected it — the
control is what makes the comparison strong, so the correction improved the
result rather than weakening it.

* **A — one capture, not one session.** The strapped capture at 14.91 cm; its
  same-day unstrapped control at 7.22; everything else 1.76–3.90.
* **F — video-free corroboration.** The RAW pre-detrend integration runs away:
  831 → 2744 cm across the strapped set against 150 → 579 on its own twin, and
  highest of any deadlift at *every* rep index including the first.
* **B — a longer lever is FALSIFIED.** 15 cm of displacement buys `160x6_1` 6%,
  makes the control worse, and helps the *unstrapped* `185x3_20260804` most.
* **C — the fitted roll is DISCOUNTED by the control.** Both 2026-08-18 captures
  minimise at ≈ −50°, ~73° from the shipped `BAR_ANGLE_DEG`. If that were a
  strap effect the unstrapped control would not share it, and it does — so it is
  one parameter fitted against the answer. Read panel D instead.
* **D — the same roll, measured with no video in it.** From the gyro: the hand
  is clamped to the bar, so the dominant direction of body-frame angular
  velocity is the bar's axis. `160x6_1_20260818` sits ~20° off the −3…+8°
  cluster every other well-conditioned capture occupies. Real, predicted
  direction, worth 6%. **The X markers are ill-conditioned and must not be
  read** — one of them is unstrapped.
* **E — the discriminator.** Per-rep horizontal spread, **axis-free**: the
  strapped capture sweeps 19.9–27.9 cm, its own twin 5.4–7.7, its same-day
  unstrapped control 6.9–12.0, and the bar moved 4.4–6.0. A rotation cannot
  create that, so the excess is real motion in the reconstruction. Grey X marks
  two captures already known bad for unrelated reasons, which sweep as much or
  more — so the claim is that the strapped capture is the only CLEAN one
  inventing this much travel, not that it is the highest.

**Verdict: the watch was MOVING, not merely repositioned** — P6's strap-ringing
mechanism escaping the floor impact and contaminating a whole set. Does not
close: the unstrapped control is itself elevated at 7.22 cm with no invented
travel and ordinary raw drift, and straps do not explain it. See TASKS.md H20.

---

## 72 — the deadlift impulse: a pre-pull rest anchor (H22, 2026-08-19)

`72_deadlift_rest_anchor.py`, with its `.json` committed beside it. Owner's
task: use the impulse, or overlap the reps to find a rest period; the bounces
decay and the watch barely moves during the ringing. **One of the three works.**

*n* = 8 deadlifts, 36 reps. Three excluded by hand and named every time:
`160x6_1_20260818` (straps, H20), `170x4_3` (22.8% clock drift, G3),
`210x1_20260815` (miscounts a single, H15).

* **A — one landing in full.** The bounces decay (median peak ratio 0.83, 13-26
  peaks, settle 0.61 s) and a ~1 s rest PERIOD follows the single sample
  `segment.rest_instants` returns.
* **A2 — the reconstruction claims ~1 m/s of horizontal velocity while the bar
  is provably flat on the floor.** Visible with no video in the frame.
* **B — the anchor C29's frame was missing exists**, and is quieter than every
  rest that frame already uses, on **9 of 9** deadlifts (0.04-0.71 against
  0.17-7.15).
* **C — the coverage blocker, closed.** 23 of 36 reps -> 31. Shipping 2.78 cm
  (`beats_null` 0.68) · C29 2.00 (0.95, 23 reps, null inflated 1.28x) ·
  **H22 period frame + period-averaged dv 2.14 (0.84, 31 reps, null 0.97x)**.
  H19's null-inflation confound is REMOVED rather than inherited, so 0.68 ->
  0.84 is like-for-like where C29's 0.68 -> 0.95 was not.
* **D — neither change helps alone** (2.98 / 2.70 / 2.98 / 2.14). C29's own
  shape again.
* **E — "the watch barely moves during the ringing" CANNOT be spent.** Zero net
  displacement 11.30 cm, clamped horizontal velocity 4.76, against C29's 2.00.
  Step 7 already absorbs a constant velocity error exactly, so the absolute
  statement is invisible to the metric; imposing it inside one window
  manufactures a kink, which is the shape C29 exists to remove. The window also
  starts at impact ONSET, where the bar is still moving at 0.4-1.0 m/s.
* **F — the decay buys nothing.** A per-landing adaptive width gives 2.17
  against 2.14 for a flat constant.

**Overlapping the windows loses at every width** (2.93 against 2.14) — it breaks
the per-rep INDEPENDENCE C29 showed is load-bearing. And the **last** rep of a
set can never get a rest-to-rest window, because the lifter releases the bar;
three independent detectors agree, and it is gated.

Recommendation: `oracle.jump_period_windows` supersedes `jump_rest_windows` as
the best deadlift candidate, on coverage and the removed confound rather than on
accuracy, which is within noise. **Ship neither.** See TASKS.md H22 and
`analysis/H22_STATE.md`.

---

## 73 — the owner's final cut: covering the last rep (H24, 2026-08-19)

`73_final_cut.py`, `--cache` to re-render. H23 ruled that no correction may drop
a rep, which closed C29's and H22's rest-to-rest frame. The owner's proposal
dissolves it: use the rest boundaries for every rep but the last, and close the
last window just BEFORE its impact.

* **A — coverage**, the requirement H23 added, measured in reps SCORED.
  Shipping 36/36, H22 31/36, **the cut 36/36**.
* **B — per capture.** It also rescues the two captures H22 made worse
  (155x5_1 4.73 -> 3.56, 160x4_2 4.16 -> 1.90), because the cut applies on every
  set rather than only where a rest was missing.
* **C — `cut_s` is a plateau**, flat from 0.02 to 0.30 s. The bar's fore-aft
  barely moves in the last fraction of a second of descent, so where exactly the
  cut falls does not matter. Not a tuned constant, and gated.
* **D — the scoreboard.** 2.03 cm against shipping's 2.78, `beats_null` 0.77
  against 0.68, better on 7 of 8, paired Wilcoxon p = 0.078, and **null vs
  shipping 1.00** — like-for-like, where C29 and H22 both inflated it.

**Still 0.77, so still worse than a flat vertical line, and p = 0.078 is not
significance.** First frame to satisfy all three standing requirements at once;
not an arrival, and nothing is proposed for the pipeline. See TASKS.md H24.

---

## 74 — the bar paths under the final cut, and the cost H24 missed (H24b, 2026-08-19)

`74_final_cut_paths.py`. The owner asked to see the bar paths for H24. Every
curve is `metrics.vs_truth`'s own paired `curve_video` / `curve_pipeline`, so
the figure invents no alignment; thin is every rep, bold is the arm's mean, and
a **red halo** marks a rep outside `capture.VERTICAL_ROM_M`.

**Drawing them caught a real cost H24 never measured.** H24 was scored on the
horizontal alone. The first reps come out visibly tall and distorted, and the
measurement confirms it: vertical rms goes from shipping's **2.88 cm** — inside
the ±2–3 cm spec, 0 of 36 reps out of band — to **4.03** (H22) and **5.15**
(with the cut), 9 of 31 and 6 of 36 out of band, with reps of 70–79 cm on a lift
whose range is 40–61.

**The cost is inherited from the rest-to-rest frame, not caused by the cut** —
the first rep's ROM is identical under both (78.3/78.3, 75.2/75.2, 79.2/79.2),
so it belongs to H22's pre-pull anchor, and the cut *reduces* the out-of-band
fraction from 29% to 17%. The bottom row shows the trade on both axes.

So the frame is a **trade, not a win**. The coverage requirement H23 added is
still met, 36 of 36, and the cut is what meets it. See TASKS.md H24.

---

## 75 — where the horizontal acceleration error comes from (H25, 2026-08-19)

`75_horizontal_closure.py`. C11's closure identity — between two instants the
bar is known to be still, the integral of its acceleration must be zero — run on
the **horizontal** for the first time. Nothing tunable in it, and a video scale
error cannot move a zero crossing, so the video says only WHEN the bar was still.

* **A — the horizontal.** deadlift pull 0.144 m/s, deadlift with impact 0.256,
  bench 0.031, squat 0.070. **The impact DOUBLES the error and does not create
  it**, and a deadlift pull alone already carries 2-3x bench's.
* **B — the same intervals, vertical.** C11's shape, on today's corpus: the
  landing dominates at 2.7x the pulls. **C11's -0.589 was the v1 corpus, now
  deleted; today it is -0.126.** The panel reproduces `metrics.momentum_closure`
  exactly (n = 15 and 24), which is how the non-reproduction was caught.
* **C — why it is fatal here and nowhere else.** The same errors as mean
  acceleration, against the bar's real 0.13-0.21 m/s² horizontal, labelled with
  the attitude tilt that would leak that much gravity: 0.13° on bench and squat
  against **C6's independently measured 0.05-0.14°**.

So the horizontal error is about half impact and about half gravity leaking
through attitude, and the pause cannot remove either — two still instants give
two numbers, and step 7's line already spends both. See TASKS.md H25.

## 76 — three priors on the remaining horizontal error (H26, 2026-08-19)

`76_horizontal_priors.png`. The owner picked three of seven candidate priors
after H25 and asked for **measurement first, with no correction built**. Nothing
in `src/` changed. Same interval set as `analysis/75` — moments the video says
the bar was still, so the closure identity supplies the error with nothing
tunable in it. `deadlift_160x6_1_20260818` excluded by hand (straps, H20).

* **A — PRIOR 1, the lockout as a second, impact-free anchor. SURVIVES.** The
  pull-only horizontal error is **negative on 9 of 9 captures** (sign test
  p = 0.002) across three sessions, 150-190 kg and both camera sides, with
  direction coherence 0.83-0.99 against a random null of ~0.60. As a tilt that
  is 0.09-0.91°, median 0.43 — the size H25 predicted and the size C6 measured
  at still holds. A standing tilt, not noise. **And step 5b does not remove it:**
  under the attitude the pipeline SHIPS it is still negative on 9 of 9, at 55%
  of the raw magnitude (0.06-0.41°, median 0.23). 5b fits a RATE; this is an
  OFFSET. That check is what makes the prior live rather than a description of
  an error already corrected.
* **B — PRIOR 1, one cause or two?** The pull error does not predict the same
  rep's landing error: Spearman **r = +0.06, p = 0.83, n = 15**. Two causes. So
  the one number per rest-to-rest interval that C28b, C29, H22 and H24 all fit
  is absorbing both, and cannot.
* **C — PRIOR 2, excise the ring rather than compensate.** Not "what fraction of
  the error is inside the ring" — the interval's net partly cancels, so that
  ratio exceeds 100% and means nothing, which a first version of this got wrong.
  What the closure error BECOMES when those samples are removed: horizontal
  **0.256 -> 0.153 m/s, better on 15 of 24**; vertical **0.128 -> 0.653, better
  on 1 of 24**. Licensed on one axis, forbidden on the other, because the
  vertical impulse is real (B5, ratio 1.04).
* **D — PRIOR 4, does the tilt track acceleration? DEAD where proposed.**
  Correlated within H25's four INTERVAL CLASSES, so neither the lift nor the
  impact is the confound. In the PULL class nothing reaches |r| = 0.15 and every
  p is above 0.5. It correlates only on the LANDING (+0.45..+0.56), where the
  mechanism is P6's strap ringing and already known.

Two of three survive and point the same way: a standing tilt of ~0.4°, one
direction, on every deadlift, independent of the rep's vigour and of the landing
error. **The coverage caveat is what stops it being buildable today** — only 15
of 39 intervals carry a lockout dwell, so H23's cover-every-rep requirement is
not met per rep. See TASKS.md H26.

## 77 — the per-set tilt correction, built and measured (H27, 2026-08-20)

`77_pull_tilt.png`. The owner asked for H26's prior 1 to be BUILT. It is
(`oracle.pull_intervals`, `pull_tilt`, `pull_tilt_correction`) and **it loses on
7 of 8 deadlifts in every variant.** Kept for the mechanism.

* **A — every variant loses.** Median horizontal rms: shipping 2.78 cm; per-SET
  constant from IMU anchors 5.01; per-SET from VIDEO anchors 5.18; per-REP 5.00;
  in-span-only 3.54. Better than shipping on 1, 1, 1 and 2 of 8 respectively.
* **B — `beats_null` 0.68 -> 0.33**, paired Wilcoxon p = 0.078. The null is
  UNCHANGED because the arm keeps shipping's windows, so unlike C29 and H22 this
  is like-for-like with nothing to discount. Reps scored is 36 of 36 in every
  arm, vertical rms 2.88 cm in every arm, reps outside the 40-61 cm ROM band
  0 of 36 in every arm. **Not H24b's failure shape** — nothing was traded.
* **C — why, and the arithmetic says so in advance.** Step 7 removes a LINE per
  rep; a constant acceleration error is QUADRATIC in position, leaving a
  parabola of sagitta `a·T²/8` — **1.2 to 12.9 cm, median 8.0** for the measured
  tilt. Shipping's whole horizontal error is 2.78 cm, so the error is not that
  constant, and subtracting it injects a parabola that was never there.
* **D — a MEAN is not a SHAPE.** The same closure identity over the WHOLE rep
  gives 0.199 m/s², **4.1x the pull's**, and a uniform constant of that size
  would leave ~30 cm. Neither is a constant: the error is concentrated in time
  (H25's impact), which has a large mean and a small double integral.

So this is C28's *"not a constant in ANY frame"* reached from a new direction,
without fitting anything against the video. H26's measurements stand; the
inference that a systematically-signed mean is a uniform error does not.
See TASKS.md H27.

---

## `78_set_paths_<lift>.png` — every set, reconstruction against video (H28, 2026-08-20)

`python analysis/78_set_paths.py`. Three figures, one per lift. One ROW per
set: the leftmost panel is the set's AVERAGE rep, reconstruction against video,
and the panels to its right are its individual reps, same comparison. Black is
the bar as `vtrack` saw it, blue is the pipeline, ORANGE is the rep the display
would flag as the odd one.

**32 of the 36 captures, 124 reps.** It uses `shortset.run` rather than
`pipeline.run` — identical on three reps or more, and the only way the singles
score at all (G3). Through the plain pipeline coverage is 27 sets.

Nothing here is a new measurement: every curve is `metrics.vs_truth`'s own
`curve_video` / `curve_pipeline`, already paired and aligned by the scoring
path. Two choices are taken from H13 rather than by preference — the average is
aligned by **turnaround** (that alignment is where the whole averaging gain
lives, vertical 8.30 -> 3.00 cm) and the odd rep is **labelled, not excluded**
(excluding it makes the average worse, 1.52 -> 1.70).

**Why both halves are on the same row.** A tidy average over four scattered reps
and a tidy average over four tight ones are indistinguishable in the left-hand
panel. The product would draw only that panel; the reps beside it are what it
is hiding.

What it shows at a glance:

* **13 of 32 sets lose to the flat-line null**, drawn rather than tabulated —
  every deadlift except `deadlift_200x1`, plus `bench_spoto_95x5_2_20260806` and
  `squat_145x4_2_20260817`. H17's scorecard, visible.
* **The strapped capture is unmistakable.** `deadlift_160x6_1_20260818` sweeps
  ~20 cm of fore-aft on every rep against a video path that is nearly flat —
  H20's finding as a picture. It is drawn and labelled rather than dropped,
  because hiding it would misrepresent the corpus and dropping it silently would
  misrepresent the median.
* **`deadlift_210x1_20260815` gives two reps for a labelled single** at
  h 20.64 / v 37.74 cm — H15's open miscount, now visible as a shape.
* The five captures of 2026-08-20 are the corpus's best-conditioned:
  `squat_pause_140x4_1` at h 1.15 cm / `beats_null` 4.44 and
  `bench_spoto_80x5_1` at 1.14 cm / 3.71.

Six captures no longer have a `.mov` on disk; all six have a committed tracked
path, so the script pairs a capture to its clip through `data_v2/tracked/`
rather than through `pipeline.find_video`, which requires the file to exist.

---

## 79 — the endcap as a tilt sensor, and the bar centre (H30, 2026-08-22)

### `79_endcap_parallax.png`

The owner's task: *"You currently have 8 markers on the plate along with 1 on
the endcap, from this we can remove tilt to find the barpath of the centre of
the bar by looking at the orientation and parallax between the end cap and the
8 point conic."* Measured, not built. `src/vtrack/geometry.py` holds the
conversion the answer would feed; nothing in `src/` applies it.

**The conversion is one term, and the geometry is the easy half.** The sticker
circle and the bar centre are separated purely ALONG the bar, and both reported
quantities are perpendicular to it, so a level bar needs no conversion at all.
The whole difference is `L * sin(theta)` and the whole difficulty is `theta`.

**Of the owner's two cues, one is unusable in principle.** A circle tilted by
theta projects to an ellipse of aspect cos(theta), which at the 1-3 degrees a
barbell tilts is 0.01-0.11 px on an 85 px radius. The conic's orientation is
second order in the angle and no footage fixes that. Only the endcap parallax,
which is first order, carries signal.

**The endcap offset is real and large — and it is 81-96% perspective.** The
endcap sits nearer the camera than the sticker plane, so it projects displaced
from the principal point in proportion to where the bar is in frame, and the bar
crosses most of the frame every rep. The top row of the figure is that
correlation, and it is visibly CURVED, which is the point of the middle row.

    capture                        offset sd   after plane   after quadratic
    deadlift_160x6_2_20260804        10.20        3.07            2.00
    squat_pause_140x4_2_20260806     11.64        3.22            2.74
    bench_spoto_95x5_1_20260806      12.86        3.89            2.44

px. **The residual is still shrinking as the perspective model improves**, and
the deadlift's lag-1 autocorrelation fell 0.51 -> 0.32 as it did — so what the
plane left behind was substantially the plane's own rep-periodic error, which
is precisely the error class the spec says does not cancel rep-to-rep.

So the result is a BOUND and not a measurement. `geometry.lever_ratio` magnifies
an endcap error by 2.0-3.7 on its way to the bar centre, giving **1.1-1.7 cm
against a ~1 cm spec**. Bar tilt contributes at most that and possibly far less.
That is worth having on its own — `src/tracked.py` has named bar tilt as an
error source since C31 without anyone sizing it — but a correction fitted to a
residual that shrinks every time the model improves would be putting the
model's own error into the bar path.

**What would change it**, cheapest first: the footage is 360x640, so 1080p cuts
every figure by ~3x and puts the bound at 0.4-0.6 cm; marking the FAR plate,
currently bare, turns a 0.185-0.375 m tilt baseline into 1.73 m and makes the
lever ratio less than one; a checkerboard calibration replaces the fitted
polynomial with the real projection.

## 80 — conditioning the video referee (H30, 2026-08-22)

### `80_video_conditioning.png`

The owner's task: *"Video path should be smoothed slightly rather than being so
jagged, furthermore any anomalous data entries should be removed."* Built as
`src/vtrack/condition.py` and ON by default in `vtrack.bar_path`.

**Smoothing was the ask; the anomalies were the problem.** Four of the 36
committed tracks held on 2026-08-22 contained frames implying motion faster than
free fall, and only two of them were flagged by anything. `IMPLAUSIBLE_FRAC`/`IMPLAUSIBLE_MULT` test
whole-clip travel, which cannot see one bad frame inside a sound track:

    squat_pause_140x4_3_20260806   frame 128 reads 0.399 m between neighbours
                                   at 0.663 — 26 cm out and back in 33 ms —
                                   inside a clip whose 71.6 cm travel passes
                                   the 61-68 cm band comfortably
    deadlift_150x4_1_20260808      peaks at 6.99 m/s downward against free
                                   fall's 5.05, and is the capture TASKS.md
                                   already records for segmenting 5 reps
                                   against a labelled and confirmed 4

Both are repaired and keep their clip. The two 2026-08-13 benches fail 2.2% and
10.0% of frames on speed and are **condemned rather than repaired** — a smooth
path that is not the bar is worse than a visibly broken one, because the visible
wrongness is what makes the failure findable.

**The owner then deleted those two captures, agreeing with the condemnation
(H31, 2026-08-22), so the corpus is 34 and nothing in it is condemned.** The
table above is kept as measured, because it is what `V_MAX_MS` was derived from.
Its live consequence is that no gate can be pinned to a real broken track any
more, which is why `tests/test_vtrack.py` builds one.

**The gate is that the measurement did not move.** Smoothing invites one silent
failure: clipping the turnarounds, which shrinks range of motion and rescales
every vertical figure in the repo with nothing complaining. Savitzky-Golay at
order 2 reproduces a parabola exactly and a turnaround is locally parabolic, so
it should not, and over the 34 non-condemned captures travel changes by a median
of **-0.004 cm and at most 0.27 cm** against a +-2-3 cm spec. 121 frames of
39,988 are rejected, 0.30%.

**The two condemned captures were deleted by the owner the same day (H31) and
the figure still shows them**, as hollow crosses carried in the script's
`DELETED` table with their measured peaks. Freezing the PNG would have made it
un-reproducible from its own script, and re-rendering without them would leave
`V_MAX_MS` looking arbitrary — the whole case for the cut is that it sits in a
gap those two define. The counts in the lower-right panel are the live 34.

**`V_MAX_MS = 5.0` is derived rather than tuned** — free fall from a 1.3 m
lockout is 5.05 m/s. The clean captures peak at 2.68 vertical / 4.02 horizontal
and the suspects at 6.99, 7.94, 12.98 and 20.61, so the cut sits 24% above the
worst clean figure and 28% below the worst suspect. The top-right panel is that
separation on log axes.

A robust per-clip cut on the fit residual was tried first and **was wrong**: at
6 MADs it rejected 92 frames of `squat_140x4_1` and condemned 18 of 36
captures, because the residual distribution is heavy-tailed by nature — the
marker subtends fewer pixels at lockout, which `path.top_of_travel_residual`
documents. The shipped cut is absolute, 2.0 cm of implied position error, four
times `path.MAX_TOP_RESIDUAL_CM`.

---

## 81 — the rep gallery (H33, 2026-08-23)

### `rep_gallery.html`

The owner: *"keep live graphs of each set and rep for both video and data ran
through the most recent pipeline and video tracking so I can sanity check."*
A self-contained page — one card per capture, the whole set overlaid, then every
rep as a small multiple with the video and the reconstruction on a shared axis
and a shared sign. **Regenerate it after any pipeline or tracker change**; it
reads the live `pipeline.run` and the committed tracked CSVs, so it is only as
current as its last run. 34 captures, 117 refereed reps, ~450 kB.

Not another PNG because `78_set_paths_*.png` already draws every set, and what
it cannot do is take you from "this set looks wrong" to "this rep" without
opening a second file. Every panel is scaled to fit, so panels are not
comparable by eye — the numbers under them are, and the caption on the page says
so.

## 82 — why five captures miscount (H33, 2026-08-23)

### `82_segmentation_deepdive.png`

Two mechanisms, and **neither is the one `TASKS.md` recorded**.

**The cluster discards reps it has already identified.** On the three squats
that undercount, all four reps are present as concentric lobes and the upright
ratio separates them from everything else by ten times — 9.5–16.8 against
0.7–1.3. `_upright` drops none of them; `peak_ratio` is never reached, since
peak speed declines only 1.36× across a set against a 2.5× limit.
`_similar_cluster` is what excludes them.

**The "long cadence gap" explanation is falsified.** Last gap over first:

    PASSES  squat_155x4_3 1.68   squat_pause_140x4_3 1.59   squat_pause_140x4_2 1.53
    FAILS   squat_140x4_1 1.54   squat_140x4_2 1.42   squat_pause_140x4_1 1.27

The most irregular set counts correctly and the worst failure is the least
irregular of the six.

**A spurious pair outvotes a real single.** Both 2-for-1 captures pick a
mutually-similar pair from the setup over a real rep that is a cluster of one —
`squat_170x1_20260820` at 4.40 s + 8.71 s over the rep at 33.69 s, and
`deadlift_210x1` at 13.22 + 20.38 over a pull at 24.80 s with the largest area
and peak velocity in the capture. `_similar_cluster`'s singleton rule was
written for exactly this and never fires: it guards a winning cluster of size 1,
and the winner here has size 2.

**A lead, not a fix.** Cutting the sorted upright ratios at their largest
multiplicative gap — an argmax, not a threshold — gives bench 9/9 and squat
12/13 on the velocity path against shipping's 9/9 and 9/13, and costs
`deadlift_200x1`. Nothing is proposed for `src/`.

## 83 — reps do not close, and correcting that is worth nothing (H33, 2026-08-23)

### `83_nonclosure.png`

The owner: *"the assumption that reps start and end in the same place is
disproven by the video tracking."* Confirmed, and then followed through.

**The premise holds and is stronger than B3 recorded.** Median horizontal
non-closure over 111 refereed reps is **1.61 cm** against a ~1 cm spec; only 33%
of reps close inside spec; the miss is 19–28% of the rep's own fore-aft
excursion. Forcing it shut injects ~0.9 cm rms, roughly half the typical 2.4 cm
error.

**But the detrend is not mainly destroying it.** Per-rep net displacement,
median absolute: the reconstruction carries 50 cm (bench) to 454 cm (deadlift)
of it against 1.4–1.8 cm of real motion, so **97–100% of what step 7 removes is
integration drift**. And the two do not correlate (r = −0.13 to +0.08), so no
estimator of the true non-closure can be built from the reconstruction's own.

**The result that decides it — the oracle gains nothing.** Re-detrend each rep
to close on the video's true net displacement instead of zero:

    lift       shipped   closed   ORACLE    gain
    bench        2.08     2.08     1.93    +0.15
    deadlift     3.11     3.11     2.78    +0.33
    squat        2.58     2.58     3.19    -0.61
    ALL          2.40     2.40     2.58    -0.18

Better on 50% of 111 reps. (`closed` re-derives the shipped figure as a control
and matches it exactly.) The endpoint is not where the error lives — P3 puts it
at rep frequency, distributed through the rep, and correcting one endpoint
pivots the curve about its start.

**One thing worth carrying:** the non-closure is a different animal per lift.
Sign-consistency within a set, against the ~1/√n of a coin flip — **deadlift
0.20 against chance 0.49**, below chance, the misses actively cancel and the set
total is +0.44 cm at p = 0.65. A deadlift set closes even though its reps do
not. Bench (0.54) and squat (0.73) walk, both the same direction, −3 to −5 cm
per set at p = 0.05–0.10. n = 7–9 sets, so suggestive only.

---

## 84 — where the rep error lives, and why two corrections missed it (H34, 2026-08-23)

### `84_error_phase.png`

The follow-on from 83: if the endpoint is not where the error is, where is it?

**A bulge at mid-rep.** Horizontal error against phase, rms cm — 0.00, 3.68,
3.53, 4.17, **4.96**, 4.92, 4.11, 3.38, 2.27 across phases 0 to 1. Peak at 0.56,
and the endpoint carries only 45% of it. That is the whole explanation of 83's
null result: step 7 acts where the error is smallest.

**An oracle ladder over polynomial order** — best per-rep fit against the video,
so a ceiling and never a proposal:

    lift        ships   ord 0   ord 1   ord 2   ord 3   ord 4
    bench        2.10    1.05    0.98    0.34    0.22    0.17
    deadlift     3.09    1.68    1.47    1.10    0.93    0.55
    squat        2.58    1.87    1.78    0.77    0.67    0.58
    ALL          2.39    1.65    1.37    0.71    0.56    0.39

The jump is order 1 → 2, and 0.71 cm is inside spec. Not a contradiction of
C19: that quadratic was constrained to CLOSE the rep and so could not learn the
bulge. The basis was never the blocker.

**On deadlift the bulge is a constant acceleration error.** A constant `a` over
a rep of duration T leaves a parabola of amplitude a·T²/8 — a prediction with no
free parameters, testable against durations of 2.2–5.8 s:

    lift        Spearman(T, amplitude)   log-log slope   [T² predicts 2.00]
    deadlift      +0.392 (p = 0.014)         +2.08
    bench         +0.288 (p = 0.076)         +1.26
    squat         −0.167 (p = 0.353)         −0.57

Deadlift lands on it, at an implied 0.014 m/s² — inside the 0.011–0.070 P6
measured from acceleration. **Squat does not fit at all**, and squat is also
where 83's closure oracle *hurt* and where the non-closure walks.

**And it diagnoses H27.** Its pull-anchor estimate against what the position
error implies: too large on **9 of 9 deadlifts, median 4.6×, range 1.8–23.8×**.
Right sign on every capture (Spearman +0.32) but n = 9 at p = 0.41, so the gain
cannot be fitted without fitting noise. Applying a real effect at four times its
size is how a correct mechanism produces `beats_null` 0.68 → 0.33.

The granularity is right too: the implied acceleration is stable within a set
(sd/|mean| 0.34–0.60, under 1.0 on 22 of 24) and negative on 22 of 24 set
means — P6's sign result, reproduced from position instead of acceleration.

---

## 85 — a quadratic detrend needs a third constraint (H35, 2026-08-24)

### `85_third_constraint.png`

The owner: *"investigate subtracting a polynomial from the endpoints rather than
a straight line — this will need extra information from somewhere, see what you
can do."*

**The problem is one unknown, not three.** Keeping the endpoints and adding
curvature forces the extra term to vanish at both, so it is `c₂(s²−s)` and
nothing else — and `c₂ = a·T²/2` is exactly a constant acceleration error. It is
worth **2.39 → 1.25 cm** per rep, **1.71 per set**; a global constant is
worthless and makes deadlift worse, because the per-set sign is not fixed within
a lift.

**Four sources tested; all fail.** The pull anchors are 4.6× too large on 9 of
9. Rep dispersion is blocked by construction — a bump identical on every rep is
common-mode in rep phase, leaving only the 42% within-set T² spread, at
r(T², c₂) = +0.45. The opening hold is the right size and uncorrelated per
capture (Spearman −0.04, p = 0.83).

**The turnaround fails structurally, and that is the interesting one.** The
bump's slope vanishes at phase 0.5, and the turnaround is the middle of the
motion by definition — bench 0.57, squat 0.47, deadlift 0.74. Where the bar is
horizontally still (bench 0.20, squat 0.29 of typical) there is no lever; where
there is a lever, deadlift at 0.74, the bar is moving 1.4× its typical speed.
**Every pause the corpus has is at the useless phase.**

**What would work is a capture change.** The IMU's horizontal velocity error at
a still instant is 2.04 cm/s, so a pause cued at phase 0.25 gives σ(c₂) of 1.18×
the signal per rep and **0.59× averaged over four**. A single rep is not enough
and a set is — which suits, since per-set is the right granularity anyway.
Carried into `TASKS.md`'s capture protocol.

---

## 86 — the spare constraint was there all along (H36, 2026-08-24)

### `86_rest_zupt.png`

The owner ruled out 85's recommendation: **the capture must never affect the
set**, so a mid-rep pause is not available. That sent the question back to the
algebra, and the algebra had been read wrong.

**P6 says the two still instants are already spent by step 7's closure. They are
not.** A linear detrend of POSITION shifts VELOCITY by a constant, so it can
match one velocity condition, not two. Closure removes the MEAN of the two
velocity errors; their difference over T is `a` itself, untouched. Verified
symbolically to 1e-16.

**And a deadlift already has both instants** — the bar rests on the floor
between reps. `oracle.rest_observables` has returned the quantity since C28b,
which used it to ZERO the error, i.e. the mean again. Divide by the span
instead and it estimates the bump:

    a_est vs the oracle a   Pearson +0.594 (p = 0.0011), Spearman +0.430
    raw                     3.10 → 8.23 cm    (3.9x too large)
    fitted gain 0.173       3.10 → 2.42 cm
    LEAVE-ONE-CAPTURE-OUT   3.10 → 2.66 cm    better on 48% of reps
    oracle ceiling          3.10 → 1.88 cm

**It survives leave-one-out**, the standard C28's ladder failed, with held-out
gains of 0.157–0.218 on eight of nine captures. The median improves while the
per-rep hit rate is a coin flip — it helps bad reps more than it hurts good
ones.

**The gain of ~0.17 is the open question.** Not span bookkeeping (span/T =
1.00). Either the interval contains the floor impact, whose impulse is not a
constant acceleration, or the watch's posture at rest differs from under load.
Bench and squat cannot do this at all: a bar descending at constant velocity
reads |a| = g with a quiet gyro exactly as a bar at rest does.

---

## 87 — the 0.17 explained (H37, 2026-08-24)

### `87_the_gain.png`

H36 needed a gain of 0.173 to make the rest-ZUPT estimator usable and could not
say what it was. It is the **least-squares attenuation of a noisy predictor**,
and the identity reproduces it exactly:

    sd(a_oracle) 0.0261    sd(a_est) 0.0895    Pearson r +0.594
    predicted r*sd_o/sd_e  +0.173
    measured OLS slope     +0.173

So it is not a physical scaling and not a fudge — it is the correct shrinkage,
and `r² = 0.35` restates the question as what the other 65% of `a_est` is.

**Not the rest anchors.** `rest_instants` is validated at |v| < 0.10 m/s, but
measured against video at the 35 instants the corpus holds, the bar's real speed
there is a median **0.0168 m/s** — 0.2× the signal.

**Not removable by excising the impact**, and the attempt inverts the suspicion:

    estimator                 sd       r vs oracle    p
    rest-to-rest (H36)      0.0895      +0.594      0.0011
    pull only, pre-impact   0.0881      +0.200      0.32
    post-ring only          0.4304      -0.164      0.41
    ring EXCISED            0.1010      +0.050      0.80

**Only the full interval brackets two instants where the true velocity is
zero**, which is the entire validity of the measurement. A sub-interval ending
at the impact does not — the bar is genuinely moving there, so its `dv` mixes
real motion with error and measures neither.

**The landing and the tilt covary.** The ring's own dv explains 47% of `a_est`
(r = +0.684, p = 0.0001) and is itself correlated with the bump (r = +0.421),
while explaining none of the residual (r = −0.018). A larger tilt inflates both,
because the impulse is measured in the same tilted frame — so "constant
acceleration plus impulse" is not a decomposition this data supports.

The leverage is entirely in reducing `sd(a_est)`. Averaging over a set was tried
and loses, because the oracle `a` genuinely varies rep to rep.

---

## 88 — the ceiling on a one-number correction, per lift (H38, 2026-08-24)

### `88_dwell_average.png`

H37 put all the leverage in reducing `sd(a_est)`. This tried the obvious way,
found it does not work, and the reason sets a hard ceiling and inverts which
lift the whole approach should be aimed at.

**Averaging the rest velocity does nothing.** `rest_observables` samples a
single index at each rest; averaging over a window either side should cut white
noise by √n. A 0.5 s window moves `sd` by 1% and `r` from +0.594 to +0.614,
where white noise would have cut it fivefold. **So the 65% that does not map to
the bump is structure, not noise.**

**Why: the acceleration error is not constant across a rep.** After closure the
error vanishes at both endpoints, so its natural basis is `sin(kπs)`. A constant
acceleration error is a parabola — 99.9% the k = 1 mode. Median energy share
over 113 refereed reps:

    lift        k=1     k=2     k=3     k=4    k≥5 + rest
    bench      0.940   0.015   0.004   0.006     0.035
    squat      0.829   0.044   0.020   0.004     0.103
    deadlift   0.445   0.078   0.201   0.005     0.271

k = 1 is the ceiling on **any** correction carrying one number per rep. So
deadlift's rest-ZUPT estimator at r = 0.594 is not weak — it is close to what
the model allows, and its remaining 56% sits in higher modes, k = 3 most of all,
which is the signature of something localised. That is B6's term, now sized.

**And the lifts are the wrong way round.**

    lift        the model fits      a raw anchor exists
    bench            94%            no — and provably never
    squat            83%            no
    deadlift         44%            yes, the floor between reps

The lift where a constant acceleration explains the error is the one with no way
to measure it. That is not bad luck, it is the same physics twice: a bar that
sets down gives you a zero-velocity anchor **and** a landing impulse, and the
impulse is exactly what fills deadlift's higher modes. You cannot have the
anchor without the thing that spoils the model.

---

## 89 — bench gets an anchor at lockout, and it halves the error (H39, 2026-08-25)

### `89_lockout_anchor.png`

H38 made this the biggest prize on the board — 94% of bench's post-closure error
is reachable by a one-number-per-rep correction — and the only blocker was an
anchor.

**The standing objection was about detection, not availability.**
`metrics.momentum_closure` records that a bar descending at constant velocity
reads |a| = g with a quiet gyro exactly as a bar at rest does. True, and it is
about DETECTING an anchor from the raw signal. Nothing has to be detected:
`_full_cycles` already runs a smooth lift's window turnaround to turnaround, so
the boundary is at lockout and the segmenter has placed it.

**And the bar is still enough there, in the channel that matters.** Measured
against video, with the deadlift floor rest as the control since H36's working
estimator is built on it:

    where                    n   |v_h| median   vs typical   |v_v| median
    bench window edge       55      0.0323         0.66         0.0581
    squat window edge       72      0.0196         0.45         0.1704
    deadlift window edge    79      0.0352         0.89         0.6375
    deadlift REST (works)   35      0.0168         0.44         0.0123

The bar is moving vertically at a smooth lift's boundary — it is reversing — but
its horizontal velocity is near zero, and horizontal is where the problem is.

**The result**, `a_est = [v_h(end) − v_h(start)] / T` — and **the numbers this
entry first published are WITHDRAWN.** It reported bench going 2.09 → 0.98 cm
under leave-one-capture-out with a fitted gain of 0.576. Both came from a
harness that carried an INTERCEPT the shipped pipeline does not have, and the
intercept was absorbing part of the signal. Measured through the code that
actually ships — `correct.QUAD_LIFTS`, entry `90` — bench goes **1.81 → 1.30 cm
with nothing fitted**, six of seven captures improve, and six of seven beating
the null becomes seven of seven. The direction and the sign of every claim here
survived; the size did not.

What this entry established and `90` did not repeat is WHY bench can carry an
anchor at all, which is the velocity table above. Squat's failure under the same
rule (r = +0.217, p = 0.21 over 35 reps) also stands, and `90` reaches it a
second way.

**Squat fails despite a better anchor** (r = +0.217, p = 0.21). Its k=1 fit is
83% against bench's 94%, and its bar moves vertically 3× faster at the boundary
(0.170 vs 0.058 m/s), so any display-axis error leaks into the channel. Not
established.

---

## 90 — C19's quadratic, restricted to the horizontal (H40, 2026-08-25)

### `90_quadratic_bench.png`

**Step 7 now carries a quadratic term on bench, fore-aft only.** `correct.QUAD_LIFTS`.

`correct.detrend_rep` has had `order=2` since C19 built it — a quadratic pinned
by the rep's own endpoint velocity difference, needing no new anchor. C19
measured it and rejected it, **and the rejection was right about what it
tested**: applied to all three axes, a deadlift's `dv` is ~1 m/s of landing
impulse, spreading that smoothly injects `dv·T/8` at mid-rep, and the vertical
and the ROM threw it out — 48.7, 41.8 and 73.1 cm vertical against a shipped
5.2/6.6/5.2, ROM 78–116 cm against a 61 cm ceiling. None of that is disputed or
repaired here.

What is new is that nobody had separated the axes. Bench has no landing, so its
`dv` is velocity error rather than an impulse, and its rep boundary sits at
lockout where the bar is horizontally still — 0.66 of the rep's own typical
speed, against 0.44 at the deadlift floor rest the pipeline already trusts.

    lift        h rms          beats_null      improved   beat the null
    bench     1.81 → 1.30     2.46 → 2.82        6 of 7    6 of 7 → 7 of 7
    squat     3.19 → 3.41     1.40 → 1.36        6 of 10   8 of 10 → 8 of 10
    deadlift  3.11 → 5.84     0.64 → 0.32        0 of 9    0 of 9 → 0 of 9

**Bench goes from 6 of 7 captures beating the flat-line null to 7 of 7**, with
`bench_spoto_95x5_2` — the only capture in the corpus that lost to drawing no
fore-aft motion at all — crossing at 1.81. Four of seven now sit inside the 1 cm
spec. **The vertical does not move**, to 3e-15 cm on every capture of every
lift, by construction and by gate.

The left panel is the argument in one line: sweeping the weight on the quadratic,
bench falls and the other two rise. The deadlift curve is C19's rejection
reproducing. **The figure's sweep stops at 1.3**; the 1.5 quoted below was
measured later and is not drawn here.

**Squat is a WASH that hurts where the reconstruction works, and that is why it
is refused.** Six of ten captures improve, but the median moves the wrong way
and so does `beats_null`, because the losses are bigger than the gains and are
not randomly placed: dropping the miscounted single, the gain correlates with
the baseline error at r = +0.78 — it helps the worst captures and hurts the
best, taking `squat_pause_140x4_1` from 1.18 cm, the best squat in the corpus,
to 2.18. The middle-right of the third panel is that: squat's points sit close
to the diagonal, scattered both sides.

**There is no gain constant, and two earlier claims of one are withdrawn.** A
harness fitted 0.58, an artefact of an intercept in that harness. A
leave-one-capture-out figure of 1.53 was then quoted as the number to trust, and
it is not: it came from choosing the weight by LOO on a 0–1.3 grid, and widening
the grid to 1.5 moves it to 1.84 — the held-out median is not monotonic in the
weight across seven captures. **The weight is not identifiable from this
corpus**, so it stays at 1 where C19 put it and there is no held-out number to
quote. The sweep does show the result is not delicate: every weight from 0.5 to
1.5 leaves 7 of 7 beating the null at 1.30–1.68 cm, against 1.81 at weight 0.

*The table above was measured on 2026-08-26 through the shipped code path and
replaces the one first published with this figure, whose squat row read
3.19 → 3.95 on 2 of 10. The figure itself was right — its left panel puts squat
at 3.4 at weight 1 — and was not regenerated.*


---

## 91, 92 — where the horizontal error comes from (H41/H42, 2026-08-25/26)

### `91_error_shape.png`, `92_bump_origin.png`

The owner's hypothesis, then the owner's question: the linear detrend is doing a
polynomial's job — so where does the polynomial come from, can the pipeline
absorb it, and if not what step would?

**91 measured the shape and read it wrongly, and that is recorded rather than
quietly fixed.** PCA over the per-rep video-minus-pipeline error gives PC1 =
0.787 with a 0.962 overlap with `s²−s`, the same curve on every lift (cross-lift
|cos| 0.88–0.97). That was read as a shared physical cause. **It is what the
closure forces.** The same PCA on synthetic curves with no shared structure,
closed the same way:

    source                          PC1     |overlap with parabola|
    real error                     0.787            0.962
    white noise                    0.328            0.193
    random walk                    0.633            0.974
    double-integrated white noise  0.915            0.998

Double-integrated noise — what integrating an IMU twice produces — beats the
real data on both. Any smooth function pinned to zero at both ends looks like a
bump. What survives is the AMPLITUDE, which is real and varies rep to rep.

**92 found where it comes from, and the chain closes against measurements taken
years apart and never compared:**

    the bump implies a tilt of           0.13° median, 0.35° at p90
    P5 measured attitude at a hold       0.05° opening, 0.14° closing
    P4 measured it on a table            0.018° over 10 s
    1 cm of bump at T = 3.1 s needs      0.049°

**The tilt the bump implies is the tilt P5 measured.** The horizontal spec needs
the attitude 2.7× tighter than Core Motion delivers — so it is a sensor-accuracy
problem, not a modelling one, and the reconstruction is already near what the
attitude permits. Yaw is worse: gravity cannot constrain it and P5 bounds it at
0.0–1.4° per set, an order above what 1 cm allows.

**And it is not a fixed body-frame vector.** One 3-vector fitted across all 113
reps — as a wrist-offset error `R(t)·δd` or a body-frame accel bias `∬R(t)·b` —
gives leave-one-capture-out R² of 0.44/0.46 on bench and negative on squat,
deadlift and pooled. C28 reached that per capture; this reaches it with one
vector against a hundred reps.

**Can the existing pipeline absorb it?** Partly, and that is what `90` ships:
bench 1.81 → 1.30 cm with the quadratic term, against a perfect per-rep bump
correction's 0.65 and a 1 cm spec. No new step is proposed, because
the remaining error is attitude noise and no step downstream of the attitude can
remove it.

## 93 — `93_display_axis_sign.png`, why squat renders mirrored (H44)

The owner reported squat sets drawn as mirror images of the video, most obviously
`squat_155x4_3` and the `squat_pause_140x4_*` sets, faintly on bench, invisibly
on deadlift. That ordering is the finding, not an accident of which plots got
looked at.

**A** is the mechanism. Step 8 takes fore-aft as a fixed direction in watch
coordinates, but only that vector's HORIZONTAL projection becomes the axis — and
the vector lies 4–6° off horizontal on bench, 0–5° on deadlift and **31–55° on
squat**. **B** is the consequence: the shipped axis sits a median 12° from the
video-optimal direction on bench, 47° on deadlift and **62° on squat**, with two
squats within 5° of PERPENDICULAR. A tipped vector both amplifies the body-plane
angle into a larger screen angle and makes it posture-sensitive, so the direction
moves between sessions and the sign flips with it.

**C** shows the line is a constant after all, just not 23° — squat's optimum is
−8°, leave-one-capture-out folds land −12…−4, held-out |correlation| 0.75 against
0.62. **The SIGN is not a constant and nothing wrist-derived can be**: no fixed
body direction exceeds 6 of 10 on squat at any angle.

**The bottom row's green curve is the axis fix, NOT a sign fix.** Panels showing
green tracking blue are the line coming right; where green is still mirrored, the
sign is wrong and stays wrong. The owner's crown convention was tried here and
rejected at 6 of 10 — it moved which sets are mirrored, not how many — because
the azimuth of every watch axis from the lifter's anterior has circular
consistency 0.22–0.33 on squat against 0.77–0.80 on bench. Squat's fore-aft
DIRECTION is an open problem, recorded in `TASKS.md` rather than tuned away.

---

*Numbering: 47 through 93 are taken. The next free number is 94. **52
(`52_deadlift_excursion_origin.png`) is on disk and has no entry in this
file** — it predates G1 and is not G1's to caption, but it is doc debt and
somebody should.*

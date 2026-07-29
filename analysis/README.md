# analysis — real-data diagnostics (2026-07-26/27)

Graphs from running the current pipeline on the first real watch captures, plus
an off-pipeline reconstruction experiment. Generating scripts live in the
session scratchpad (not the repo). Data in `data/raw/`.

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

- **`quality_flags` rejects 12 of 44 reps for strap resonance, wrongly.** It
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
the corrupted velocity and their phase remains unverified.

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

## The stationary table capture (2026-07-30)
`data/raw/stationary_table_20260730_000757.csv` — a watch on a table for 19 s,
recorded to verify the new logger. C2 failed on it (see TASKS.md), and it turned
out to be the most informative capture in the project anyway, because it is the
first measurement of the sensor's own noise floor with no wrist involved.

Quiet window 6–16 s, away from the button presses at each end:

| quantity | on a table | on a wrist, calibration pause |
|---|---|---|
| gyro \|mean\| | **0.002 °/s** | 0.93–1.05 °/s |
| gyro p-p | 0.18 °/s | 4.2–6.0 °/s |
| block SEM | 0.0012–0.0015 °/s | 0.07–0.32 °/s |
| \|mean\|/SEM | 0.28–1.33 | — |
| body-frame accel bias | **0.0025 g** | ~0.035 g (press posture) |
| attitude drift | 0.018° / 10 s | — |

**Two conclusions, and they reframe P3, P4 and P5.**

The residual gyro bias is ~500× smaller than the on-wrist figure this project
has been treating as bias. It is not resolvable above its own noise. So the
0.1–0.9 °/s in P4 is the lifter's own rotation, and B1's "never apply it" is
right for a stronger reason than B1 recorded.

The 0.035 g on-wrist "accel bias" equals g·sin(2.0°). It is the size of a **two
degree attitude error**, not of an accelerometer bias measured at 0.0025 g. That
points the dominant error at attitude, which no constant-bias estimator can fix
— consistent with B6's oracle recovering only ~30%.

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

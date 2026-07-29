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
  claims" (18-36 cm on deadlift, where the video says 8.5-13 cm).

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
against a 1 cm spec. **Vertical: 5.2, 6.8 and 4.9 cm rms** against ±2–3 cm.

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

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

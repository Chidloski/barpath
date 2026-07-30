# Video ground truth — `truth.py`

Documents A2. Everything else in this pipeline measures the bar path by
integrating an IMU twice and hoping; this module measures it by looking at it.

It exists because the spec's tight number — **~1 cm horizontal** — sits on the
one axis with no other check. Vertical has a tape measure. Rep timing has the
floor impact. Horizontal had nothing until this.

---

## What it is used for

**Boundary and phase truth.** Its first act was to find a bug: A1's rep windows
start at the video lockout peak every time (16.42 vs 16.23, 19.21 vs 19.23,
22.64 vs 22.33, 25.91 vs 25.70, 29.48 vs 29.23, 34.60 vs 34.27 s on
`deadlift_155x6_1`), so each window runs lockout-to-lockout and holds the
descent of one rep followed by the ascent of the next. Half a rep out of phase.
Counts could never have shown that.

**Clock sync between video and IMU.** `landings()` finds the bar reaching the
floor; `segment.impact_anchors()` finds the 15–21 g spike. Matching them gives
`sync()`, which fits both an offset *and* a slope so clock drift is measured
rather than assumed.

**Absolute ROM.** Lockout height above the resting bar, per rep, in metres.

**The horizontal spec, given a number.** `metrics.vs_truth` (A3) uses this
module to measure the reconstruction against the bar: 5.05, 9.19 and 15.44 cm
rms per rep on the three deadlifts, against a 1 cm spec, and 5.24/6.60/5.24 cm
vertical against ±2–3 cm. It also showed the horizontal error is a smooth arch
at rep frequency rather than noise. See `analysis/19`.

Note what that leans on, and how it turned out. The plates were measured on
2026-07-30 — 425 mm notched, 445 mm bumper, 450 mm calibrated — replacing a
single assumed 450. Correcting deadlift to the bumper moved those numbers by
under 1% (they were 5.1/9.2/15.4 and 5.2/6.8/4.9), so the diameter was never
the problem it was flagged as.

The scale error is real and it is somewhere else. Per-rep video ROM on the
three deadlifts is 59.1, 66.8 and 47.6 cm against a 61 cm ceiling measured for
this lifter — a 19 cm spread, from two captures that found the *same* plate
radius. Drawback 1 below is rewritten around it. The horizontal numbers above
survive; the vertical ones and the ranking do not. See `analysis/23`.

**Still to come:** B2 needs this to establish the wrist-to-bar lever arm `d`
against something other than a guess.

## Current state, per lift

| lift | plate | works? | median NCC | per-rep ROM | notes |
|---|---|---|---|---|---|
| deadlift | 445 mm bumper | **timing yes, vertical no** | 0.83–0.94 | 59.1 / **66.8** / **47.6** cm | sync 11–16 ms rms, drift <0.25%; ROM spread 19 cm on a 61 cm ceiling |
| squat | 450 mm calibrated | tracks, **warns** | ~0.40 | — | plate clips top of frame at lockout |
| bench | 425 mm notched | **raises** | — | — | needs a manual seed |

Deadlift's row used to read "yes, unattended" without qualification. It tracks
unattended and it syncs to the IMU, and on two of three captures its vertical
scale is wrong — see drawback 1.

Pinned by tests in `tests/test_real_data.py` so the state cannot regress
unnoticed.

## Usage

```python
from src import truth

path = truth.bar_path("data/video/deadlift_155x6_1_20260728.mov")
# -> t, x (fore-aft, m), height (m above resting bar), score, m_per_px, ...

fit = truth.sync(truth.landings(path), imu_impact_times)
t_imu = truth.to_imu_time(path, fit)
```

Bench needs the template placed by hand — coordinates are in the **decoded**
frame, so at the default `scale=0.5` they are half what you read off the video:

```python
path = truth.bar_path(video, seed_yx=(195, 187), seed_radius=37)
```

Requires `ffmpeg` on PATH. No new Python dependencies.

---

## Drawbacks

Ordered by how much they could bite.

**1. The vertical scale is wrong by up to ±20%, per capture.** Per-rep video ROM
on the three deadlifts: 59.1, **66.8** and **47.6 cm**, against a ceiling of 61
measured for this lifter. One lifter, one lift, a 19 cm spread.

This drawback used to read "`PLATE_DIAMETER_M` is assumed (450 mm), nobody has
measured the actual plates." They were measured on 2026-07-30 and it was not the
cause: captures 1 and 2 found the *same* plate radius, and 450 → 445 mm moves
everything about 1%. Radius quantisation (a 1 px grid moves ROM under 2%) and
tracker drift (the floor baseline holds to 0.4 cm; the worst capture has the
*best* NCC) were tested and ruled out too.

What is left is the geometry: `find_plate` calibrates on a plate resting on the
floor, and that scale is then applied to travel reaching the top of frame. The
module docstring used to assert this was safe. It is not. The fix is footage
with a known vertical reference in shot — a metre rule against the rack — not
code. `truth.validate` warns and `metrics.vs_truth` returns `video_rom_flags`;
never quote a flagged capture's vertical unqualified.

Note the flag is one-sided in practice. `deadlift_180x3`'s 47.6 cm is ~20% low
and passes, because the sanity floor is 40 cm and nothing justifies raising it.

**2. Lens distortion is uncorrected.** A phone wide lens bows straight lines and
the bar crosses most of the frame vertically. The leading candidate for
drawback 1, and still without a number of its own.

**3. Bench does not seed automatically.** The plate is small, sits against a
dark ceiling, and abuts the lifter-and-bench silhouette — a larger dark blob
than the plate — so the dark-disc matched filter prefers the clutter. Widening
the radius search does not help; it is not a radius problem. Before `validate()`
existed this returned a confident 0.907 median NCC while tracking motionless
background, reporting 0.0 cm of travel. **A high NCC means the template kept
matching something, not that it matched the plate.**

**4. Squat tracking is indicative only.** NCC ~0.40 against 0.83–0.94 for a
clean deadlift, because the plate leaves the top of frame at lockout and the
template only partly matches. A warning is raised. Do not use squat output as
truth.

**5. It tracks the plate, not the bar centre.** Fine while the bar stays level —
it is rigid — but a tilted lockout moves the plate differently from the centre.
Unquantified.

**6. Fixed template from the seed frame.** The plate rotates a little during a
pull, and minimum NCC on deadlifts drops to 0.337 even where the median is 0.83.
Not currently a problem; would be if a set ran much longer.

**7. Rolling shutter is unmeasured.** Phone sensors skew fast-moving subjects,
and a deadlift pull is fast. Suspected small, but that is a guess, not a finding.

**8. 30 fps quantisation.** 33 ms between frames, against a sync residual of
11–16 ms — the two are close enough that some of that residual is probably just
sampling.

**9. `height` is relative, not absolute.** Measured from the lowest tracked
position. For a deadlift that is the bar on the floor, which is meaningful
(add the 22.25 cm bumper radius for height above ground). For bench and squat
the lowest point is arbitrary.

**10. Auto-seed can pick a bad frame.** It scans the middle half of the clip for
the strongest disc response. A false lock at r=108 px scoring 11 was observed
against ~19 for a correct one — the score separates them, but nothing currently
checks that margin.

## Improvements

Roughly in value-per-effort order.

**Free, and worth doing first:**

1. **Measure a plate.** Removes drawback 1 entirely. Thirty seconds with a tape.
2. **Re-frame the next captures.** Step the camera back so the whole plate stays
   in shot at squat lockout, and so the bench plate clears the bench silhouette.
   Converts squat and bench from "indicative"/"broken" to truth with **no code
   at all**. This is the single highest-value change available.
3. **Film a plumb line or doorframe** from the same position, once. Enough to
   estimate lens distortion and put a number on drawback 2.

**Small code:**

4. **Edge-based circle detection** instead of the intensity blob. The plate has a
   strong circular *edge* regardless of whether its interior is darker than the
   background, which is exactly what breaks on bench. Would likely make bench
   automatic without re-shooting.
5. **Check the auto-seed margin** — reject when the best disc response is not
   clearly ahead of the runner-up, rather than trusting it silently.
6. **Track the bar sleeve** rather than the plate face. Immune to plate changes
   between sets and to drawback 5.

**Larger, only if needed:**

7. **60 fps capture** halves the timing quantisation in drawback 8.
8. **Multi-scale template**, if the camera is ever placed off-axis so that
   fore-aft becomes depth. Not needed for the current filming setup, where the
   camera looks along the bar and fore-aft is in-frame horizontal.

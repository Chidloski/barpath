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

**Still to come:** `metrics.vs_truth` in A3 needs this to give the horizontal
spec a real number, and B2 needs it to establish the wrist-to-bar lever arm `d`
against something other than a guess.

## Current state, per lift

| lift | works? | median NCC | travel | notes |
|---|---|---|---|---|
| deadlift | **yes, unattended** | 0.83–0.94 | 49–70 cm | sync 11–16 ms rms, drift <0.25% |
| squat | tracks, **warns** | ~0.40 | 51–74 cm | plate clips top of frame at lockout |
| bench | **raises** | — | 0.0 cm | needs a manual seed |

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

**1. `PLATE_DIAMETER_M` is assumed (450 mm).** It sets the scale directly, so a
wrong value is a proportional error on every number this module produces. At 2%
that is 1.2 cm on a 60 cm ROM — larger than the spec. *Nobody has measured the
actual plates.*

**2. Lens distortion is uncorrected.** A phone wide lens bows straight lines and
the bar crosses most of the frame vertically. This is the largest error here
that has no number attached to it.

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
(add the 22.5 cm plate radius for height above ground). For bench and squat the
lowest point is arbitrary.

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

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

Since 2026-07-31 that list is no longer deadlift-only. Bench adds **0.64, 0.76,
1.88, 2.63, 2.69, 2.75 and 3.67 cm** horizontal across all seven captures — two
of them inside the 1 cm spec, the first in this project. Read those through
`metrics.bench_sync`'s docstring: the clock alignment is a cross-correlation
calibrated on deadlift rather than a landmark match, so bench carries no sync
residual and its vertical inherits ~1 cm from the sync itself. See
`analysis/29`.

**And read `beats_null` before any of them.** `vs_truth` compares the pipeline
against drawing no fore-aft motion at all. Six of ten captures lose to that flat
line, including all three deadlifts (0.70×, 0.35×, 0.13×). Only `bench_90x4_2`
and `_3` clearly win, by 4×. Gated since C11: a per-capture non-regression floor
plus an xfail carrying `beats_null > 1` as the target.

**One number here does not depend on the video's distances at all.**
`metrics.momentum_closure` (C11) integrates vertical acceleration between two
moments the video says the bar was *still*, which must come to zero. A scale
error cannot move a zero crossing, so this survives the per-capture vertical
scale defect below — and it found that the deficit is the floor landing and
nothing else. Bench closes at 0.0019 g over 44 intervals and the deadlift's own
pulls at 0.0008 g, against 0.0300 g across a landing. See `analysis/31`.

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

| lift | plate | works? | median NCC | travel | notes |
|---|---|---|---|---|---|
| deadlift | 445 mm bumper | **timing yes, vertical no** | 0.83–0.94 | 59.1 / **66.8** / **47.6** cm | automatic; sync 11–16 ms rms, drift <0.25%; ROM spread 19 cm on a 61 cm ceiling |
| bench | 425 mm notched | **yes, from a hand seed** | 0.75–0.95 | 21.8–29.8 cm | `truth.SEEDS`; all 7 sync since C10; radius carries ~4% scale |
| squat | 450 mm calibrated | **no — `vs_truth` refuses** | ~0.40 | 2 raise, 2 at ~12.5 cm | plate clips top of frame at lockout |

Deadlift's row used to read "yes, unattended" without qualification. It tracks
unattended and it syncs to the IMU, and on two of three captures its vertical
scale is wrong — see drawback 1.

Bench's row read **raises** until 2026-07-31. Two things changed it: a
hand-placed seed per capture, and a template sized to fit inside the plate
rather than `track`'s default 97×97 px, which was holding static ceiling in its
corners and part-anchoring the tracker to the gym. Squat's row got worse rather
than better, and the ordering of this table changed with it — deadlift is no
longer the only lift with truth, and squat is now the only one without.

Pinned by tests in `tests/test_video_truth.py` (the referee itself) and
`tests/test_real_data.py` (the pipeline judged through it) so the state cannot
regress unnoticed.

## Usage

```python
from src import truth

path = truth.bar_path("data/video/deadlift_155x6_1_20260728.mov")
# -> t, x (fore-aft, m), height (m above resting bar), score, m_per_px, ...

fit = truth.sync(truth.landings(path), imu_impact_times)
t_imu = truth.to_imu_time(path, fit)
```

Bench needs the template placed by hand, but you do not have to place it — the
seven captures are already in `truth.SEEDS`, and `bar_path` looks the stem up,
so a bench clip is called exactly like a deadlift one. A capture that is not in
the table still raises rather than being seeded by guesswork.

To seed a NEW bench capture, read the plate centre and radius off a frame with
the bar out of the rack and add a row. Coordinates are in the **decoded** frame,
so at the default `scale=0.5` they are half what you read off the video, and
`half` is derived from the radius by `truth.template_half`:

```python
# What a SEEDS row means, spelled out: (frame, cy, cx, radius)
truth.SEEDS["bench_90x4_1_20260727"]     # -> (530, 192, 197, 48)

# The same thing passed explicitly, which is what bar_path does internally:
path = truth.bar_path(video, seed_yx=(192, 197), seed_radius=48,
                      half=truth.template_half(48))   # half -> 31
```

**`seed_radius` is the pixels-to-metres scale**, not just a search hint. Read it
carelessly and every distance from that capture is wrong by the same fraction.

Requires `ffmpeg` on PATH. No new Python dependencies.

---

## Drawbacks

Ordered by how much they could bite.

**0. The deadlift track is LOST AT LOCKOUT, and it invents ~10 cm of fore-aft
motion there.** Added 2026-07-31 (C12), at the top because it undermines the
lift this project treats as its best-founded truth.

Top-of-travel NCC is **0.371 / 0.395 / 0.440** against whole-clip medians of
0.830 / 0.846 / 0.937. Stratified by height it is total: 97–100% of the frames
in the top 10 cm of travel score below `GOOD_SCORE`, and 0% of those in the
bottom 10 cm do. The bar at a deadlift lockout is held against the thighs and is
nearly still, so the several centimetres of fore-aft travel reported there are
the tracker moving, not the bar.

**The old `validate` could not see this** — it checked the whole-clip median,
and lockout is 8–15% of a clip. `truth.top_of_travel_score` measures it now and
`validate` warns separately, because the two fail independently.

It flatters the pipeline rather than penalising it: the invented motion inflates
`null_h_rms`, so deadlift `beats_null` falls from 0.70/0.35/0.13 to
0.59/0.21/0.07 when restricted to well-tracked frames. Horizontal magnitude
barely moves. Bench is the control and holds at 0.563–0.850.

Not fixable by template size — shrinking `half` raises NCC and makes the track
worse (ROM 60.5 → 74.1 cm). Needs a wider shot. See `analysis/34`.

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

**Drawback 0 is probably the mechanism.** ROM is the lowest-to-HIGHEST tracked
point, so the highest point — the one that sets the number — is measured exactly
where the tracker has lost the plate. "Right in location, no mechanism" became
"right in location, with a mechanism" on 2026-07-31. It is not proven: the three
candidates above were tested and this one cannot be until footage tracks at
lockout. But it explains a 19 cm spread on a fixed anatomy far better than a
scale subtlety does.

Note the flag is one-sided in practice. `deadlift_180x3`'s 47.6 cm is ~20% low
and passes, because the sanity floor is 40 cm and nothing justifies raising it.

**2. Lens distortion is uncorrected.** A phone wide lens bows straight lines and
the bar crosses most of the frame vertically. The leading candidate for
drawback 1, and still without a number of its own.

**3. Bench does not seed automatically — it is seeded by hand.** The plate is
small, sits against a dark ceiling, and abuts the lifter-and-bench silhouette —
a larger dark blob than the plate — so the dark-disc matched filter prefers the
clutter. Widening the radius search does not help; it is not a radius problem.
Four seeders were tried on 2026-07-31 — dark disc, circular-edge radial
gradient, dark disc weighted by temporal motion energy, and a dark-annulus rim
filter — and **all four preferred the clutter**, which is why improvement 4
below is struck out. `truth.SEEDS` carries one hand-read `(frame, cy, cx,
radius)` per capture instead, and all seven now track.

Before `validate()` existed the auto path returned a confident 0.907 median NCC
while tracking motionless background, reporting 0.0 cm of travel. **A high NCC
means the template kept matching something, not that it matched the plate** —
which is doubly worth remembering now the seed is placed by hand, since a hand
placed until the score looks good proves exactly nothing. The bench gates in
`tests/test_video_truth.py` therefore assert travel and rep count, not NCC.

The hand-read `radius` is also the pixels-to-metres scale, at about ±2 px on
~48 — **~4% on every bench distance**, checked by nothing but `VERTICAL_ROM_M`.
That is larger than the plate-diameter correction that drawback 1 chased, which
turned out to be worth under 1%.

**4. Squat is not truth, and `metrics.vs_truth` refuses it.** The 2026-07-27
captures track at NCC ~0.40 against 0.83–0.94 for a clean deadlift, because the
plate leaves the top of frame at lockout; a warning is raised. The four from
2026-07-30 are worse — two raise, two report ~12.5 cm of travel against a
45–76 cm band. `find_plate` was fixed on 2026-07-31 so that a disc hanging off
the frame edge cannot win by being scored against zero-padding, which stopped
three of those dying with a numpy broadcast error. **That converted a crash
into an honest refusal; it did not make squat trackable.** Do not use squat
output as truth.

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
   Converts squat from "indicative" to truth with **no code at all**, and would
   let bench drop its hand seeds. Still the highest-value capture change, though
   no longer the highest-value change overall — bench became truth in code on
   2026-07-31, which is what that claim was written against.
3. **Film a plumb line or doorframe** from the same position, once. Enough to
   estimate lens distortion and put a number on drawback 2.

**Small code:**

4. ~~**Edge-based circle detection** instead of the intensity blob. Would likely
   make bench automatic without re-shooting.~~ **Tried on 2026-07-31 and it does
   not.** A circular-edge radial-gradient matched filter was one of four seeders
   built and tested; it preferred the bench-and-lifter silhouette like the other
   three. The reasoning above was sound and the measurement disagreed: the plate
   is not the most circular thing in a bench frame either. Kept rather than
   deleted because it is the obvious idea and someone will have it again.
5. **Check the auto-seed margin** — reject when the best disc response is not
   clearly ahead of the runner-up, rather than trusting it silently.
6. **Track the bar sleeve** rather than the plate face. Immune to plate changes
   between sets and to drawback 5.

**Larger, only if needed:**

7. **60 fps capture** halves the timing quantisation in drawback 8.
8. **Multi-scale template**, if the camera is ever placed off-axis so that
   fore-aft becomes depth. Not needed for the current filming setup, where the
   camera looks along the bar and fore-aft is in-frame horizontal.

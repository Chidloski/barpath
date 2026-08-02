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

### Which referee scores a capture (C17, 2026-08-02)

`metrics.vs_truth` and `metrics.momentum_closure` take either tracker. You
normally say nothing and it is inferred from where the clip lives:

```python
metrics.vs_truth(result, "data/video/deadlift_180x3_20260728.mov")     # template
metrics.vs_truth(result, "data_v2/video/deadlift_150x5_20260801.mov")  # markers

metrics.vs_truth(result, clip, tracker="markers")   # or say so explicitly
metrics.vs_truth(result, markers.bar_path(clip))    # or hand it a tracked path
```

The third form is how you track once and score several ways without decoding
twice. `pipeline.find_video` pairs a capture inside its own dataset, so a
`data_v2/raw` CSV finds `data_v2/video` and never reaches across.

**The inference is about the directory, not the footage.** `data_v2/` exists
because the capture protocol changed, so the layout already records the answer;
sniffing frames for markers would be a second tracker on every call and a new way
to be wrong. A capture cannot be scored by the tracker its footage was not shot
for — the template does not reliably find a marker-less bench plate, and the
constellation cannot find stickers nobody applied.

`vs_truth` reports `video_tracker`, and `video_top_ncc` **or**
`video_top_residual_cm` with NaN for the other, because one field that silently
means two things is a failure mode this project already has a collection of.

**Nothing has yet been scored through the markers**, because no `data_v2`
capture has an IMU log beside it. The plumbing is gated; the agreement is not.
Specifically unmeasured: whether a landing found on marker footage falls at the
same instant as one on template footage, which matters at the deadlift sync's
13.5 ms.

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

---

# The sticker tracker — `markers.py`

A second referee, added 2026-08-01 (C15) for the `data_v2/` captures, which are
filmed from a tripod with retroreflective markers on the plate: three near the
rim roughly a third of the circumference apart, one on the bar's end cap, each
reflective disc ~1.5 cm.

It does not replace `truth.py` and cannot — no marker exists in `data/video/`,
so every capture the pipeline is currently scored against is still refereed by
the plate template. It is what future captures should use.

## Why a different feature entirely

Both of `truth.py`'s measured defects are defects of the *feature*, not of the
code around it, and no amount of tuning reaches them:

- **Lost at lockout.** A black plate against a dark ceiling has no contrast to
  match on. `analysis/36` reproduces this on footage C12 never saw: NCC falls
  from ~0.85 at the floor to ~0.3 at lockout on all three new deadlifts.
- **Confidently static.** On `bench_85x6` the plate template scores its highest
  median NCC of the five, 0.95, while reporting 0.2 cm of travel over six reps.

A bright marker on a dark plate is the one feature whose contrast does not
depend on what is behind the bar, and three of them in a rigid triangle measure
their own scale in every frame.

## State on the five `data_v2` captures

| | tracked | 3 markers | fit residual | travel | plate template, same clip |
|---|---|---|---|---|---|
| deadlift_150x5 | 100% | 100% | 0.52 px | 54.0 cm | 54.5 cm |
| deadlift_160x5 | 100% | 100% | 0.61 px | 57.1 cm | 58.6 cm |
| deadlift_190x1 | 100% | 100% | 0.15 px | 52.3 cm | 47.9 cm |
| bench_85x6 | 100% | 100% | 1.10 px | 29.7 cm | **0.2 cm, raises** |
| bench_110x1 | 100% | 100% | 1.07 px | 23.8 cm | 33.3 cm |

All five sit inside `truth.VERTICAL_ROM_M`. Deadlift travel spans 4.8 cm against
the template's 10.7 cm on the same footage. Rep counts read off the vertical
trace match all five labels.

## The three things to know before quoting a number

**The pose is fitted on the rim markers only.** The end-cap marker is on the
sleeve, which protrudes toward the camera, so its offset from the rim centroid
is parallax — it correlates with the bar's height at r = 0.949 and swings over
168 px on one clip. It is tracked and reported as a diagnostic of the camera
geometry, and deliberately kept out of the path.

**Absolute scale rests on one constant, `STICKER_RATIO = 0.858`**, measured on
the three deadlifts where the plate rim is detectable and verified by eye. Per-
*frame* scale is measured properly, from the constellation's own apparent size,
which is the part that attacks the ±20% vertical scale error. **On bench the
constant is transferred, not measured** — a different plate, its own stickers —
and that is the weakest claim in the module. Three rim detectors were tried and
recorded at `STICKER_RATIO`, including one that was beautifully consistent
across captures (0.928/0.938/0.929) and simply wrong, having locked onto the
bumper's inner step. Consistency is not accuracy.

**`score` is not an NCC** and must never be compared with `truth.GOOD_SCORE`.
It is fit quality: markers matched, attenuated by residual.

## Usage

```python
from src import markers

path = markers.bar_path("data_v2/video_only/deadlift_150x5_20260801.mov")
# key-compatible with truth.bar_path: t, x, height, score, fps, m_per_px, travel_m
path["calibration"]           # read this before quoting anything
path["height_flat"]           # the same path under one fixed scale, for comparison
path["perspective_shift_cm"]  # how far the per-frame scale moved it
```

Both paths are returned on purpose: the module's claim is that the per-frame
scale is better, and a claim like that should be checkable from its own output.
Measured, the correction is worth 0.6-1.4 cm on deadlift and 0.1-0.4 cm on
bench — real but small, and much smaller than the tracking failures it sits
alongside.

Gated by `tests/test_markers.py`, which skips cleanly when `data_v2/` is absent.

**The fit residual rises with height, and is reported here so it is not
discovered later as a surprise.** Pooled over the three deadlifts it runs 0.16 px
at the floor to 0.81 px at lockout, correlation +0.54; per capture the lockout
medians are 0.78, 0.71 and 1.60 px. So the stickers are **not** immune to what
breaks the plate template — the marker is smaller and dimmer at the top of
frame, and the centroid is correspondingly noisier. The difference is that they
degrade inside tolerance and never lose the bar, while the template degrades
past `GOOD_SCORE`: 100% of its top-10 cm frames are untrusted against 31% at the
floor. Do not restate this as "height does not affect the sticker tracker".
Measured in `analysis/37`.

**That paragraph used to end by noting the 1.60 px lockout sat above the 1.5 px
gate, "which passes because it tests the whole-clip median". C17 stopped writing
that down and fixed it (2026-08-02).** `markers.top_of_travel_residual` measures
the fit over `truth.TOP_FRAC` of travel — the same span `truth.top_of_travel_
score` uses, so the two referees stay comparable — `validate` warns on it, and
`tests/test_markers.py` gates on it per capture.

Two things fell out of measuring it properly, and the second is the reassuring
one. **`deadlift_190x1` has the lowest whole-clip residual of the five (0.150 px)
and the highest at lockout (1.595 px), a 10.6x spread**: the old gate ranked it
the best-fitting capture held while it was the worst where the measurement is
taken. That is C12's shape exactly, in the module written to fix C12. And
**converted through each frame's own scale the same five read 0.177 / 0.168 /
0.333 / 0.279 / 0.226 cm**, so the worst lockout fit in the set is a third of the
1 cm spec. The stratification is real; the tracker is still comfortably usable
at its worst point, which is precisely the claim C15 made against the template
and it survives being measured properly. The gate is therefore in **centimetres
against the spec** rather than pixels — `markers.MAX_TOP_RESIDUAL_CM`, set at
half the accuracy the referee is asked to judge — with the per-capture values
pinned at 25% headroom so they can only improve.

**It tracks at full resolution and holds the whole clip, so mind the memory.**
The stickers are ~5 px at 360x640 and `truth.bar_path`'s `scale=0.5` would throw
away the sub-pixel accuracy the module rests on. `markers._frames_u8` therefore
decodes to uint8 and `_grey` converts one frame at a time: 610 MB peak for a
759-frame clip, against the 1936 MB `truth.frames` peaks at just to *produce* the
float32 stack. Do not go back to `truth.frames` here, and do not run several
tracks concurrently on a small machine — running six at once is what crashed an
8 GB laptop on 2026-08-01, and it is why this is written down.

# D2 state — why two of the four 8-sticker squat clips mis-track

Written 2026-08-07 by **D2**, on branch `c29-jump-state`, stopped early on the
PM's instruction (owner at 94% of usage). Diagnosis is substantially complete;
no fix was attempted and **no source file was changed**. Written so a cold agent
can resume without re-deriving anything.

**Nothing in `src/` or `tests/` was touched.** `src/markers.py`, `src/truth.py`
and `tests/test_markers.py` are byte-identical to `38ac79d`, so the nine
existing marker captures cannot have moved and no verification is owed. This
file and a `HEARTBEAT.md` claim are the whole diff.

---

## Headline

**The proximate cause is family selection, and it is C27's defect one level up:
on both bad clips `layout="auto"` chose the THREE-marker family over the conic,
and the triangle it chose is gym furniture.** Rendered over the frames, the
`squat_170x1` constellation is *a rack upright + one plate sticker + a bench/
floor fixture*, with the fitted centre sitting in empty air between the lifter
and the rack; on `squat_pause_140x4_3` all three points are background fixtures
and the plate — eight stickers, plainly in shot — is ignored throughout.

Two of the three points being bolted to the gym is exactly why the health
numbers look fine: a static pair pins the similarity, so coverage is 96.7-97.8%
and the whole-clip residual 1.11-1.12 px, while the reported travel is 14 cm.

**But forcing the conic does NOT fix these two clips**, so selection is
necessary and not sufficient — the same shape as C21's result. My current
verdict is that `squat_170x1` is **UNUSABLE as shot** and `squat_pause_140x4_3`
is **probably unusable**; confidence moderate on the first, lower on the second
(I did less work on it). See *Verdict* for what would settle it.

---

## Per-clip numbers

### What ships today (from the tracked-path cache, `tmp/paths.pkl`)

| clip | n_rim | layout | seed f | coverage | resid med | travel |
|---|---|---|---|---|---|---|
| `squat_pause_145x4_1` | 7 | ellipse | 810 | 100% | 0.88 px | 59.4 cm |
| `squat_pause_140x4_2` | 6 | ellipse | 700 | 100% | 0.69 px | 60.1 cm |
| `squat_170x1` | **3** | **triangle** | 0 | 97.8% | 1.11 px | **14.0 cm** |
| `squat_pause_140x4_3` | **3** | **triangle** | 1219 | 96.7% | 1.12 px | **24.7 cm** |

`n_rim` is the tell and it is already in the shipped output: 3 means the
three-sticker path won on a plate that carries eight.

### Per-family trial merits

`seed_frame`'s two families run separately through `_select_hypothesis`, which
is what `layout="auto"` compares:

| clip | triangle merit | ellipse merit | winner |
|---|---|---|---|
| `squat_pause_145x4_1` | 0.0428 | **0.1671** | ellipse ✓ |
| `squat_pause_140x4_2` | 0.0601 | **0.2282** | ellipse ✓ |
| `squat_170x1` | **0.0545** | 0.0197 | triangle ✗ |
| `squat_pause_140x4_3` | **0.0657** | 0.0109 | triangle ✗ |

The good clips win by 2.8-3.8x; the bad ones lose by 2.8-6.0x. Nothing is
marginal — the ellipse hypothesis on the bad clips is genuinely poor, not
narrowly beaten.

### Forced `layout="ellipse"` on the bad clips

| clip | n_rim | coverage | resid med | centre y-range | circumradius seed → tracked median |
|---|---|---|---|---|---|
| `squat_170x1` | 8 | 95.6% | **4.03 px** | 161 px | 144.6 → 98.7 (not rigid) |
| `squat_pause_140x4_3` | 8 | 75.5% | **4.21 px** | 252 px | 109.5 → 73.8 (not rigid) |

Against the good clips' 0.69-0.88 px and 288-303 px of centre travel. **So
disabling the triangle family would convert a wrong answer into a differently
wrong answer.**

---

## What was ruled IN and OUT

- **`layout=` / family selection — RULED IN, and it is the proximate cause.**
  `n_rim = 3` in the shipped path on both bad clips; the merits above; the
  overlay renders. See *Structural point* below.
- **Detector de-duplication (C27's `_merge_close`) — RULED OUT.** The winning
  constellations on the bad clips are three-point triangles, so `_merge_close`
  is not in their path at all, and the hand-seeded eight-point conic on
  `squat_170x1` returns exactly 8 distinct points with a 0.08-0.39 px fit. No
  doubled sticker was observed on any squat clip.
- **`seed_frame` verification (`_trial_merit`) — RULED IN as a contributing
  defect, but not sufficient.** Handed the *provably correct* eight-point
  constellation by hand (below), `_trial_merit` scores it **0.0112**, i.e.
  **lower than the clutter triangle's 0.0545**. The merit prefers the furniture
  over the bar. Two named reasons, both structural:
  1. It divides by `1 + r3`, where `r3` is the **similarity** residual. On these
     clips the plate tips after the unrack and the similarity cannot represent
     foreshortening, so the true constellation is charged 3.6-6.6 px of residual
     that is a model error, not a tracking error. A clutter triple that is
     bolted to the wall is charged 1.1.
  2. Its leading term is "fraction of frames with **all** `n_rim` markers
     matched". That asks an 8-point model to hold 8 of 8 and a 3-point model to
     hold 3 of 3. The docstring acknowledges the bias ("toward the incumbent
     triangle ... the safe direction"); on these captures it is not safe.
  3. **It has no MOTION term at all**, although `seed_frame`'s own docstring
     says "The bar is the thing in a gym that moves, and that is what picks it
     out here." Motion survives only in the *group filter* (`spread`), which
     C23 demoted; the decision itself is blind to whether the hypothesis moved.
- **`truth.find_plate` — NOT implicated in the mis-track**, but it is wrong here
  as C32 found on bench: `squat_170x1` reports `sticker_ratio = 1.11` (a sticker
  circle *larger* than the detected plate) and `rim_detection_credible = False`.
  It sets nothing, so it cannot cause this.
- **`truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06 entry**, so squat falls
  through to `sticker_radius_m = 0.1823` (= ½·0.425·`STICKER_RATIO`) by accident
  rather than by decision. Recorded, **not fixed** — it is a scale question and
  cannot turn 14 cm into 65. Still owed.

### Structural point worth keeping

On a plate carrying **eight** stickers, `candidates` can never return the true
constellation — C26 measured the best available triple at 135/135/90°, chord
spread **0.255 against `_triangle_ok`'s tolerance of 0.25**. So on eight-sticker
footage *every* triangle hypothesis is clutter by construction, and yet
`layout="auto"` still lets one win on merit. C27 fixed "the fallback never
fires"; it did not fix "the guaranteed-wrong family can still win". That is a
real defect independent of whether these two clips are salvageable.

---

## `validate` already catches both — correcting the brief

The brief (and C31's note) says coverage and residual "look HEALTHY", which is
true only of coverage and the **whole-clip** residual. `markers.validate` is not
fooled, and C17's stratified gate is what catches it:

    squat_170x1          ROM 14.0 cm below the 45 cm squat floor
                         top-15%-of-travel residual 2.10 cm (13.68 px)
                         against 0.14 cm (1.11 px) whole-clip  — 12x
    squat_pause_140x4_3  ROM 24.7 cm below the 45 cm squat floor
                         top-15%-of-travel residual 2.69 cm (10.18 px)
                         against 0.26 cm whole-clip
    squat_pause_145x4_1  no residual or ROM warning
    squat_pause_140x4_2  no residual or ROM warning

So **no new gate is needed**; the existing one fires and separates the good from
the bad cleanly. What was missing is that nobody read the warnings. Do not
"fix" this by adding another check.

(`validate`'s own docstring is now falsified and should be corrected by whoever
resumes: it says "A constellation tracker cannot lock onto static background —
the geometry would not fit." These two clips are that failure, and `track`'s
docstring already contradicts it — "a rigid triple of gym fixtures fits a rigid
model perfectly".)

---

## The hand-seeded test — is the plate trackable at all?

C21's method: hand the tracker the right constellation and see what it does.
Seeded by running `ellipse_candidates` over only the detections inside a box
drawn around the plate.

**`squat_170x1`, frame 0 (bar racked):** an eight-point constellation at centre
(281.1, 257.3), semi-major 99.6 px. `track` follows it at **0.08-0.39 px median
residual with 8 of 8 markers for frames 0-150** — so the stickers are there,
they are detected, and the tracker can follow them. This is the positive
control and it passes.

Then, from frame ~160 on:

    frames      resid (px)   n_markers
    0-150       0.08-0.39       8.0
    160-440     3.6-6.6         8.0     <- unrack; all 8 still matched
    480-640     10-13           6.5-7.5
    720+        8.5-12          6-8, lock lost during the descent

**Residual rising to 3.6 px while all eight markers are still matched is a
SHAPE change, not a tracking failure** — the constellation is no longer a
similarity of the model. That is out-of-plane plate tilt after the unrack, which
`track`'s similarity fit cannot represent by construction (module docstring,
*Limits*). The good clips do not have it: `axis_ratio_median` is **0.983 and
0.989** there (near square-on) against NaN on the bad ones (no conic was fitted,
because the triangle path won).

Relaxing every physical gate (`max_scale_dev` 1.0, `max_jump_px` 80,
`gate` 24, `max_scale_step` 0.15, `max_angle_step_deg` 25) does **not** rescue
it: coverage 0.980 but residual 8.15 px, and the overlay shows the lock held to
about frame 852 and lost through the descent. Individually: `scale_dev 1.0` →
resid 4.54; `jump 80` → 4.08; `gate 24` → 6.64. None recovers the rep.

**So C21's "`track` is not implicated, the whole failure is `seed_frame`" does
NOT transfer to these clips.** Here `track` is implicated as well.

---

## Plate geometry — the framing problem

Conics fitted inside a hand-drawn box on named frames of `squat_170x1`, with the
fit residual reported so a hypothesis can be believed or rejected on its own
numbers. `plate_r` = semi-major / `STICKER_RATIO`; `edge_margin` = how far the
implied plate rim is *inside* the nearest frame edge (negative = off-frame).

    frame   phase                    n   semi-major  centre (y,x)     fit_res  plate_r  edge_margin
    0       racked                   8      99.6     (281.1, 257.3)   ~0.15px   116.1     (partial)
    950     standing, walked out    15     113.9     (348.1, 181.7)    0.25px   132.7     +45.6 px
    1010    visibly deep in squat    8     107.4     (499.5,  84.0)    0.28px   125.2     -41.2 px
    1071    rising                  17     110.3     (357.9,  97.9)    0.44px   128.5     -30.6 px

**During the rep the plate is 25-45 px outside the LEFT edge of a 360 px-wide
frame.** The lifter's walk-out carries the bar toward the left edge, so the rim
— and with it one or two stickers — leaves the picture exactly where the
measurement is taken. The same is visible on `squat_pause_140x4_3` at frame 1147
(bottom of a squat): the plate is clipped at the left and close to the bottom
edge. By contrast `squat_pause_145x4_1` keeps the whole plate in shot at every
phase including the bottom of the squat — rendered and checked by eye.

This is `src/README.md` improvement 2 ("Step the camera back so the whole plate
stays in shot at squat lockout") biting again. It was written for `truth.py`;
it binds the marker tracker too.

### One thing that does NOT reconcile — flagged, not resolved

From the fits above, frame 950 (standing) to frame 1010 (visibly deep) is
151 px of centre travel, which at these scales is **~25 cm**. The IMU
reconstructs `squat_170x1` at **64.4 cm** and `truth.VERTICAL_ROM_M` for squat
is 45-76 cm. Either frame 1010 is not the bottom of the rep, or one of the two
conics is not the plate. **I did not resolve this and it should not be quoted.**
Resolving it is the first thing to do on resuming, because it decides whether
this clip contains a measurable rep at all.

---

## Verdict, and confidence

- **`squat_170x1`: unusable as shot — moderate-to-high confidence.** The
  stickers are present and detectable (0.08-0.39 px while racked), so this is
  not a marker problem. Three independent things go wrong during the rep, and
  none is a code defect: the plate leaves the left edge of the frame by 25-45 px;
  it tips far enough out of plane that the similarity fit degrades to 3.6-6.6 px
  with every marker matched; and the tracker loses lock through the descent even
  with all physical gates relaxed.
- **`squat_pause_140x4_3`: probably unusable — lower confidence.** Same
  selection failure, same clipping at frame 1147, but I never obtained a clean
  hand-seeded eight-point constellation on it (my boxes admitted clutter and
  returned 9-11 inliers), so the positive control was never run. **Run that
  first on resuming.**
- **`squat_pause_145x4_1` and `_140x4_2`: sound.** The constellation sits on the
  plate at every phase, verified by eye on rendered frames, and `validate` is
  silent. Their travel is **59.4 and 60.1 cm** against an IMU ROM of ~69 and
  ~66 — the video reading 9-14% low, which is the open `STICKER_RATIO` /
  `sticker_diameter_m` question and not a tracking one.

**True travel of the four clips:** 59.4 and 60.1 cm for the two good ones;
**not measurable from this footage** for `squat_170x1` and
`squat_pause_140x4_3`, which is the deliverable rather than a gap in it.

**What to re-shoot:** camera further back and framed so the bar stays well
inside the picture through the *walk-out* as well as the rep — the walk-out is
what moves a squat out of frame, and it has no equivalent on bench or deadlift.
The 8-sticker plate itself is fine and needs no change.

---

## Left undone, in priority order

1. **The 25 cm / 64.4 cm contradiction above.** Decides whether `squat_170x1`
   contains a measurable rep. Cheap: hand-fit the conic at the true top and
   bottom of the rep rather than at frames chosen by eye.
2. **The hand-seeded positive control on `squat_pause_140x4_3`**, which was
   never run. Use a tighter box; my `300,640 x 0,300` box at f1147 admitted
   clutter (9-11 inliers for 8 stickers).
3. **`analysis/53_squat_mistracking.png` — claimed and NOT rendered**, so the
   number is still free if the figure is not wanted. It was going to be three
   rows: (a) the shipping constellation drawn over 8 frames of `squat_170x1`,
   showing the rack-upright + one-sticker + floor-fixture triple and the centre
   in empty air; (b) the same for `squat_pause_145x4_1` as the control, all
   seven markers on the plate at every phase; (c) the hand-seeded eight-point
   track's residual and marker count against frame index, with the unrack marked
   — the 0.08 px → 3.6 px step with `n_markers` still 8. The renders exist in
   scratch (see below) and can be transplanted into `src/plot.py`.
4. **Decide what to do about the guaranteed-wrong triangle family** on
   ≥5-sticker footage. Two candidate changes, neither implemented or measured:
   score `_trial_merit`'s residual against the **conic** rather than the
   similarity when the model has ≥5 points; and give it the **motion** term its
   own docstring already claims. My arithmetic says these are worth ~2-2.5x
   together while ~5x is needed to flip `squat_170x1`, so **expect them not to
   rescue these clips** — they would be for correctness on future footage, and
   must be gated bit-identically on all nine existing captures.
5. `truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06 entry (above).
6. `markers.validate`'s docstring claim that a constellation tracker cannot lock
   onto static background (above).

## Repro

Interpreter is plain `python`. Scratch scripts, all written by D2, live in
`/Users/sam/.claude/jobs/366a3089/tmp/d2/` — they are throwaway, not repo code:

    diag1.py <clip>                       per-family merits, run separately
    overlay.py <clip>                     shipping constellation over 8 frames
    ov2.py <clip> ship|hand [i] [seed]    same, or a hand seed with gates relaxed
    handseed.py <clip> <f> <y0 y1 x0 x1>  seed inside a box, then track
    relax.py <clip>                       the gate-relaxation sweep
    plate_at.py <clip> f,y0,y1,x0,x1 ...  conic + edge margin on named frames
    zoom2.py <clip> <f> <y0 y1 x0 x1>     frame-coordinate zoom with det ranks

Renders already produced and worth looking at before re-running anything:
`ov_squat_170x1_*.png` (the furniture triple), `ovship_squat_pause_140x4_3_*.png`,
`ovship_squat_pause_145x4_1_*.png` (the control), `ovhand_squat_170x1_*.png`
(the true constellation held, then lost), `z2_squat_170x1_*_1010.png` (the plate
off the left edge). Each clip is ~1-2 min to decode and track; do not run
several at once on this machine.

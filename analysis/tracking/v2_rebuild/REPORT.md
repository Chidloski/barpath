# v2 tracking, round 2 — the deadlift corpus and `squat_170x1` (2026-08-13)

Owner's report after reviewing round 1: **`squat_170x1_20260806` and the entire
deadlift corpus** are still wrong; the 2026-08-03 three-sticker benches are
non-issues and have been removed from `data_v2`.

Both are fixed. Neither cause was the one predicted, and the evidence for that
is direct rather than inferential — see "What was actually wrong" below.

**Nothing in `src/` was touched.** `HEARTBEAT.md` shows F2 (tidy) still holding
`src/`, `tests/` and `run.py`, with live uncommitted edits in
`.claude/worktrees/tidy`. Under the concurrency protocol I may not write those
paths. The tracker lives in `code/` beside this report; landing it in
`markers.py` is a separate decision for the owner once F2 releases.

## Result

    capture                    cov    travel   band     reps   round 1
    deadlift_150x4_1          0.98    54.0   53-61     4/4      54.0
    deadlift_160x4_2          1.00    51.6   53-61     4/4      51.5
    deadlift_160x6_1          1.00    54.4   53-61     6/6      54.0  (4 of 6 reps)
    deadlift_160x6_2          1.00    54.9   53-61     6/6      69.5  WRONG
    deadlift_170x4_3          1.00    51.6   53-61     4/4      55.1
    deadlift_185x3            0.99    54.6   53-61     3/3      54.7
    deadlift_200x1            1.00    49.4   53-61     1/1      58.1
    squat_170x1               1.00    58.4   61-68     1/1      58.4  (6 teleports)
    squat_pause_140x4_2       1.00    63.4   61-68     4/4      63.4
    squat_pause_140x4_3       1.00    64.3   61-68     4/4      64.3
    squat_pause_145x4_1       1.00    60.5   61-68     4/4      60.4
    bench_117.5x1             1.00    26.0   24-31     1/1      26.0
    bench_92.5x6_1            1.00    27.3   24-31     6/6      27.3
    bench_92.5x6_2            0.98    27.0   24-31     6/6      27.0
    bench_spoto_95x5_1        1.00    25.9   24-31     5/5      25.9
    bench_spoto_95x5_2        1.00    25.3   24-31     5/5      25.3
    ---- out of scope ----
    bench_95x2_20260803       1.00    37.9   24-31     7/2      44.6  3-STICKER

**16 of the 17 clips track and count. The one failure is
`bench_95x2_20260803`**, the old three-sticker plate — the owner removed the
other three of that session but this one is still in `data_v2/video/`. Flagged,
not acted on.

### The rep count is a new gate and it is the one that matters

Round 1 reported `deadlift_160x6_1` at 54.0 cm, inside the band, from a trace
holding **four of its six reps** — the missing two were dropouts between two
surviving lockouts, so the extremes, and therefore the travel, were untouched.
Whole-clip travel cannot see that. The rep count can, it is free because every
capture is labelled in its own filename, and it needs no IMU, no sync and no
referee. `code/reps.py`, output in `reps_gate.txt`.

*Its first run scored 8 of 17 and was wrong.* Every smooth-lift capture read
exactly one short — 6→5, 5→4, 4→3, 1→0 — because a deadlift starts on the floor
and each rep is a peak, while a bench or squat starts at the top and each rep is
a **trough**. That clean off-by-one was the counter's bug, and it doubles as
evidence the traces held the right reps all along.

## What was actually wrong

### Deadlift: the tracker let go at the drop and could not re-acquire

Not motion blur. The dropouts were not scattered — **runs of ~85 frames (2.83 s)
each beginning at a rep's descent**, which is why whole reps vanished.
`deadlift_160x6_1` lost 20.7% of its frames this way.

  * Centre speed in the frames before each loss: **19.8–22.9 px/frame**, against
    a prediction window a few pixels wide.
  * **Detection was never the failing stage.** On the lost frames the plate's
    own stickers rank inside the **global top 15** with unchanged settings, and
    a fresh lattice search restricted to radii near the lock returns the true
    plate as the **top-ranked hypothesis, 6–8 filled slots, radius within
    0.0–1.7% of the lock**, on every frame sampled through every dropout.

The answer sat at rank 1 for 2.8 seconds at a time and nothing asked for it. So
no contrast boost and no blur tolerance were needed; what was missing was
`_reacquire`.

### Squat: the plate is clipped by the frame edge and the fit goes ill-conditioned

The owner's hypothesis, confirmed. Coverage was **1.000 the whole time** —
`_step` succeeded every frame, on the wrong points — which is why no summary
statistic caught it. As the lifter walks out, the inliers collapse from 8 slots
spanning 48° to 5 spanning 183°. A freely fitted circle through a 180° arc has a
well-determined radius and a centre free to slide along the arc's perpendicular,
**which is the fore-aft axis, the one carrying the 1 cm spec**.

## The four changes, and what each cost before it was gated

1. **`_reacquire`** — after 3 misses, re-search radii within 12% of the lock;
   accept on radius, ≥6 filled slots and a reach window.
   `deadlift_160x6_1` coverage **0.793 → 0.998**.

2. **Reach scaled by the speed at the moment of loss, not a constant.** A
   constant wide enough for a dropped deadlift crosses a bench press's whole
   frame. The first version used `MAX_STEP_PX * gap` and made `bench_92.5x6_2`
   re-acquire a plate racked in the background: **50.6 cm of travel on a bench
   press** against 27.0. Speed-scaled: 27.2.

3. **Re-acquisition must prove itself** — track on 6 frames and require 4 to
   hold ≥5 slots before committing. One frame cannot tell the bar's plate from a
   plate racked behind it or a chance constellation on the lifter's shorts.
   Without this `deadlift_160x4_2` went to coverage 1.000 with the circle on the
   lifter's shorts at frame 471, **while travel (59.7 cm) and the rep count
   (4/4) both still looked right**.

4. **`_fit_centre_lattice`** — when the arc spans >100° or fewer than 5 slots are
   filled, hold the radius and take the centre as the median of
   `p_i − r·u(phase + slot_i·45°)`. The owner's prior used directly: with even
   spacing and known radius, *each* visible sticker alone fixes the centre, so
   clipping costs precision rather than conditioning.
   `squat_170x1` max single-frame jump **222.6 px → 14.7 px**, jumps over 40 px
   **6 → 0**, with the real fore-aft range unchanged (48.7 → 48.5 cm).

   It also checks the assumption that licenses it: if the stickers really are
   evenly spaced on one circle, the per-sticker estimates must **agree**, so
   their dispersion is a free test of the slot assignment. Without that check,
   `deadlift_160x4_2` went 51.5 → 58.5 cm with a height trace of spikes.

**Points 3 and 4 are needed together, not separately.** Re-acquisition alone
takes `squat_170x1` to 67.4 cm; the conditioning guard alone leaves the deadlift
dropouts. Both on: 58.5 cm and 0.98–1.00 coverage.

## A trap worth recording: a tracking guard moved the ruler

Adding the guards flipped the chosen radius on four clips —
`deadlift_185x3` 81.4 → 72.0 px, `deadlift_200x1` 85.6 → 96.3 — and **the radius
IS the pixels-to-metres scale**, so travel moved with it: 54.6 → 64.1 cm on a
clip the plate template puts at 52.7.

The cause is real and not a bug in the guards. **A plate carries more than one
ring of eight evenly spaced features**: its cutouts, its bolt circle, and the two
ends of each sticker, since the markers have radial extent and a sub-pixel
centroid can sit at either. On `deadlift_185x3` three radii — 72.0, 81.4, 93.9 —
all give 8 filled slots, 0.90–0.98 coverage and 0.69–0.81 px residual, scoring
6.782 / 6.768 / 6.118. **The 8-fold prior cannot break that tie and should not
be asked to.**

What does break it is how the points *look*. `detect` already scores every
detection for isolated-disc-ness and the seeder was throwing it away:

    clip                sticker ring          every rival ring
    deadlift_185x3      0.339 (r=81.4)        0.077-0.095
    deadlift_200x1      0.267 (r=85.6)        0.035-0.054
    deadlift_160x6_1    0.319 (r=90.4)        0.056-0.076

A factor of 3.6–5×, against score ties of 0.2%, and in each case it picks the
ring that agrees with the independent referee. Applied as a **tie-break within
20% of the top score only** — never as an admission gate, which is the
distinction C21 drew after finding three appearance gates in
`markers.candidates` all sitting at zero margin. `seed.prefer_sticker_ring`.

The right panel of `00_summary.png` shows the runner-up beating the chosen
hypothesis on several clips: that is this tie-break working, left visible.

## The residual signal drops, and they were my own guard (added 2026-08-13)

After the above, the deadlifts still dropped short runs of frames —
`deadlift_150x4_1` 7.1%, the others 1–2% — and the owner asked why. Three
candidate answers, separated by measurement rather than argument:

**1. Is the plate findable on the lost frames?** Running the same restricted
lattice search `_reacquire` uses: most lost frames carry a hypothesis, but with
**5 filled slots, not 6**, and most gaps are **1–3 frames long**. Both point at
the trigger, so `REACQ_AFTER` and `REACQ_MIN_SLOTS` were swept together — this
is also why setting `REACQ_MIN_SLOTS = 5` alone had changed nothing earlier, as
the gaps it would help were too short to reach the trigger. **It bought almost
nothing:** coverage 0.929 → 0.949 on `deadlift_150x4_1` and 0.983 → 0.984 on
`deadlift_160x6_1`, at 2–4× the runtime, with the rep count unmoved. Reverted.

**2. Is it motion blur?** Partly, and less than the frames suggest. Sharpness in
the plate's own crop (variance of Laplacian) puts lost frames only **1.12–1.31×
less sharp** than tracked ones, with peak white top-hat **0.72 → 0.62**. So blur
**thins and shifts** the markers; it does not erase them. The owner's original
hypothesis is right about *these* frames — and was wrong about the 85-frame
dropouts, where the bar sat still on the floor and the stickers ranked in the
global top 15.

**3. It was `LATTICE_AGREE_PX`.** The guard has to sit between two displacement
scales: a wrong slot assignment moves a per-sticker centre estimate by 40–90 px,
while blur moves a smeared centroid by a few. At **4.0 px it was too close to
the blur scale and was refusing real frames.** At 8.0:

    clip                 agree_px    coverage   travel   reps
    deadlift_150x4_1       4 (ship)    0.929     54.0    3/4
    deadlift_150x4_1       8           0.990     54.0    4/4
    deadlift_150x4_1    1000 (off)     1.000     54.0    4/4
    deadlift_160x6_1       4           0.983     54.3    6/6
    deadlift_160x6_1       8           0.998     54.3    6/6
    deadlift_160x6_1    1000 (off)     0.998     54.3    6/6

**Travel is unchanged to 0.1 cm**, so this recovered frames rather than moving
the answer, and disabling the guard entirely buys only a further 0.010 and
0.000 — so 8.0 is where real frames stop being refused, not a slope toward
having no guard. Checked against the three clips the guard was added for:
`deadlift_160x4_2` 51.6, `squat_170x1` 58.4 and `bench_92.5x6_2` 27.0, all
unmoved, against the 58.5 cm and spiked height trace with no guard at all.

`LATTICE_AGREE_PX = 8.0` ships. Coverage is now **0.98–1.00 across the corpus**
and the rep gate reads **16 of 17** — every 8-sticker clip correct.

**The lesson is the one this repo keeps relearning, pointing the other way.**
The guards were added because the tracker was emitting confident wrong answers,
and refusing a frame is the right response to that. But a guard tuned on the
failure it was built for will also refuse the honest hard cases, and it costs
coverage silently — a *rep*, here, since a refused stretch landing on a peak is
invisible to travel and to residual. Only the rep count saw it.

## Blur-tolerant detection (2026-08-14)

The owner asked for the smeared markers to be detected. `_sector_contrast`
scores a candidate as its core minus its **brightest** surrounding sector, which
is what removes points on strip lights and rack edges — and a motion-blurred
sticker is a short streak, so it has two bright opposite sectors and is removed
for exactly the same reason. Ignoring the two brightest sectors instead of one
recovers it. Measured on `deadlift_150x4_1`'s worst drop, filled lattice slots
on the known circle over 13 frames: **strict 34, smear-tolerant 49 (+44%)**, and
on one frame 6 against 0.

**The relaxed candidates are kept in a separate, flagged block, not merged**,
and that is the part that makes this safe. Ignoring two sectors is precisely
what makes a long bright line admissible again, so the list is noisier. The
clip-level search never sees it — seeding decides *which* circle is the plate,
and a noisier candidate list can only make that worse. Tracking already knows
where the plate is to within a few pixels and has the lattice to check against,
so there the extra clutter is harmless, and `_step` asks for the relaxed block
only after the strict one has failed. **The relaxed block can therefore only
recover frames, never change which plate is chosen** — confirmed: every radius
and every travel figure is unchanged to 0.1 cm across all 17 clips.

## `deadlift_150x4_1` (2026-08-14)

Its residual defect was fore-aft strays, not lost frames — up to **19.8 cm** on
the axis carrying a 1 cm spec. Cause: **3 points is too little evidence for the
lattice fit.** All five stray frames were 3-slot or 5-slot, the two worst both
3. With three points and 8 px of slack a lattice-consistent fit exists on
clutter at a centre 100 px from the truth, and the agreement test cannot object
because the three estimates agree *with each other*. `LATTICE_MIN_PTS = 4`.

Those two changes need each other: `LATTICE_MIN_PTS = 4` alone drops coverage
0.990 → 0.957 and *raises* strays from 5 to 14, because refused frames send the
tracker into re-acquisition. With the relaxed block: **0.980 coverage, 5 strays,
worst 19.8 → 14.3 cm**, rep count 4/4.

**Two further guards were built, measured, and thrown away** — recorded because
the measurement is the useful part:

  * *A fit-residual cap.* The strays carry 3.2–5.8 px residual against a 1.00 px
    median, so a cap looked obvious. At 3.0 px it costs `deadlift_150x4_1` 2.5%
    coverage and `deadlift_200x1` 1.1%, removes 3 of 5 strays and **leaves the
    worst one untouched at 14.3 cm**; at 4.5 px the rep count *drops to 3 of 4*.
    Non-monotonic in its own threshold, so it is interacting with re-acquisition
    rather than measuring anything. Removed.
  * *A tighter `MAX_STEP_PX`.* 75 px is twice the fastest motion in the corpus
    (39.2 px/frame), so tightening to 50 looked free. **No effect at all** — and
    that is informative: the strays are not jumps, they are a slow drift.

**What remains on `deadlift_150x4_1`, stated honestly: 5 frames of 705 (0.7%),
at t = 22.87 s and 23.37–23.47 s in a 23.5 s clip**, i.e. the final lockout and
the last four frames, reading up to 14.3 cm fore-aft. It touches the last rep's
lockout, not any pull. Every other deadlift has **zero** frames over 8 cm. Not
fixed, and I would not add a third guard for it without understanding why that
one lockout differs.

## Round 3 — the artifacts and the gaps (2026-08-14)

The owner reported that `deadlift_150x4_1` and `deadlift_160x4_2` still showed
artifacting and signal drops. Both were real, both had causes, and **neither was
the cause the section above assumed.**

### The gaps were the residual filter, i.e. mine

Splitting the missing frames by cause settles it:

    clip                 genuine track loss   dropped by the rms filter
    deadlift_150x4_1     14 (two runs of 7)   34, in 22 runs of 1-4 frames
    deadlift_160x4_2      2 (two singles)     26, in 15 runs

So the drops were overwhelmingly self-inflicted. And the filter was not even
selecting for the fault it was built for: on `deadlift_150x4_1` the fit residual
correlates with the actual fore-aft error at **r = +0.007**. It dropped 14
frames deviating under 2 cm while leaving the worst frame in the clip — 14.0 cm,
residual 1.87 px, under the 2.49 px cap. On `deadlift_160x4_2` the same
correlation is **+0.505**, so it worked by coincidence on one clip and not the
other, which is what disqualifies it as a mechanism.

Removing it improved coverage on **8 of 8 clips measured**, by up to 5.6 points,
with whole-clip travel changed by at most 0.3 cm and no rep count moved.

### The artifacts were unverified multi-start seeds

`_reacquire` proves itself by trial-tracking; the **starts never did**, though a
start is trusted for a whole direction of travel and a re-acquisition only for a
few frames. There was no argument for the asymmetry. `deadlift_150x4_1`'s worst
frame is the *last frame of the clip*, reached by a backward pass from a start
planted where the lifter is already re-racking.

`_start_ok` applies the same trial-track, in whichever direction has room, and
accepts a start too close to both ends to verify rather than refusing it. Worst
frame **14.0 → 5.5 cm**, inside C27's 4.3–6.2 cm band for real deadlift
fore-aft, for 3 frames of coverage. It is **inert on every clip that did not
need it** — identical output on `deadlift_160x4_2` and `deadlift_160x6_1`.

### Two fixes measured and rejected

*Radius pinning.* The artifact frames sit at a radius inflated 3–4% (clean
median 96.1 px against 99.3 on the strays), and `_step`'s guard only rejects
outside 0.75–1.33× the lock, so it never fires. Legitimate variation is
1.05–1.25% p2–p98 on the two cleanest clips, and the seed radius reproduces the
clean median to 0.05% on 5 of 6 — so holding the radius and fitting the centre
alone looked well founded. **It was not the cause.** Pinned, clutter simply
drags the centre at the locked radius: fore-aft 9.1 → 8.4 cm and the worst frame
*unmoved* at 14.6. It cost residual on every clip — `bench_spoto_95x5_1` 0.56 →
**2.85 px** on a path it did not change at all — because `r_lock` is 1.6% off on
bench and pinning bakes that in. Radius inflation is a **correlate** of clutter
admission, not its cause.

*An appearance veto.* The detector scores every point for `blob`, `whiteness`
and `tophat`, and `_step` is handed y,x only. The admitted clutter is genuinely
dimmer — worst-inlier sector contrast 0.036 against 0.164 on clean frames, a
4.5× separation, replicated at 2.3× on the second clip; whiteness carries no
signal at all (ratio 0.99). But a veto cannot use it. At a 0.10 cut the artifact
frames retain a median of **2 inliers of 6**, below the 4 a fit needs, so it
*deletes* those frames rather than repairing them — the residual filter's
mistake with a better statistic — while on `deadlift_160x4_2` it removes almost
nothing (7 of 8 inliers survive). It also costs 16–19% of motion-blurred frames.

The table does contain a better discriminator, recorded for whoever needs it:
**blur dims all eight stickers together, clutter admission produces a mixed
constellation.** Bright fraction is 33% on `150x4_1`'s artifact frames against
100% on its blurred and clean ones. Not built, because after `_start_ok` there
was not enough left to justify it.

### What remains

One stray frame per clip, and one of them is not an error. Rendered zoomed with
the fitted circle and inspected rather than judged from statistics:

  * `deadlift_160x4_2` **f579, −6.3 cm: a CORRECT fit.** Eight slots evenly
    round the plate, circle on the hub. That is the bar moving, and it sits
    inside C27's band. It must not be "fixed".
  * `deadlift_160x4_2` **f720, +6.6 cm: a genuine artifact.** Four inliers
    spanning a 132° arc, circle slid off the plate — the exact failure
    `_fit_centre_lattice`'s docstring describes. Pre-existing: spread 228° was
    never "well-conditioned", so it takes the same path in every arm. The
    lattice fit has a dispersion check but **no angular-spread requirement**.
  * `deadlift_150x4_1` **f470, +5.6 cm**, five slots.

Whole-corpus state after round 3: **16 of 16 clips track**, coverage 0.97–1.00,
eight filled slots median on every one, none flagged implausible, and the rep
gate reads **16 of 16 captures count correctly**.

*The corpus is 16 rather than 17 because `bench_95x2_20260803` — the last
three-sticker clip, and round 2's only failure — has since been removed from
`data_v2/video/`. The round-2 result table above is left as it was measured.*

### The pipeline against the rebuilt referee

Re-scored through `metrics.vs_truth` with the rebuilt paths passed in as a path
dict, so nothing in `src/` was touched.

**WHICH PIPELINE THIS IS, and it is not the one `CLAUDE.md` describes.** This
worktree is at **`ae14c40` (C27-era)**, not at the `dded7f1` the session's git
status reported. Two consequences, both checked rather than assumed:

  * **Step 6 is OFF and cannot be turned on here.** `correct.WRIST_OFFSET_M`
    does not exist in this branch and `pipeline.run`'s `wrist_offset` still
    defaults to `None`; `70b2a63` is not an ancestor of HEAD. **So every figure
    below is a WATCH-path number, not a bar-path one**, and it belongs against
    `CLAUDE.md`'s "d OFF" column, never its "d ON" column.
  * **The segmenter predates C31a.** `_longest_cadence` still carries
    `tol=1.45` and the global-spread rule; `a2494b4` is not in this branch.
    So any rep count below that disagrees with a label is the *known*
    pre-C31a behaviour, not a new defect.

    capture                 reps   h_rms   null  beats  v_rms  sign  vidROM  vidFA
    bench_92.5x6_1           6/6    1.09   3.75   3.43   2.92     0    25.8    7.2
    bench_92.5x6_2           6/6    1.76   4.11   2.34   2.34     0    26.2    8.0
    bench_spoto_95x5_1       5/5    1.28   3.23   2.53   2.91     0    24.6    5.8
    bench_spoto_95x5_2       5/5    3.19   3.67   1.15   2.89     0    23.9    6.3
    deadlift_150x4_1         4/5    5.26   1.78   0.34  27.56     2    53.6    6.0
    deadlift_160x4_2         4/4    4.17   1.50   0.36   4.91     1    51.9    4.9
    deadlift_160x6_1         6/6    8.12   1.54   0.19   3.59     1    54.6    4.9
    deadlift_160x6_2         6/6    4.56   1.54   0.34   3.66     1    54.3    4.4
    deadlift_170x4_3         4/4    5.46   1.39   0.26  11.99     1    51.5    4.8
    deadlift_185x3           3/3   11.55   1.55   0.13   1.74     0    53.8    6.0

Not scored: `bench_117.5x1` (a single — `bench_sync` finds no lag with enough
overlap) and `deadlift_200x1` (needs ≥2 landings). Squat is refused by
`vs_truth` itself.

Three things follow, and the second is the one worth acting on.

**The referee independently reproduces C27.** Per-rep video fore-aft is
**4.4–6.0 cm on all six deadlifts**, against C27's 4.3–6.2 — and three of those
six are new 2026-08-08 captures C27 never saw. That is the strongest evidence
available that the rebuilt tracking is right.

**The referee rebuild barely moves the SCORES, and that is the honest result.**
Against `CLAUDE.md`'s d-OFF column — the like-for-like comparison, since step 6
is off here — the rebuilt referee reproduces the old marker tracker closely:

    capture              CLAUDE.md d OFF      rebuilt referee
    bench_spoto_95x5_1     1.17 / 2.65          1.28 / 2.53
    bench_spoto_95x5_2     2.76 / 1.16          3.19 / 1.15
    deadlift_160x6_1       7.22 / 0.23          8.12 / 0.19
    deadlift_160x6_2       4.55 / 0.34          4.56 / 0.34
    deadlift_185x3        11.44 / 0.14         11.55 / 0.13

**An earlier draft of this section claimed the rebuild flipped both paused
benches past the null, from 0.88 and 0.72 to 2.53 and 1.15. That was wrong.**
Those two figures are `CLAUDE.md`'s **d-ON** values, and this branch cannot
apply `d`. The benches were already above the null with `d` off (2.65, 1.16);
the flip `CLAUDE.md` records is caused by turning step 6 ON, exactly as it says,
and nothing here bears on it. P2's referee-versus-pause tension is **untouched
by this work** and remains open.

What the rebuild is worth is therefore not re-scoring the captures that already
scored. It is the clips that were **outright mis-tracked** — the two squats
`CLAUDE.md` records at 14.0 and 24.7 cm of travel, now 58.4 and 64.3 — and the
strays on `deadlift_150x4_1` and `_160x4_2`. A referee that agrees with the old
one where the old one worked, and is right where it did not, is the correct
outcome; it is just a narrower claim than the one first written here.

**Deadlift is untouched by the fix, which is itself a result.** `beats_null`
0.13–0.36 against `CLAUDE.md`'s 0.14–0.35 for the three captures it holds. A
better referee did not rescue it, so P2's deadlift horizontal problem is in the
reconstruction, exactly where P2 says it is. Sign disagreement did improve —
0–2 reps per set against the old 4/6 and 2/6.

**Rep-window trouble on three captures — but the segmenter here predates
C31a**, so this is not evidence of a new defect and must be re-run on a branch
containing `a2494b4` before it is called one:

  * `deadlift_150x4_1` segments **5 reps** where the label and the video both
    say 4, with a vertical rms of **27.56 cm**; `deadlift_170x4_3` reads 11.99
    against 1.7–4.9 elsewhere.
  * `squat_pause_140x4_2` and `_3` segment **3 reps of 4** — which is precisely
    the failure C31a diagnosed (a paused squat's cadence lengthens rep by rep,
    and the global-spread rule cannot admit it) and fixed with the local-drift
    rule and `tol=1.50`. Seeing it here confirms the branch, not a regression.

### Squat, and it is INDICATIVE ONLY

`vs_truth` refuses squat by a hardcoded check whose stated reason describes the
old `data/video/` template footage. `code/squatcheck.py` bypasses it in-process
the way C31 did, routing squat through the bench branch. It does **not** lift
the refusal, and three unresolved problems ride along with every figure:
`bench_sync` is unvalidated on squat and a walkout hands its correlation a large
non-rep feature bench does not have; squat has **no phase anchor** (P1), so a
window half a rep out of step would be invisible to all of it; and the two
instruments already disagree on the vertical.

    capture                reps   h_rms   null  beats  v_rms  vidROM  imuROM  vidFA
    squat_pause_140x4_2     3/3    2.70   3.33   1.23   4.62    63.4    65.7    7.1
    squat_pause_140x4_3     3/3    3.95   3.86   0.98   7.52    64.1    70.1    8.6
    squat_pause_145x4_1     4/4    3.44   3.97   1.16   7.67    60.2    68.5    7.3

`squat_170x1` is refused correctly — a single, and `bench_sync` needs the rep
cadence to separate a whole-rep ambiguity from a real one.

### RE-RUN ON `c29-jump-state` (dded7f1) — THESE ARE THE AUTHORITATIVE NUMBERS

Everything above this line was scored with the audit worktree's C27-era `src/`.
Re-run against an export of `c29-jump-state`, which carries **C31a's segmenter
(`tol=1.50`)** and **step 6 on by default (`wrist_offset="auto"`)** — the
pipeline `CLAUDE.md` describes. `code/vspipe.py` and `code/squatcheck.py` now
take `BARPATH_SRC_ROOT` and print the checkout and the step-6 default on every
run, so provenance is on the output rather than in anyone's memory. That is what
went wrong the first time.

    capture                 reps   h_rms   null  beats  v_rms  sign  vidROM  vidFA
    bench_92.5x6_1           6/6    1.23   3.75   3.05   2.21     0    25.8    7.2
    bench_92.5x6_2           6/6    1.61   4.11   2.55   1.67     0    26.2    8.0
    bench_spoto_95x5_1       5/5    3.64   3.23   0.89   2.11     0    24.6    5.8
    bench_spoto_95x5_2       5/5    2.41   3.67   1.52   2.13     2    23.9    6.3
    deadlift_150x4_1         4/5    5.28   1.78   0.34  30.11     2    53.6    6.0
    deadlift_160x4_2         4/4    3.98   1.50   0.38   4.90     1    51.9    4.9
    deadlift_160x6_1         6/6    7.52   1.54   0.20   3.54     1    54.6    4.9
    deadlift_160x6_2         6/6    4.40   1.54   0.35   3.69     1    54.3    4.4
    deadlift_170x4_3         4/4    5.54   1.39   0.25  12.14     1    51.5    4.8
    deadlift_185x3           3/3   10.72   1.55   0.14   1.69     0    53.8    6.0

**THE REBUILT REFEREE RESOLVES HALF OF P2's DISSENT, AND ISOLATES WHICH HALF.**
Against `CLAUDE.md`'s d-ON column:

    capture              CLAUDE.md d ON     rebuilt referee
    bench_spoto_95x5_1     3.54 / 0.88        3.64 / 0.89     unchanged, still under
    bench_spoto_95x5_2     4.45 / 0.72        2.41 / 1.52     CROSSES THE NULL
    deadlift_160x6_1       6.65 / 0.25        7.52 / 0.20
    deadlift_160x6_2       4.39 / 0.35        4.40 / 0.35
    deadlift_185x3        10.61 / 0.15       10.72 / 0.14

So of the two paused benches behind "`d` helps under the template referee and
hurts under the marker one", **`_2` was a referee artefact and `_1` is not.**
`_1` reproduces the old marker referee to 0.01 and still loses to the flat line
with `d` applied. That is a sharper statement than "the split is by referee",
and it names `bench_spoto_95x5_1` as the single capture to explain.

Two independent signs `d` is behaving as recorded: bench vertical improves on
**all four** captures with step 6 on (2.92→2.21, 2.34→1.67, 2.91→2.11,
2.89→2.13), the ~20–25% effect `CLAUDE.md` reports; and the three deadlifts land
within 0.01–0.9 cm of the recorded d-ON figures. One cost, recorded:
`bench_spoto_95x5_2`'s sign disagreement goes 0 → 2 reps with `d` on.

**Squat on the same branch, still INDICATIVE ONLY, and all four reps now count:**

    capture                reps   h_rms   null  beats  v_rms  vidROM  imuROM  vidFA
    squat_pause_140x4_2     4/4    2.46   3.22   1.31   6.51    62.7    67.8    6.7
    squat_pause_140x4_3     4/4    3.87   3.67   0.95   9.72    63.5    71.9    8.2
    squat_pause_145x4_1     4/4    3.13   3.97   1.27   9.24    60.2    70.7    7.3

`squat_pause_140x4_3` **is newly scoreable**: C31's bypass could not use it at
all, because the old tracker put it at 24.7 cm of travel. That capture is what
the rebuild adds to squat, rather than a change to the two that already worked.

Squat sits at **0.95–1.31** — around the null, between deadlift's 0.13–0.38 and
bench's best. Its vertical is **6.5–9.7 cm rms**, far worse than bench's
1.7–2.2, and video reads 7–15% below the IMU on ROM (62.7/67.8, 63.5/71.9,
60.2/70.7). None of that is a result: `bench_sync` remains unvalidated on squat
and squat still has no phase anchor.

**`deadlift_150x4_1` over-counts under C31a's segmenter too** — 5 windows for a
labelled and video-confirmed 4 reps, with 30.11 cm vertical rms. This no longer
has an old-branch explanation and is a real open defect. `deadlift_170x4_3`'s
12.14 cm vertical stands beside it. Both are 2026-08-08 captures, which postdate
P1's 124/124 counting claim.

So squat sits **at the flat-line null**, 0.98–1.23: better than deadlift's
0.13–0.36 and well short of bench's best. The vertical disagreement narrows
under the rebuilt tracking — video reads 3–12% below the IMU (63.4 vs 65.7,
64.1 vs 70.1, 60.2 vs 68.5) against the ~15% C31 measured — but it does not
close, and the rep counts above mean two of these three are scored on 3 windows
of a 4-rep set. **Read the whole table as a reason to referee squat properly,
not as squat's error.**

## Open

  * `deadlift_160x4_2` f720 and `deadlift_150x4_1` f470 — one stray frame each.
    The lattice fit accepts 4 points on a narrow arc with no angular-spread
    requirement. Pre-existing and untouched.
  * `deadlift_150x4_1` over-counts in the IMU segmenter (5 vs 4) and reads
    27.56 cm vertical rms; `deadlift_170x4_3` reads 11.99. `src/`, not here.
  * `deadlift_200x1` tracks cleanly but reads 49.4 cm travel against
    `truth.VERTICAL_ROM_M`'s 53–61 deadlift band — below the band, above the
    implausibility gate, so nothing catches it.
  * `metrics.vs_truth` still refuses squat by a hardcoded check whose stated
    reason describes the old `data/video/` template footage. All four v2 squats
    now track at 1.000 coverage. Lifting it is real work — squat has no phase
    anchor and `bench_sync` is unvalidated there.
  * `bench_92.5x6_2` retains 1.8% lost frames.
  * The relaxed block costs ~25% more detection time and 60 extra rows per
    frame in the cache.
  * **`STICKER_RATIO = 0.858` is still transferred, not measured**, and every
    metre figure scales linearly with it. The concentric-ring finding above
    makes this sharper rather than softer: the sticker circle's radius is
    genuinely ambiguous to ±13% from geometry alone. **A tape across the sticker
    circle settles all 16 clips at once** and is the single highest-value
    measurement available here.
  * `truth.STICKER_PLATE_DIAMETER_M` still has no 2026-08-06 entry (C32).
  * Nothing committed.

## How to run

    cd /Users/sam/Desktop/barpath
    python3 analysis/tracking/v2_rebuild/code/detect.py data_v2/video/*.mov  # cache
    python3 analysis/tracking/v2_rebuild/code/make_figures.py                # figures
    python3 analysis/tracking/v2_rebuild/code/reps.py                        # rep gate

Detection caches to npz, so geometry can be re-run without re-decoding. A clip
takes ~30 s to detect once and 35–115 s to track — slower than round 1, because
a rejected re-acquisition costs a Hough and the guards reject far more often.

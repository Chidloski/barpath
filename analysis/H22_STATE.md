# H22 — the deadlift impulse: a pre-pull rest anchor, and two ideas that fail (2026-08-19)

Owner's task, verbatim: *"explore new ways to fix deadlifts. For deadlift, see
whether you can use the impulse to your advantage or whether by overlapping reps
slightly you can more easily find a rest period. You know that the bounces at the
drop will decrease and the watch will move very little during the ringing."*

Measurement only in the reconstruction sense — **no file under `io`, `calibrate`,
`orient`, `integrate`, `segment`, `correct`, `project` or `pipeline` was
written**, so no branch. What landed is new code in `src/oracle.py`, gates in
`tests/test_oracle.py`, and `analysis/72_deadlift_rest_anchor.png` from
`analysis/72_deadlift_rest_anchor.py` and its committed `.json`.

Everything is scored through `metrics.vs_truth` against `vtrack`, with the
pipeline as it ships — step 6 `d` on, H8's step 5b on, H9's anatomical axis,
B4's sign, H14's tape scale.

**Every number here was measured against a read-only snapshot of `src/` at
`e5c9427`.** A second agent (H21) was editing `src/metrics.py` live to retire
`markers.py`; its work is meant to be numerically inert on `data_v2/`, but a
referee that can change under a measurement is not a referee. The snapshot is
`git archive e5c9427 src`, imported ahead of the working tree. Nothing here
reads the working copy of `metrics.py`.

**Exclusions, applied by hand and stated everywhere.** Three of the twelve
deadlifts are out: `deadlift_160x6_1_20260818` (lifted in straps, H20 measured
the watch moving), `deadlift_170x4_3` (its clock fits 22.8% drift, G3), and
`deadlift_210x1_20260815` (miscounts a labelled single, H15). That leaves **8
scoreable captures and 36 reps**; `deadlift_200x1` has one landing and cannot be
synced by landings at all, so it appears in the anchor work and not in the
scores. Every table is also given on all ten for comparability with H19.

## The one that works: there IS a rest before the first pull

H19's blocker, restated: `segment.rest_instants` answers *"when did the bar come
to rest AFTER each landing"*, so n impacts give n rest instants and
`oracle.rest_windows` pairs them into **n-1** windows. Rep 1 of every set is
therefore never inside a window. On this corpus C29's frame scores **23 of 36
reps**, and H19 recorded that as the single reason C29 cannot ship.

**The missing boundary is not missing from the signal.** Immediately before the
first pull the bar is on the floor and the lifter is set. `oracle.prepull_rest`
takes the quietest sample in the 3 s before the segmenter's first rep start, on
`rest_instants`' own accel-plus-gyro variance score — raw signal only, no
attitude, no integration. On **9 of 9** deadlifts it scores **0.04-0.71** against
**0.17-7.15** for that capture's post-impact rest instants. It is the quietest
anchor in the capture, on every one, and it lands 0.01-0.90 s before the pull.

That is now gated per capture:
`test_the_prepull_anchor_is_quieter_than_every_rest_it_joins`.

### It is EXACTLY additive, which is what makes it evaluable

Prepending the anchor adds one window and leaves every later window
**bit-identical**. Measured on all deadlifts and gated
(`test_the_prepull_anchor_leaves_every_later_window_BIT_IDENTICAL`), and the
algebra says why: the correction it enables lives entirely inside the new first
window, and what leaks past it is a constant velocity offset — linear in
position, and removed exactly by step 7's per-window line.

    capture              C29's windows, per-rep h rms      with the pre-pull anchor
    150x4_1 0808         [3.67, 3.83]                      [4.62, 3.67, 3.83]
    155x5_1 0815         [5.52, 2.66, 2.65, 5.83]          [6.76, 5.52, 2.66, 2.65, 5.83]
    160x4_2 0808         [1.43, 1.64, 7.67]                [4.95, 1.43, 1.64, 7.67]
    160x5_2 0815         [1.61, 2.38, 1.34, 4.75]          [2.25, 1.61, 2.38, 1.34, 4.75]
    160x6_1 0804         [1.80, 2.51, 1.00, 2.22]          [4.25, 1.80, 2.51, 1.00, 2.22]
    160x6_2 0804         [1.57, 1.06, 1.56, 1.19]          [1.56, 1.57, 1.06, 1.56, 1.19]
    185x3 0804           [1.58]                            [2.89, 1.58]
    190x3 0818           [4.13]                            [3.34, 4.13]

**So the recovered rep's error is attributable to the recovered rep, and it is
the hardest rep of the set on 4 of 6 sets with three or more windows.** Read
that against H19's confound-3 test, which found rep 1 was *not* systematically
easier in the SHIPPING frame: it is not that rep 1 is an easy rep C29 was
skipping, it is that the first rest-to-rest window is a hard window. Part of
C29's headline was nonetheless a coverage effect — restoring the rep takes the
median from **2.00 to 2.77 cm**, which is most of C29's margin over shipping.

## The second half: a rest PERIOD, not a rest instant

The owner's word was "period", and the bar really does dwell. `oracle.still_mask`
marks samples where smoothed |omega| < 0.6 rad/s and smoothed |a| < 4 m/s² — raw
gyro and raw user acceleration, nothing derived. After a floor landing that run
lasts a **median 0.96 s** (37 landings, range 0.28-3.25). The pipeline has only
ever used the single quietest SAMPLE inside it.

Averaging the reconstruction's velocity over the whole interval is a
lower-variance read of the same observable C28b and C29 use, and it is what buys
back the cost of the recovered rep. The clean 2x2, all four arms carrying the
pre-pull anchor, width 0.30 s, median horizontal rms in cm:

    boundary \ dv estimator      at the INSTANT     over the PERIOD
    the rest instant                 2.98               2.70
    the period's midpoint            2.98               2.14

**Neither change helps alone.** That is C29's own shape repeated — C29 needed
both the moved windows and the correction, and neither worked by itself — and it
is the strongest structural thing in this task.

## The ladder, n = 8 (exclusions applied)

    arm                                        h rms   beats_null   reps    null
    shipping (step 7 on impact windows)         2.78      0.68      36/36   1.00x
    rest windows, NO correction (control)       8.52      0.22      23/36   1.28x
    C29, rest instants, 0.20 s                  2.00      0.95      23/36   1.28x
    C29 + the pre-pull anchor                   2.77      0.78      31/36   1.13x
    period frame + period-averaged dv, 0.30 s   2.14      0.84      31/36   0.97x

    frame-internal, control vs treatment:  C29  8 of 8, Wilcoxon p = 0.008
                                           H22  8 of 8, Wilcoxon p = 0.008
    against shipping:                      C29  5 of 8, p = 0.195
                                           H22  6 of 8, p = 0.383

On all ten captures — H19's frame, so the three excluded ones are back in and the
numbers are directly comparable to `TASKS.md` H19:

    arm                     h rms   beats_null   reps     vs shipping
    shipping                 3.31      0.57      46/46      —
    C29                      2.88      0.83      30/46      7 of 10, p = 0.049
    H22                      2.76      0.76      40/46      8 of 10, p = 0.105

**Read the coverage column before the accuracy column.** The honest statement is
not "C29 got worse" but "the coverage blocker is closed at a cost of 0.14 cm":
23 of 36 reps becomes 31 of 36, and 30 of 46 becomes 40 of 46.

### One of H19's two confounds is REMOVED rather than inherited

H19 flagged that C29's frame inflates `null_h_rms` by a median **1.28x**, larger
on 9 of 10 captures, which flatters `beats_null` — C12's shape, where a
referee's own invented motion inflated the null and made the pipeline look
better. **This frame's null is 0.97x shipping's.** So H22's `beats_null`
0.68 -> 0.84 is like-for-like where C29's 0.68 -> 0.95 was not.

The other confound is only partly closed. C29's frame drops rep 1 of every set;
H22's drops the LAST rep of about half of them, for a reason that is a property
of the lift and not of the estimator — see below.

### And it is not D1's degenerate case

D1 was rejected for converting every capture into approximately the flat-line
null (`beats_null` entering at 0.13-5.39 and leaving at 0.76-1.16). H22's
`beats_null` spreads **0.35-1.65** across the eight, wider than shipping's
0.43-0.93, with captures separating rather than converging. It is adding
information, not deleting a channel.

## What cannot be recovered, and why it is not an estimator problem

**The final rep of a set has no rest anchor after it and never will.** The
lifter releases the bar and stands up, so:

* `segment.rest_instants` refuses the final impact on 4 of 12 captures through
  its `max_accel` gate (mean |a| 9.3-19.6 m/s² there against 1.2-3.5 for the
  interior landings);
* `still_mask` finds no still interval after it at all on 4 of 9;
* `oracle.ring_duration` never settles inside its 1.2 s search on exactly those
  landings, reached from raw acceleration by a third, unrelated route.

Three independent detectors agree on the same landings, which is the strongest
evidence in this task that the refusal is real rather than a threshold. It is
gated: `test_the_ringing_settles_except_where_the_lifter_lets_go` asserts every
INTERIOR landing settles, so if a detector ever drifts the disagreement surfaces.

`deadlift_200x1` is the extreme case and is worth naming: one landing, no rest
instant, no still interval after it, so it has **zero** rest-to-rest windows with
or without the pre-pull anchor. A single cannot be scored in this frame at all.

## The two ideas that FAIL, in enough detail that nobody retries them

### 1. "The watch will move very little during the ringing" cannot be spent

This is a real and correct observation and it does not convert into a
correction. Two shapes were built, both on top of C29's frame, both scored
against the same referee:

    correction shape                            width 0.10  0.20   0.30   0.40
    C29: one constant accel, zeroes dv only         2.68   2.00   2.25   2.55
    + zero NET DISPLACEMENT (accel linear in t)     6.27  11.30  16.33  22.60
    clamp the horizontal velocity to zero           8.62   4.76  11.23   7.49

**The structural reason, which is the part worth carrying.** Step 7 removes an
independent line per window, so a CONSTANT velocity error is already absorbed
exactly. An absolute "the watch did not move" statement is therefore invisible to
the metric — and imposing it *inside one window only* does not remove a constant,
it manufactures a kink at the window's edge, which is precisely the error shape
C29 exists to remove. The reconstruction claims **~1 m/s of horizontal velocity**
through a period the bar is provably on the floor (drawn in `analysis/72` panel
A2), and none of that magnitude is actionable; only its CHANGE between two rest
periods is. That sharpens C28b: the impact is informative about the horizontal,
but the informative part is a difference and nothing else.

**A second, smaller reason, and it is a factual correction to the premise.** The
correction window starts at the impact ONSET, and the bar is still moving at
0.4-1.0 m/s there — it takes ~150 ms to stop (`segment.rest_instants`). So over
the 0.20-0.40 s window that actually works, "the watch barely moves" is false at
the start of it. The watch is still for the ~0.5 s AFTER the ringing, which is
the interval `still_mask` finds and which the period-averaged `dv` above already
uses.

### 2. "Overlapping the reps slightly" is the worst of three boundary choices

Taken literally: let window j run from the START of still period j to the END of
still period j+1, so consecutive windows share a whole still interval. Against
having them meet at the midpoint, and against excluding the still intervals
entirely:

    boundary placement, all at width 0.30 s   h rms   beats_null
    meet at the period midpoint                2.14      0.84
    exclude the still intervals ("tight")      2.59      0.75
    OVERLAP by a whole still interval          2.93      0.75

(at width 0.20 s the first two swap by 0.07 cm — 2.54 against 2.47 — so
"midpoint beats tight" is not a robust ordering and is not claimed. "Overlap
loses to both" is, at every width tried.)

Overlapping loses. The mechanism is the same one as above: a window that
overlaps its neighbour contains samples that two independent detrend lines both
claim, and the two lines disagree there, so the shared stretch is reconstructed
twice and inconsistently. C29 already established that step 7's power comes from
per-rep INDEPENDENCE; overlapping windows is the other way of breaking
independence, after `detrend_knots`' continuity broke it in 2026-08-05.

**What DID survive from that half of the task is the word "period" rather than
the word "overlap"** — see the 2x2 above.

### 3. The bounces decay, measurably, and it buys nothing

`oracle.ring_duration` measures the settle time from raw |a| alone: **median
0.61 s** over 37 landings, range 0.41-1.20, with a bounce train of 13-26 peaks
decaying at a median peak-to-peak ratio of **0.83**. The owner's physical
description is exactly right.

Two things it is good for: it separates a landing you can anchor from one you
cannot (above), and it says the correction window is about **half** the ringing —
C29's optimum is 0.20-0.30 s against a measured 0.61.

**And one thing it is not good for.** Setting the width per landing to a fixed
fraction of the measured ringing is no better than a single constant: 0.50x ring
gives 2.17 cm against 2.14 for a flat 0.30 s, on the same eight captures. Sweeping
the fraction (0.20, 0.30, 0.40, 0.50, 0.75, 1.00) gives 2.73, 2.74, 2.45, 2.17,
2.88, 3.56 — a minimum in the same place a constant already sits. **The ringing's
LENGTH carries no information the constant does not already have**, which is a
small negative but a clean one: it says the variation in settle time between
landings is not the variation that matters.

## Verdict

**Recommend:** treat `oracle.jump_period_windows` as the current best deadlift
candidate in place of `oracle.jump_rest_windows`, on the strength of the coverage
and the removed null confound rather than on the accuracy, which is within noise
of C29's. Do not ship either yet.

**Reject:** the zero-displacement and velocity-clamp corrections; overlapping
windows; a per-landing adaptive correction width. All three are measured above
with the mechanism named.

**What would settle it, unchanged from H19 and now cheaper:** more deadlifts.
Eight captures cannot resolve a 0.5 cm median difference and ten cannot either —
H19 watched two new captures move the same test from p = 0.195 to p = 0.049. The
frame-internal case is decisive at 8 of 8 and p = 0.008; the case against
shipping is not, and no amount of re-analysis of these eight will make it so.

**What would settle it and is NOT more data:** a decision about the last rep. The
pre-pull anchor makes the frame lose the last rep of about half the sets instead
of the first rep of all of them, which is strictly better but is still a product
question — the owner's call, exactly as H19 said about rep 1.

**One thing worth chasing that this task did not:** the reconstruction's ~1 m/s
of horizontal velocity during a period the bar is provably still is enormous, it
is visible with no video in the frame, and step 7 absorbs all of it. That
absorption is why it cannot be used as a correction — but it is also a
video-free measurement of how much drift the pipeline is carrying, per rep, on
every deadlift. Nobody has quoted it as a diagnostic.

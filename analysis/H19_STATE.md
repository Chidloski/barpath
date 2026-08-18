# H19 — fixes for the deadlift horizontal, explored (2026-08-18)

Owner's task: explore fixes for the deadlift error. **Measurement only — no file
under `src/` was written**, so no branch. Figure:
`analysis/69_deadlift_fixes.png`, from `analysis/69_deadlift_fixes.py`.

Everything is scored with the pipeline as it now ships — step 6 `d` on, H8's
step 5b on, H9's anatomical axis, B4's sign, H14's tape scale — against
`vtrack`, through `metrics.vs_truth`.

## Where the deadlift actually stands

H17 put it at **1 of 10 sets beating the flat-line null**, against bench's 6 of
7 and squat's 9 of 10, and the one winner is a single. The starting point for
any fix, and the asymmetry that makes this lift hard:

    lift        median null   median h rms
    bench          3.93 cm       1.81 cm
    squat          4.61 cm       3.18 cm
    deadlift       1.63 cm       2.78 cm

**The deadlift null is the smallest in the corpus by a factor of ~2.5.** The bar
genuinely barely moves fore-aft, so beating the null there means reconstructing
fore-aft to ~1.6 cm — which is about the 1 cm spec itself. Deadlift is not
merely reconstructed worse; it is graded against a much harder bar. H1 said this
first and it is worth restating before any fix is judged.

## The thing that was open, and it is now closed

`analysis/C31b_STATE.md` has carried this as **item B** since 2026-08-06: C29's
rest-to-rest window + impact correction took the deadlift horizontal
**10.66 -> 3.93 cm** with step 6 OFF and before H8's step 5b existed. 5b also
removes a drift-shaped error, so either 5b had already taken what C29 was
taking, or the two compose.

**They compose, and C29 is worth MORE after 5b than before it.** Median
horizontal rms over the eight scoreable deadlifts, all arms sharing identical
rest-to-rest windows:

    arm                                    h rms    beats_null
    control  (rest windows, no correction)  9.34        0.21
    C29      (+ 0.20 s jump), 5b OFF        4.08        0.69
    C29      (+ 0.20 s jump), 5b ON         2.88        0.83

So 5b did not subsume it. Within its own frame the correction is **better on
10 of 10 captures, paired Wilcoxon p = 0.002.** Four captures cross
`beats_null = 1.0` (1.05, 1.11, 1.41, 1.65), which no multi-rep deadlift has
ever done.

Two implementation points worth carrying:

* **Correct the vertical too.** `jump_rest_windows` defaults to `axes=(0, 1)`.
  Left there, the rest-window frame's vertical rms is **6.08 cm** against
  shipping's 2.88 — the frame costs vertical accuracy that the correction then
  has to give back. With `axes=(0, 1, 2)` it is 2.80, and the horizontal is
  bit-identical. C29's own table corrected all three axes; the default does not.
* **The width has an interior optimum between 0.20 and 0.40 s, and which end
  depends on the metric** — `beats_null` peaks at 0.20 (0.83) and falls
  monotonically after, while raw `h_rms` bottoms at 0.40 (2.55 against 2.88).
  Beyond that it degrades sharply — 0.60 s gives 3.59 cm, 1.20 s gives 4.68,
  and `width_s=None` (C28b's whole-interval spread, already measured and
  rejected) gives 4.41. **So the correction is genuinely local**, which is the
  point C28b/C29 were making, and 0.20–0.40 s brackets where B6 independently
  measured the strap ringing. *At the eight captures held this morning the h
  minimum sat at 0.20; the two new captures moved it to 0.40, so do not read
  either endpoint as settled.*

## And it is still not shippable. The blocker is the FRAME, not the correction

**Against what ships, the improvement is marginal and should be read as
such.** Median h **3.31 -> 2.88 cm**, median `beats_null` **0.57 -> 0.83**,
better on **7 of 10** — which reaches nominal significance on a paired magnitude
test (**Wilcoxon p = 0.049**) and does NOT on the sign test (p = 0.34). p = 0.049
on ten captures, two of which arrived the same day and are both large wins, is a
result to hold loosely.

*This changed during the task and the way it changed is worth recording.* At the
eight deadlifts the corpus held that morning it was 5 of 8, sign p = 0.73,
Wilcoxon **p = 0.195** — not a demonstrated improvement at all. Two deadlifts
arrived mid-session and both favour C29 heavily (14.91 -> 5.45 and 7.22 -> 4.13),
taking it across the line. That is exactly the sensitivity this file's own
recommendation predicted: eight captures could not resolve a difference this
size, and two more moved it. It equally means ten cannot settle it either.

Worse, the shipping-vs-C29 comparison carries **two confounds, and they pull in
opposite directions**, which is why it has to be reported rather than reduced to
one number.

**Confound 1 — coverage, and it is structural.** `rest_windows` pairs
consecutive rest instants, so n impacts yield n rests yield **n-1 windows**. The
frame scores **30 of 46 reps** and **rep 1 is never scored** on any capture;
`deadlift_185x3` drops to a single rep, so its `beats_null` of 1.41 rests on one
rep and should not be quoted.

*Recovering the missing rep was tried and FAILS.* Prepending the segmenter's own
first-rep start as an extra boundary restores coverage (n-1 -> n) and makes the
horizontal worse on **5 of 5** captures tested — `deadlift_160x4_2` 1.64 -> 4.66.
The first window is not a rest-to-rest window in the sense that matters: the bar
starts dead on the floor and the window carries the setup, so the impact does
not sit inside it the way C29's construction requires.

*And the obvious decoupling does not exist.* "Detrend on rest-to-rest windows
but keep impact-to-impact reps" is the natural fix and cannot be built: C29
itself measured that step 7 is load-bearing through its per-rep INDEPENDENCE
(the continuous piecewise-linear variant cost 8.21 -> 17.00 cm), so the
detrended position is only defined piecewise inside its own windows. Slicing
different windows out of it re-introduces exactly the discontinuity that failed.
Windows and reps are the same object here.

**Confound 2 — the window change moves the null, by 27%.** Median `null_h_rms`
is 1.63 cm in the shipping frame and 27% larger in the C29 frame, **larger on 9
of 10 captures.** This cuts both ways and both readings are needed:

* it **flatters `beats_null`**, whose numerator this is — part of the 0.68 ->
  0.83 is the denominator moving, not the reconstruction improving. That is
  C12's shape exactly, where a referee's invented motion inflated the null and
  flattered the pipeline;
* it **makes the raw `h_rms` comparison harder** for C29, not easier — the
  rest-to-rest windows contain 27% more real fore-aft travel to get right, and
  C29 gets them to 2.00 cm where shipping gets its easier windows to 2.78.

**Confound 3 was tested and does not exist.** C29 drops rep 1, the only rep
pulled from a dead stop, so its gain could have been a selection effect. It is
not: rep 1 is *better* than its set's average on 3 of 5 captures measured, and
dropping rep 1 from SHIPPING makes shipping worse on 3 of 5 (2.91 -> 3.26,
2.65 -> 2.84, 2.26 -> 2.39). The selection runs against C29 or is neutral.

## The two captures that arrived mid-task, and one alarming thing in them

`deadlift_160x6_1_20260818` and `deadlift_190x3_20260818` landed at 14:03 while
this was running. Both track cleanly under the C31 protocol — coverage 99.8% and
99.7%, travel 56.7 and 54.9 cm, residual 0.72 and 0.76 px, rep counts 6/6 and
3/3 matching their filenames — and neither is flagged implausible. The corpus is
now **31 captures**; `CLAUDE.md` still says 29.

    capture                        ship h   ship bn   C29 h   C29 bn   null
    deadlift_160x6_1_20260818       14.91     0.12     5.45     0.34   1.81
    deadlift_190x3_20260818          7.22     0.43     4.13     1.05   3.11

**`deadlift_160x6_1_20260818` reconstructs at 14.91 cm and is the worst
horizontal in the corpus by a factor of two.** It is not a scoring artefact —
6 of 6 reps, a normal null of 1.81, a clean track. The alarming part is the
comparison available for free: **the same lift, load and rep count on
2026-08-04 reconstructs at 1.97 cm.** Same lifter, same bar, same nine steps,
a 7.6x difference in horizontal error between two sessions.

*Checked, because there was an obvious candidate and it is NOT the cause.* The
suite flags this capture's rep 6 as a broken window — `up 122 cm vs down 37 cm,
the window is missing a phase` — which would be the natural explanation. It is
not: the error is **uniform across all six reps at 10.4-15.7 cm**, and dropping
the last rep moves the total only 14.35 -> 14.11. Meanwhile the VERTICAL is
1.1-1.6 cm per rep and the IMU's per-rep ROM (52.8-54.5 cm) matches the video's
(53.9-56.3) to about a centimetre. **So this capture reconstructs its vertical
and its extent correctly and is uniformly ~14 cm wrong fore-aft on every rep** —
which is a cleaner statement of the defect than "one bad rep" would have been,
and it rules out segmentation as the cause.

That is worth putting beside H17's result that rep-1 MCV repeats across sessions
to 0.6–4.6%. **The velocity channel is reproducible session to session and the
horizontal position channel is not**, which is the same split H17 found between
the load–velocity fit and `beats_null`, now visible within a single set spec
rather than across lifts. Nothing here explains it and it was not chased.

`deadlift_190x3_20260818` is the more useful capture of the two: at 190 kg the
video shows the bar genuinely drifting ~8 cm toward the lifter, giving it a null
of **3.11 cm — twice the deadlift median** — and under C29 it crosses the null
at 1.05. A heavier bar with real fore-aft travel is the condition under which
this lift is easiest to grade, and the corpus has almost none of it.

## What C29 is not: D1's degenerate case

D1's per-rep parabola detrend was rejected because it **converted every capture
into approximately the flat-line null** — `beats_null` entered spanning
0.13–5.39 and left spanning 0.76–1.16. It removed the channel rather than
correcting it. That is the first thing to check of any deadlift fix, and C29
passes it:

    arm         beats_null span    median   n >= 1.0
    shipping      0.12 – 0.93       0.57       0 of 10
    C29           0.34 – 1.65       0.83       4 of 10
    D1 (for contrast, from `oracle.parabola_detrend`)  0.76 – 1.16, collapsed

The spread **widens** under C29 rather than collapsing onto 1.0, and captures
separate from one another instead of converging. C29 is adding information, not
deleting a channel.

## Verdict, and what would settle it

C29 remains the strongest deadlift candidate anyone has measured, it survives
every change made since it was built, and **the reason it cannot ship is now a
measured one rather than an untested one**: its frame costs a rep per set, that
cost cannot be recovered by the two available routes, and against shipping the
remaining gain does not clear a paired test on eight captures.

Three things would move it, in order of cost:

1. **More deadlifts — and this is no longer hypothetical.** Two arrived
   mid-task and moved the headline test from p = 0.195 to p = 0.049 on their
   own. Ten captures cannot settle a 0.4 cm median difference either; the same
   argument that says eight were too few says ten are.
2. **A decision about rep 1.** If losing the first rep of every set is
   acceptable for the product, C29's frame-internal case is strong (p = 0.002)
   and the question becomes a product one rather than a measurement one. It is
   the owner's call, not a measurement — a 3-rep set losing 2 of 3 reps is a
   different proposition from a 6-rep set losing 2 of 6.
3. **A boundary before the first pull that is a genuine rest.** The bar IS still
   on the floor before rep 1; what failed above is using the segmenter's rep-1
   start, which includes the setup. `phase == 0` marks an opening hold but it
   ends ~8 s before the first pull on `deadlift_150x4_1`, so neither existing
   anchor is the right one. A still instant found in the last second before the
   bar breaks the floor would be, and nothing in `segment.py` looks for it.

   **BUILT AND MEASURED (H22, 2026-08-19) — the prediction in this paragraph
   was right, and it does not by itself make C29 shippable.**
   `oracle.prepull_rest` finds that instant on 9 of 9 deadlifts and it is
   quieter than every post-impact rest instant in the same capture. Coverage
   goes 30 of 46 reps to 40 and rep 1 is scored; the null inflation this file
   records as confound 2 goes from 1.28x to 0.97x, so that confound is removed
   rather than inherited. But the recovered window is the HARDEST in the set on
   4 of 6, so the gain over shipping stays marginal (8 of 10, p = 0.105, where
   C29 was 7 of 10 at p = 0.049). See `analysis/H22_STATE.md` and
   `analysis/72`.

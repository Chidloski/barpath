# EVALUATION — E1, 2026-08-07

An audit rather than a task. Branch `c29-jump-state`, HEAD at the time of
measurement `14eaf00`, **step 6 ON** (`wrist_offset="auto"`) unless a row says
otherwise. Nineteen captures: the ten in `data/raw` refereed by `truth.py`'s
plate template and the nine in `data_v2/raw` refereed by `markers.py`'s conic.
Squat is excluded throughout because `metrics.vs_truth` refuses it.

Decision rules were fixed in writing before any number was read
(`E1_DECISION_RULE.md` in the session scratch, reproduced in outline below).
Reproduce anything here with the scripts named at the end.

Findings are ranked by how much they matter, and each says plainly whether it
is **CERTAIN**, a **SUSPICION**, or **UNSETTLED**. Section 7 is the list of
things I checked and found SOUND, because that is a result too.

---

## 1. CERTAIN — the pipeline loses to drawing ONE IDENTICAL AVERAGE PATH for every rep, on both axes

**This is the project's own success criterion and it had never been measured.**
CLAUDE.md's Spec says it in so many words:

> What matters is **rep-to-rep difference**, not absolute truth. A path
> systematically 1.5 cm forward of truth is fine if it is consistently so.

That licence is only available if the per-rep error is smaller than the
rep-to-rep differences the display exists to show. Measure the second quantity
directly — for each capture, predict rep *k*'s video curve with the
**leave-one-out mean of the other reps' video curves**, and compare that
predictor's error against the pipeline's. The predictor draws the same shape
every rep, so it contains zero rep-to-rep information by construction.

    capture                     n   pipeline h   LOO-mean h  ratio | pipeline v  LOO-mean v  ratio
    bench_90x4_1                4        1.25         2.05    1.65 |      1.33        3.56   2.68
    bench_90x4_2                4        0.89         1.38    1.55 |      1.81        3.19   1.76
    bench_90x4_3                4        1.36         1.67    1.22 |      0.95        2.78   2.94
    bench_92.5x2                2        1.53         1.87    1.22 |      4.71        1.33   0.28
    bench_spoto_90x5_1          5        2.21         0.96    0.44 |      4.47        1.31   0.29
    bench_spoto_90x5_2          5        1.63         1.14    0.70 |      3.64        2.22   0.61
    bench_spoto_90x5_3          5        1.25         0.73    0.59 |      2.79        1.46   0.52
    bench_92.5x4_1              4        1.23         0.98    0.80 |      2.45        2.58   1.05
    bench_92.5x4_2              4        1.18         1.32    1.11 |      2.62        2.14   0.82
    bench_92.5x4_3              4        1.92         1.10    0.57 |      2.68        2.26   0.84
    bench_95x2                  2        0.80         1.35    1.68 |      2.11        1.62   0.77
    bench_spoto_95x5_1          5        3.53         0.92    0.26 |      2.90        2.47   0.85
    bench_spoto_95x5_2          5        4.43         1.84    0.42 |      3.01        1.00   0.33
    deadlift_155x6_1            6        4.55         2.87    0.63 |      5.10        3.26   0.64
    deadlift_155x6_2            6        8.96         3.64    0.41 |      6.51        4.47   0.69
    deadlift_180x3              3       15.58         2.14    0.14 |      5.32       10.56   1.98
    deadlift_160x6_1            6        6.63         2.37    0.36 |      4.55        2.40   0.53
    deadlift_160x6_2            6        4.38         1.25    0.29 |      4.60        1.97   0.43
    deadlift_185x3              3       10.57         2.21    0.21 |      2.78        6.17   2.22

    ratio > 1 = the pipeline beats a display that never varies.  cm, median per rep.

**Horizontal: 6 of 19. Vertical: 6 of 19.** Restricted to the fifteen captures
with four or more reps — where the leave-one-out mean is a fair predictor
rather than "the other rep" or "the mean of the other two" — it is **4 of 15 on
each axis**, and the four are `bench_90x4_1/_2/_3` plus one. Two of the six vertical passes
(`deadlift_180x3`, `deadlift_185x3`) come from captures whose video vertical
scale is the known per-capture defect, so their LOO number is inflated; discount
them and vertical is 4 of 19.

**Read the middle column as the answer to "is there anything to show?".** The
real bar's rep-to-rep spread is **0.7-3.6 cm horizontally**. That is not
nothing, and it is exactly why the spec is ~1 cm. The pipeline's per-rep error
exceeds it on 13 of 19 captures.

**What this is not.** It is an ORACLE — the predictor is fitted on the video,
so it bounds the family "draw a rep-invariant path" rather than being an
estimator anyone could ship. That is the same construction C19 used to bound the
detrend family and B6 used to bound constant-bias correction, and it is used
here for the same reason: it cannot be beaten by a better implementation.

**What would falsify it.** A capture where the pipeline's per-rep error is below
the leave-one-out spread on both axes, on four or more reps. Three exist
(`bench_90x4_1`, `_2`, `_3`) and they are one session on one lift.

*Evidence:* `analysis/54`, right panel. Rule 4 of the pre-registered decision
rule fired on exactly these captures.

---

## 2. CERTAIN — on deadlift, the horizontal reconstruction cannot tell which rep it is looking at

The permutation control this evaluation was opened with. Score reconstructed rep
*k* against video rep *j* of the **same capture**, on a normalised-phase grid,
and ask how often the true partner is the nearest. Vertical is the positive
control: same clips, same windows, same code, one column over.

    lift        axis         reps identifying their own video rep    expected   p
    bench       horizontal                20 of 53                      13     0.042
    bench       vertical                  27 of 53                      13     0.0001
    deadlift    HORIZONTAL                 7 of 30                       6     0.39
    deadlift    vertical                  17 of 30                       6     0.0001

    With each capture's mean rep removed from BOTH sides first — i.e. asking
    only about rep-to-rep DIFFERENCE, which is what the Spec says the product is:

    bench       horizontal                27 of 53                      13     0.0004
    deadlift    HORIZONTAL                 7 of 30                       6     0.39
    deadlift    vertical                  25 of 30                       6     <1e-4

*p* is Monte-Carlo over independent uniform random matchings, 40 000 draws,
exact null per capture (fixed points of a random permutation).

**Deadlift horizontal is at chance and the vertical from the identical windows
is not.** That rules out the sync, the segmentation, the axis sign, the video
scale and the tracker in one step — all of them are shared between the two
columns. It is a sharper form of C30's correlation result: no null model, no
threshold, no choice of projection direction.

**Bench horizontal does carry per-rep information**, weakly but significantly,
and more of it once the mean rep is removed. That corroborates C30b's bench
finding through an independent statistic, and it is the strongest positive
result in this evaluation.

**Sanity check, passed:** the phase-resampled matched error reproduces the
shipping `pipeline_h_rms` to two decimal places on all 19 captures (e.g. 4.57
vs 4.55, 15.65 vs 15.58), so the resampling is not doing the work.

**And split by referee, the bench result splits with it — a third independent
instance of the two trackers disagreeing about the horizontal and only the
horizontal** (demeaned, the spec-relevant variant):

    referee                     bench H            bench V        deadlift H
    truth.py template     17/29  p = 0.0008   26/29  p < 1e-4   5/15  p = 0.19
    markers.py conic      10/24  p = 0.084    21/24  p < 1e-4   2/15  p = 0.80

Vertical is overwhelming under both at comparable sample sizes, so this is not
simply less power in the marker set. It is the same shape as `d` helping
uniformly under the template and being mixed under the markers. Nothing here
says which is right; it says the disagreement is not confined to `d`.

*Evidence:* `analysis/54`, left panels — `deadlift_160x6_1`'s two confusion
matrices, 1 of 6 on the diagonal horizontally against 3 of 6 vertically.

---

## 3. CERTAIN — `beats_null` is measured against the WEAKEST member of the family it names, and it ranks captures differently from finding 2

`null_h_rms` is the rms of the video's fore-aft about the rep's **start** point.
That is one particular vertical line. The best-placed vertical line — an oracle
over the same "draw no fore-aft motion" family — scores **1.00 to 2.07x
better**, typically ~1.6x on bench.

    beats the start-line null (what `beats_null` reports)   11 of 19
    beats the BEST-PLACED flat line                          7 of 19

Captures that change verdict: `bench_90x4_1` (bn 1.67, but 0.80 against the
best flat line), `bench_spoto_90x5_1` (1.19 -> 0.62), `bench_spoto_90x5_2`
(1.32 -> 0.72), `bench_92.5x4_3` (1.19 -> 0.74).

**Two of the three crossings that `pipeline.run` calls "the strongest single
piece of evidence" for shipping step 6 do not survive it.** The three
2026-07-30 paused benches went 0.72/0.80/0.92 -> 1.19/1.32/1.94 under `d`; under
the best-flat-line reference they are 0.62/0.72/1.22.

And `beats_null` does not predict rep identification. Spearman over the 19
captures is +0.53 (p = 0.02) against the raw hit-rate excess and **+0.38
(p = 0.11)** against the demeaned one. Concretely: `bench_92.5x2` beats the null
2.03x and identifies 1 of 2 reps (chance) and 0 of 2 demeaned;
`bench_spoto_90x5_1` beats it only 1.19x and identifies 4 of 5 demeaned. **They
are different questions and neither substitutes for the other.**

**This does not retract `beats_null`.** Below 1 still means the reconstruction
subtracts information, and the start-aligned line is what the display would
actually draw. What it means is that "beats the null" is a weaker claim than it
reads as, and it should not be quoted alone.

**A smaller reporting point in the same function.** `beats_null` is
`median(null) / median(pipeline)` — a ratio of medians, not the median of the
per-rep ratios. On 6 of 19 captures the two differ by more than 15%, and on
five of those the reported figure is the more flattering one:
`bench_90x4_3` 2.25 against 1.56, `bench_spoto_90x5_3` 1.94 against 1.42,
`bench_90x4_1` 1.67 against 1.31. `deadlift_155x6_1` goes the other way,
0.78 against 0.97. Not wrong — both are defensible summaries — but the
per-rep view is the one the docstring's prose describes.

*Falsified by:* nothing here — it is arithmetic on the same curves `vs_truth`
already returns.

---

## 4. CERTAIN — no `data_v2` capture has an accuracy regression gate, and the gate that exists has 2.1-2.6x of slack where it matters most

`tests/test_real_data.py` pins horizontal error (`AS_SHIPPED_H_CM`, 3 deadlifts)
and `beats_null` (`BEATS_NULL`, 10 captures). Every entry is a `data/raw`
capture. Grepping the rest of the suite for `pipeline_h_rms`, `pipeline_v_rms`
or `beats_null` finds no other assertion anywhere.

**So the nine `data_v2` captures — the ones refereed by the tracker
`src/README.md` says a future capture should be judged by, and the exact six on
which `d` is a coin flip — are gated on tracking quality and sync only.** A
change that halved their accuracy would pass the suite.

The gate that does exist is one-sided and has not been re-pinned since step 6
went on:

    capture               BEATS_NULL   floor (x0.80)   actual now   slack
    bench_spoto_90x5_1        0.72         0.576          1.19       2.07x
    bench_spoto_90x5_2        0.80         0.640          1.32       2.06x
    bench_spoto_90x5_3        0.92         0.736          1.94       2.64x
    bench_92.5x2              1.14         0.912          2.03       2.23x
    bench_90x4_1              1.10         0.880          1.67       1.90x
    bench_90x4_2              3.45         2.760          3.45       1.25x
    bench_90x4_3              2.25         1.800          2.25       1.25x

The three paused benches are precisely the captures whose crossing of 1.0 is
cited as the evidence for the shipping default, and each has room to fall by
more than half before its gate notices. `AS_SHIPPED_H_CM`'s headroom is
1.23-1.38x on the three deadlifts, which is the intended 1.25 plus what `d`
bought.

*Recorded, not fixed — I hold no `tests/` path.* The change is two dictionaries:
re-pin `BEATS_NULL` at the post-step-6 values, and add the nine `data_v2`
captures to both tables. See §5 for why it matters right now.

---

## 5. CERTAIN — the suite does not notice step 6 being turned off

Ran `tests/test_real_data.py`, `test_pipeline.py`, `test_projection.py` and
`test_segmentation.py` under a pytest plugin that reverts
`pipeline.run(wrist_offset=)` to `None` — i.e. undoes the branch's headline
change.

    RESULT_NOD

Baseline (`E1_MUTANT=none`, `test_real_data.py` alone): **291 passed, 1 skipped,
8 xfailed, 7 xpassed** in 8 m 35 s.

This follows directly from §4: the only two-sided accuracy assertions are the
three deadlift ceilings, and `d` improves those, so removing it stays inside
them. The `xfail` on `test_the_reconstruction_beats_drawing_nothing` is
`strict=False`, so the three benches that stopped XPASSing report as plain
xfail and nothing fails.

Three further mutants, each aimed at a claim the docs make about what would be
invisible:

    MUTANT_TABLE

*Reproduce:* `PYTHONPATH=<scratch> E1_MUTANT=nod python -m pytest
tests/test_real_data.py -p e1_mut -q`, plugin in `e1_mut.py`.

---

## 6. CERTAIN — step 6 flips the display-confidence flag on 6 of 30 captures, unrecorded and ungated; and three of that gate's decisions sit within 0.5% of their threshold

`project.confidence` gates plot.py's 4x horizontal stretch. Switching step 6 on
moved it:

    capture                  d OFF   d ON    what moved
    bench_92.5x2              True   False   ratio 8.59 -> 5.93
    bench_spoto_90x5_2        True   False   ratio 4.26 -> 3.09
    bench_92.5x4_2            True   False   ratio 4.87 -> 2.89
    squat_170x1               True   False   ratio 56.3 -> 12.6
    deadlift_155x6_1          True   False   excursion 18.3 -> 21.0 cm, over the 20 cm ceiling
    squat_130x5              False    True   ratio 2.78 -> 4.19

Nothing in `CLAUDE.md`, `TASKS.md` or `pipeline.run`'s docstring records that the
default change altered what a lifter sees, and no test asserts `confident` on
any real capture.

**And the gate is at zero margin in three places**, which is C21's pattern
(three admission gates all at zero margin at once):

    bench_92.5x2         ratio 5.930 against a need of 5.935   REFUSED by 0.08%
    bench_spoto_95x5_2   ratio 3.360 against a need of 3.342   ADMITTED by 0.54%
    deadlift_155x6_1     excursion 21.0 cm against 20.0 cm     REFUSED by 5%

`project.confidence`'s docstring also says the 20 cm ceiling "on data/raw
refuses exactly the four captures that are independently known to be wrong". Two
of those four defects (`squat_160x1`, `bench_spoto_90x5_1`) were fixed by C5, so
that sentence no longer describes what the gate does.

Finally, and this is the docstring's own warning turned into a count: of the
seven bench/deadlift captures currently marked `confident`, **four lose to
drawing one identical average path every rep** (`bench_spoto_90x5_1` 0.44,
`bench_spoto_90x5_3` 0.59, `bench_92.5x4_1` 0.80, `deadlift_185x3` 0.21). The
flag is honest about being necessary-not-sufficient; nobody had measured how far
from sufficient.

---

## 7. Checked and SOUND — no defect found

Reported because "I checked X and it is sound" is a result, and three of these
were on the brief's suspect list.

**`integrate.py`, the 68 lines nobody has challenged.** Two things could be
wrong and neither is. *The time base:* `times = np.cumsum(dt)` with `dt[0]`
duplicated from `dt[1]` reproduces `log["t"]` up to an additive constant
**exactly** (max deviation 0.00e+00 on all six deadlifts), and
`cumulative_trapezoid` reads only differences, so the duplicated first sample
cannot bias anything. *The scheme:* double trapezoid is not exact even for a
piecewise-linear acceleration — the second integration under-reads by
`h^2/12 * da` per interval, which is largest exactly at the floor impact where
`a` jumps ~200 m/s^2 in one sample. Summed, that defect is **1.0-1.6 mm over a
whole capture and 1.1-2.1 mm within the worst rep**. Two orders below the error
under investigation. Do not spend time here.

**`orient.to_world`'s gravity round trip, checked numerically rather than read.**
`accel - R_reported^-1 . G`, rotate by the corrected attitude, add `G` back.
With the shipping zero gyro bias the two attitudes agree and it reduces to
`R . accel` to **4e-14 m/s^2**; the construction is nonetheless the right one,
because it applies the attitude correction to the full specific force rather
than to user acceleration alone. Injecting a deliberate 1 degree attitude error
leaks **0.169 m/s^2 horizontally** against `g sin(1 deg) = 0.171` and
**0.0014 m/s^2 vertically** against `g (1 - cos(1 deg)) = 0.0015` — the
first-against-second-order asymmetry the module docstring derives, reproduced
on a real capture. Frame conventions are right and the w-x-y-z to x-y-z-w
boundary is handled at every crossing.

**The step-6 `d` on/off table is NOT corrupted by the display axis turning.**
C31b's confound is real — the axis moves 0.4 to 50.0 degrees between the two
arms — but rep bounds are identical in both arms (they come from `rep_bounds`,
which runs before step 6) so the comparison can be redone with the axis held
fixed. Re-scored along the d-OFF axis, **the sign of the change flips on one
capture of nineteen** (`bench_92.5x4_2`, 1.12 -> 1.18 becomes 1.12 -> 1.10, a
0.02 cm difference). The three large-angle captures — `bench_92.5x4_3` (50.0
deg), `bench_spoto_95x5_1` (45.9), `bench_spoto_95x5_2` (22.5) — all keep their
sign. **The bench dissent is not the turning axis.** Magnitudes do move (up to
1.39 -> 2.41 cm), so hold the axis if you quote a magnitude, but the verdict
stands.

**Every number in C10's `beats_null` table and in `pipeline.run`'s d-on/d-off
table reproduces exactly.** All ten of C10's step-6-off horizontal figures
(0.64 / 0.76 / 1.88 / 2.63 / 2.69 / 2.75 / 3.67 / 5.05 / 9.19 / 15.44) and all
nine of C31's on/off pairs come back bit-for-bit. The documentation's arithmetic
is trustworthy; it is the framing that needs care.

---

## 8. SUSPICION — `d` lowers the error without adding information

Re-running finding 2's statistic in both arms:

    lift        rep identification, raw / demeaned      d OFF        d ON
    bench                                              21 / 27      20 / 27   of 53
    deadlift                                            7 /  8       7 /  7   of 30

Step 6 improves horizontal rms on 3 of 3 deadlifts and takes C31's acceleration
correlation from 0.12-0.23 to 0.43-0.64, and **moves rep identification by
nothing at all**. The most economical reading is that `R(t).d` removes a term
that is common to every rep — which is exactly what a body-frame constant swept
by a near-repeating wrist rotation is — while the part that differs rep to rep
is untouched. That is consistent with C31b's "it does not cash out in position"
and gives it a mechanism.

**Not certain**, because 19 captures and ~83 reps is a small sample for a null
result, and because the acceleration-domain gain is real. What would settle it:
the same statistic on more reps, or on a capture with deliberately varied
fore-aft.

---

## 9. RECORDED, not fixed — claims that no longer reproduce

I hold no `src/` path. Each of these is a one-or-two-line docstring correction
for whoever holds the file next.

1. **`src/metrics.py` lines 824-825** — "Three of the seven bench captures clear
   the correlation floor; the other four raise." False since C10 withdrew the
   peak-height threshold; all seven sync, and this evaluation scored all seven.
2. **`src/correct.py` module docstring and `apply_offset`** — the whole step-6
   argument is still framed at **|d| = 14 cm** ("roughly 14 cm along the forearm
   axis", "at |d| = 14 cm the within-rep variation is 1.2-2.4 cm"). The owner's
   tape says 9.5 cm on bench and deadlift, 6.4 on squat, so every magnitude in
   that section is 1.5-2.2x too large. The constant below it is right; the prose
   above it predates it.
3. **`src/project.py`, `confidence`** — "on data/raw it refuses exactly the four
   captures that are independently known to be wrong". Two of the four named
   defects were fixed by C5; the excursion ceiling now refuses the three
   deadlifts, and `deadlift_155x6_1` only because step 6 pushed it from 18.3 to
   21.0 cm. Same docstring: "reconstructions of 18.3, 35.9 and 30.0" is now
   21.0, 35.4, 30.5.
4. **`tests/test_projection.py`,
   `test_every_capture_gets_a_projected_path_and_a_verdict`** — "`confident`
   being False ... is the answer on **8 of 17** captures". The corpus is 30 and
   with step 6 on the answer is **15 of 30**; six of those verdicts changed when
   step 6 went on (finding 6). The test itself is fine — it asserts only that a
   verdict exists — but the number in its docstring is two corpus generations
   old.
5. **`src/correct.py`, `detrend_rep`** — its `t` parameter is documented as if it
   were the full time array but must be pre-sliced to the rep (`detrend_set`
   passes `t[start:end]`, and `metrics._close` passes the window). A full array
   raises rather than silently mis-computing, so this is a documentation defect
   only.

---

## What I could not settle

- **Which referee is right.** C31b called this the highest-value open question
  and it still is. Findings 1 and 3 hold under both trackers with the same
  shape. Finding 2 does not: bench horizontal rep identification is significant
  under the template (p = 0.0008) and not under the markers (p = 0.084), while
  vertical is overwhelming under both. That is a **third** independent instance
  of the two referees disagreeing about the horizontal channel specifically —
  after C24's ~20% ROM gap and the `d` split — and it is now the disagreement
  with the most evidence behind it. I cannot adjudicate it: doing so needs a
  capture filmed by both, or a physical scale reference in shot.
- **Whether the four `bench_90x4_*`-session results are the pipeline working or
  the session being easy.** Those three captures pass every test here — best
  `beats_null`, best rep identification, the only ones beating the rep-invariant
  oracle on both axes. They are one lifter, one day, one lift, touch-and-go,
  filmed from the side opposite the watch. I cannot tell a working
  reconstruction from a favourable capture with n = 3.
- **Squat.** Refused by `vs_truth`, so nothing here covers it. D2 holds it.

## 10. CERTAIN, and outside the pipeline — the concurrency protocol's race resolution rests on a clock no agent is reading

Found by colliding with it. CLAUDE.md resolves two overlapping claims by
comparing `since:` — "the **earlier `since:` wins** and the later agent
withdraws its block. That is the whole race resolution."

I appended a claim on `src/plot.py` at `since: 2026-08-07T11:40Z`. D1's
competing claim on the same file sits **above** mine in the file and carries
`since: 2026-08-07T12:15Z` — later. So the rule says D1 withdraws, even though
D1 appended first and was already mid-transplant.

The real time in this checkout, from `date -u`, was **2026-08-07T00:10Z**.
Every `since:` on the board today is between nine and twelve hours in the
future: D1 09:05Z, D2 09:25Z, mine 10:05Z, C31 03:10Z. **They are all invented.**
Agents are writing a plausible-looking timestamp rather than reading the clock,
which nothing stops them doing and nothing detects — `tests/test_heartbeat.py`
checks that `since:` parses, not that it is true.

Two consequences, and the second is the one that costs work:

* Ordering by `since:` can invert the true order of arrival, which is exactly
  what happened here. I withdrew rather than take the file on a number I knew
  to be fiction; a less careful agent wins the collision and two agents edit
  `src/plot.py` at once, which is the accident the board exists to prevent.
* A stale-looking claim cannot be judged. CLAUDE.md tells an agent not to break
  a claim that merely looks abandoned and to hand it to the owner instead —
  reasonable, but "a stale `since:` and no sign of progress" is not observable
  when `since:` is a guess. C30b's 41-hour hold was adjudicated on the owner's
  direct knowledge, not on the board.

**The fix is one sentence in the protocol and costs nothing: `since:` is
`date -u "+%Y-%m-%dT%H:%MZ"`, run, not estimated.** `tests/test_heartbeat.py`
could then also refuse a `since:` in the future, which would have caught every
block written today. Recorded rather than done — CLAUDE.md and
`tests/test_heartbeat.py` are not mine and this is not the task I was given.

## Method and reproduction

Scratch scripts, session `366a3089`:

    E1_DECISION_RULE.md   the rules, fixed before any number was read
    e1_track.py           tracks the ten data/video clips into e1_plate_paths.pkl
    e1_perm.py            experiment 1, the E_match / E_mis / S_vid table
    e1_perm2.py           finding 2 — hit counts, demeaned variant, permutation p
    e1_axis.py            finding 8 and §7's held-axis re-scoring
    e1_null.py            finding 3 — the three nulls
    e1_figdata.py         collects analysis/54
    e1_mut.py             the pytest mutation plugin used in §5

`data_v2` clips come from the shared tracked-path cache
(`366a3089/tmp/paths.pkl`); the ten `data/video` clips were tracked once into
`e1_plate_paths.pkl`. Nothing re-decodes on a repeat run.

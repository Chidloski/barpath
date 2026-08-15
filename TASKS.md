# Tasks

Working state of the pipeline rebuild started 2026-07-28, after milestones 1–6
all passed on synthetic data while the pipeline failed in the gym by two orders
of magnitude.

Related, and deliberately not duplicated here:

- `CLAUDE.md` — **Open problems** P1–P5, the *problems*. This file holds the
  *work*.
- `analysis/README.md` — the measurements and plots behind each finding.
- `src/README.md` — video ground truth (A2) in depth.

---


## G3 — a pipeline variant for singles and doubles (2026-08-15)

Owner's task, following G2. **The corpus is now 16 of 16 scored.** The three
captures that had never been refereed — `bench_117.5x1`, `deadlift_200x1`,
`squat_170x1`, one single per lift — score at h 0.96 / 2.66 / 2.05 cm, and all
three beat the flat-line null (3.31 / 1.08 / 2.01).

`deadlift_200x1` is the first deadlift in the project to beat the null at all;
every multi-rep deadlift sits at 0.14-0.81. Read it carefully rather than as
good news: a single's `beats_null` is a median over ONE rep, so it is far less
robust than the six-rep figures it is being compared against.

New module `src/shortset.py`; `pipeline.py` and `segment.py` are untouched.

### The premise was wrong, and measuring it first is what saved the work

The task's prior was that singles need a new SEGMENTER — "find the part of the
recording with maximum displacement with IMU dwells on either side". Measured
before building anything, singles do not have a segmentation problem at all:
`segment.rep_bounds` gets 1/1 on all three real singles (G1 checked the windows
against video) and 1/1 on thirteen more singles truncated out of the multi-rep
captures, with IoU 0.53-0.99 against the first rep of the full capture.

The proposed rule was implemented anyway, in three readings, and all three lose:

    rule                                        median IoU   IoU >= 0.5
    dwell = stationary_mask, duration-capped        0.00        1/12
    dwell = vertical-velocity turnaround            0.29        3/12
    candidates from _all_lobes, max displacement    0.00        2/13
    segment.rep_bounds as it stands                 0.70       12/12

One number explains it: **integration drift produces more apparent displacement
than a rep does.** The window the rule picks on `bench_92.5x6_1` claims 86.8 cm
of vertical travel on a bench press whose true range is 27 cm, and the largest
claim any variant made was 127 cm. Drift grows with window length, so "maximum
displacement" systematically prefers the longest admissible window. No dwell
threshold repairs that — the ordering is wrong, not the cut. **Do not
re-propose displacement as a selection rule without first removing the drift.**

### What was actually broken: the sync, in two different places

Bench and squat singles died on `bench_sync`'s cadence precondition — it accepts
on "every rival is a whole rep away" and a single has no rep period. The
deadlift single never reached it: `capture.sync` fits offset AND slope, so it
needs two landings against two impacts, and a single has one of each.

`shortset.short_sync` is the same correlation with the cadence precondition
removed and **the sweep bounded by overlap instead of by lag**. That swap is the
whole of it. Running `bench_sync`'s widening search on a single is a disaster:

    deadlift_200x1, sweep half-width    peak      error vs its own floor impact
      6.00 s                          -0.355 s          +11 ms
     11.75 s (the shipping constant)  -10.820 s      -10454 ms
     20.00 s                          -19.190 s      -18824 ms

and the wrong answers score HIGHER (0.490 and 0.688 against 0.335), because a
single is a flat record with one event in it and sliding the two records apart
correlates flat against flat on ever less of it. `MIN_OVERLAP_FRAC` is 0.80, the
LOW edge of a 0.80-0.95 plateau — taken at the edge on purpose, since the
failure it guards against grows as the floor falls.

### Accuracy, against answers the module did not supply

    singles (n=12)   median 7.5 ms, worst 103.9 ms
    doubles (n=9)    median 5.0 ms, worst  15.0 ms
    deadlift_200x1   +10.9 ms against its own floor impact — the only real
                     single carrying an offset that owes nothing to this module

For scale the multi-rep deadlift sync, the best-validated clock in the project,
runs 8.4-9.7 ms. Two acceptance checks: **containment** (the video's single
largest excursion must land inside the IMU's rep window — measured 0.44-0.88 on
all sixteen, and injected whole-rep errors are refused in both directions on all
three real singles) and, where the lift provides one, a **landmark** (a floor
impact matched to a video landing, agreeing to 3-104 ms).

### Doubles: bench and squat yes, deadlift NOT VALIDATED

The prior that doubles work like the existing pipeline is half right. The
existing route answers 9 of 13 truncated doubles at 0-27 ms; two of the extra
refusals are `bench_sync`'s fractional-rival guard on a two-rep set and two are
`capture.landings`, whose `skip_s=10.0` discards the only landing on a short
record. `short_sync` answers all of them.

But **deadlift doubles cannot be tested by truncation and are not claimed.** A
deadlift set has NO GAP between reps — the windows run impact to impact and the
measured gap is 0.00 s on all six captures — so cutting after rep 2 ends the
record exactly at the second landing with zero trailing record, where a real
double ends with the lifter releasing the bar and stepping back. Swept the
margin from 0.5 to 0.98 of the (zero) gap; the counts do not move. Bench and
squat doubles segment 2/2 on all seven and sync to 0-15 ms.

**A deadlift double is the single most useful capture anyone could add.**

### Two pre-existing defects found in passing, NEITHER fixed here

1. **`deadlift_170x4_3` is scored through a physically impossible clock.** Its
   landing-to-impact sync fits slope **0.7715** — a 22.8% clock drift, 216 ms
   residual — against under 0.4% and ~9 ms on every other deadlift. Nothing in
   the pipeline gates on `drift_pct` or `rms_ms`, so no caller could see it.
   Two independent estimates agree with each other and not with it: the
   correlation says -0.627 s and its own single landing/impact pair says
   -0.652 s, against the four-point fit's -1.505 s. `capture.sync` is not this
   module's to change and the right fix is a gate rather than a special case,
   so it is pinned by `test_a_broken_reference_sync_is_detectable` instead.
2. **`capture.sync` and `metrics.bench_sync` return `fit["offset"]` with
   OPPOSITE SIGNS** — `video = slope*imu + offset` against `imu = video +
   offset`. Each branch uses its own correctly and always has, so nothing is
   currently wrong; but anything comparing the two is silently out by twice the
   offset, which it did to this task's own measurements mid-flight and would
   have shipped a ~1 s error in six places. `vs_truth` now reports
   `sync_offset`, `sync_slope` and `sync_method` together, with the trap
   labelled where the fields are built.

### Evidence

`analysis/56_singles_doubles.png` (`run.py --shortsets`) and
`tests/test_shortset.py`, 45 gates. The thirteen multi-rep captures are
**bit-identical** with the hook installed and without it, checked per capture —
`metrics.vs_truth` and `_video_on_imu_clock` take a `sync=` hook defaulting to
None, and `shortset.sync` returns None for anything over two reps.

---


## G2 — vs_truth's squat refusal lifted, and the sync corroborated (2026-08-15)

Owner's task, following G1's investigation.

**Suite, run file by file:** 330 passed, 169 skipped, 1 xfailed, **6 failed** —
the same six as after G1, so G2 adds no new failures. Five pre-date this
session entirely and the sixth is `test_oracle[deadlift_200x1]`, which G1 caused
by making that capture's window right.

Squat is refereed for the first time in this project: **h 1.88 / 2.97 / 2.65 cm on the three paused captures,
all three beating the flat-line null** (1.71 / 1.24 / 1.50), which no deadlift
does. The corpus goes from 10 scored captures to 13, and the three that remain
unscored are all SINGLES. *(All three scored 2026-08-15 by G3; the corpus is
16 of 16. See the G3 entry above.)*

### Why it was refused, and why that reason was empty

`vs_truth` raised on any squat before doing anything else. Its stated reason —
median NCC ~0.40, the plate clipping the top of frame at lockout, two of four
2026-07-30 captures not tracking, "a wider shot, not code" — described the v1
plate template on `data/video/` footage. **F1 deleted both on 2026-08-14**, so
the refusal was gating on a claim that could no longer be checked in either
direction. The gate protecting it (`test_vs_truth_refuses_squat`) had been
silently skipping since, because it parametrised on two deleted captures.

"A wider shot, not code" was wrong in an interesting direction: it needed
neither. It needed a different feature to track, which `src/vtrack/` now is.

### The sync works, and works BETTER on squat than on bench

`_video_on_imu_clock` has always routed non-deadlift lifts to `bench_sync`.
Nobody had run it on a squat because the refusal fired first. Measured:

    capture               corr    whole-rep rivals   highest sidelobe
    bench (four)       0.46-0.63        2 to 4          0.720-0.794
    squat_pause_140x4_2   0.752            0            0.598
    squat_pause_140x4_3   0.732            0            0.578
    squat_pause_145x4_1   0.760            0            0.693

Bench's lag is identified only modulo one rep — that is `bench_sync`'s
documented ambiguity — and the paused squats' is identified absolutely. The
bottom dwell breaks the periodicity that makes bench ambiguous.

**Read the last column before quoting the middle one.** `squat_pause_145x4_1`'s
highest sidelobe is 0.693 against a 0.70 threshold: one percent from having a
rival. "The paused squat is unambiguous" is comfortable on two captures and
marginal on the third, and a slightly noisier capture would have failed the
rival test without anything about the sync being wrong.

### So the claim rests on a landmark instead, not on the rival count

`segment.dwell_instants` finds the bottom of each rep in RAW acceleration and
gyro — no attitude, no integration, no filtering, the discipline
`impact_anchors` and `rest_instants` keep — and `metrics.pause_landmark` matches
those against the video's per-rep lowest point. Two instruments that cannot see
each other, on the same offset. Across all seven multi-rep bench and squat
captures they agree to **0.003–0.083 of a rep period**.

`_video_on_imu_clock` now refuses when they disagree by more than
`LANDMARK_TOL_REPS = 0.25` — 3x clear of the worst real capture, 4x clear of the
whole-rep error it exists to catch. **Tested by breaking it:** a one-rep error
injected in both directions on every capture with a cadence is refused 14 times
out of 14, none missed.

That check is bench's gain as much as squat's. `bench_sync`'s validation was
transferred from deadlift — calibrated where the true offset is known, applied
where it is not — and this is the first on-lift evidence any bench capture has
had. Where it bites hardest: `bench_92.5x6_2`'s correlation offset is −5.385 s,
more than a rep from zero, and the landmark independently lands at −5.453.

### Two things that had to be got right, both found by them failing

**The dwell must be sought in the window's INTERIOR.** Searched over the whole
rep window the quietest instant is the standing brace at the edge, not the
bottom — a lifter holding a racked bar is quieter than the same lifter braced at
depth under it. That happened on 4 of 12 reps, at phase 0.02–0.16, and it
wrecked the fit: residual 55–677 ms and an implied clock drift of 1.6–5.3% where
the deadlift's landmark sync measures under 0.25%. Restricted to the middle 60%
the instants land at phase 0.31–0.54. Every value in 0.4–0.6 is bit-identical.

**It fits an OFFSET only.** Per-rep scatter is 83–223 ms against `capture.sync`'s
11–16 ms from matched landings, so four points over a 20 s set do not support a
slope — fitting one reads noise as drift. It corroborates a correlation and
bounds a whole-rep error; it does not replace `capture.sync`.

### Squat gains a second check for free, and it reads like bench

`metrics.momentum_closure` had no squat gate of its own — it was simply never
reachable, because nothing scored squat. It integrates vertical acceleration
between two moments the VIDEO says the bar was still, which must come to zero,
and a paused squat's bottom dwell is exactly such a moment. Median |dv| over the
whole corpus, in g:

    bench                0.0121 - 0.0263   (8-11 intervals)
    squat (paused)       0.0112 - 0.0401   (5-6 intervals)
    deadlift             0.0374 - 0.2785   (3-7 intervals)

Squat lands in bench's band and well inside deadlift's, and this number does not
depend on the video's distances at all — a scale error cannot move a zero
crossing — so it is independent of `STICKER_RATIO` being transferred rather than
measured. Not chased further here; recorded because it is now reachable.

### What is still refused, and why it is not about squat

`squat_170x1` — a single, so no cadence, so `bench_sync` cannot tell a whole-rep
ambiguity from a real one. Identical to `bench_117.5x1`. The three unscored
captures in the corpus are now exactly the three singles, and the fix for them
is a sync that does not need a cadence, not anything squat-specific. Note the
bottom dwell will not rescue `squat_170x1`: it is not a paused squat.

**CLOSED 2026-08-15 by G3, and the prediction above was right on both counts.**
The fix was a sync that does not need a cadence (`shortset.short_sync`) and the
bottom dwell did not rescue it — `segment.dwell_instants` misses `squat_170x1`
by +616 ms and `bench_117.5x1` by -843 ms, because neither is a paused lift.
All three singles now score. The corpus is 16 of 16.

### Evidence

`analysis/55_squat_sync.png` (`run.py --squatsync`), and the gates
`test_vs_truth_scores_squat_and_the_sync_is_corroborated` and
`test_the_sync_landmark_catches_a_whole_rep_error`. The latter replaces
`test_vs_truth_refuses_squat`, which asserted the opposite and had been skipping
since v1's deletion.

---

## G1 — three segmentation defects, fixed (2026-08-15)

Owner's task: find the segmenter's problems, fix them, then run the pipeline
against the cached tracked paths and plot it. F1 had already *diagnosed* two and
deliberately left them red as findings; this closes those and adds a third that
was found only by checking the second fix's own output against the video.

**Counting is 16/16 captures and 64/64 reps.** Every capture that was already
correct produces **bit-identical** windows — only the three broken ones move.

**Suite, run file by file:** 324 passed, 173 skipped, 1 xfailed, **6 failed**.
Five of the six pre-date this session (`test_segmentation` deadlift_170x4_3 ROM,
two `test_oracle` parabolas, `test_tracked`'s stale implausible flag,
`test_vtrack`'s stale `data/video/` assertion) and the sixth is
`test_oracle[deadlift_200x1]`, which G1 caused by making its window right —
see defect 3. Six gates that were RED before G1 now pass: the four in
`test_segmentation` and two in `test_real_data`.

### Defect 1: a setup wrist swing counterfeits a floor landing

`deadlift_150x4_1` gave five anchors for four reps. The extra one at 7.03 s is
not a collision at all but a 250 ms ramp — |a| climbing 0.7 → 6.9 g while |ω|
climbs to 27 rad/s and snaps to a stop. At the watch's ~9.5 cm lever that is
`α·r` = 6.3 g against 6.9 measured, so it is the lifter setting their grip. The
cached video track settles it: the bar is flat on the floor at 1.4–1.5 cm from
0 to 11 s.

**A higher `threshold_g` cannot fix it** — counterfeit 7.01 g, weakest real
landing 6.69 g, disjoint. `impact_anchors` now rejects on the median wrist
rotation rate in the second BEFORE the spike (28 real landings 0.39–0.98 rad/s,
4 setup swings 1.65–2.83, 5 rack collisions 0.33–0.56 and correctly kept).
Plateau [0.98, 2.83]; 1.3 ships. Still raw accel and gyro only — no attitude,
no integration, no filtering — which is the property that makes an anchor worth
having. Fixed at the source, so `capture.sync` and `metrics` get it too.

Three alternatives measured and rejected, in `analysis/53` and the docstring.
The instructive one: high-frequency energy fraction looked like the winner on
the deadlift and INVERTED on the control.

### Defect 2: the first bench single has no majority to out-vote the setup

`bench_117.5x1` gave two windows. Shape, size and cadence all compare candidates
with EACH OTHER, so all three need a majority of real reps; a single has none.
Its cluster is the real press at 21.9 s plus a setup arm movement at 10.6 s,
correlating 0.80 and carrying 0.290 against 0.304 m.

New discriminator `segment._upright`: a loaded bench or squat rep is a closed
kinematic chain and is constrained to travel vertically. Per candidate window,
detrended — 36 real bench and squat reps score 3.64–15.08 on vertical over
fore-aft; the setup movement scores 1.00. Plateau [1.02, 3.62], 255% wide, 2.0
ships. It **abstains** where no member of a cluster passes, on this module's
standing preference for silence over a false assertion; nothing in the corpus
exercises that today. `rep_bounds` takes an optional `position=`;
`pipeline.run` passes step 4's.

### Defect 3: the deadlift single was on the DROP, and only checking found it

Not in the brief — found while verifying defect 2's own work, and the most
useful thing in this entry. `deadlift_200x1` counted 1/1, reported a plausible
43.8 cm inside a 40–61 cm band, and its window was 18.97–19.92 s. The video has
the pull at **15.7–17.5 s** and the bar back on the floor by 19.8. It was
segmenting the drop. `squat_160x1`'s shape for the third time, and every summary
number said fine.

**Two independent defects, each of which alone leaves it wrong:**

  * `_similar_cluster` ranked a degenerate cluster by DISPLACEMENT, and the
    largest of its ten lobes is the reconstruction's invented velocity across
    the drop (0.529 m) rather than the pull (0.280 m). Singletons now rank by
    verticality, the same quantity `_upright` filters with, computed once and
    shared. Measured on all three singles the corpus holds, displacement gets
    **one of three** right and verticality gets three of three:

        capture           real rep   argmax displacement   argmax verticality
        squat_170x1         35.0 s   35.0 s  correct       35.0 s  correct
        bench_117.5x1       21.9 s    5.4 s  the unrack    21.9 s  correct
        deadlift_200x1      16.6 s   19.8 s  the DROP      16.6 s  correct

    Margins over the runner-up: 12.6x, 4.4x, and **1.22x on the deadlift**,
    which is the thin one and the value to watch.

  * `_full_cycles` was then handed a **hardcoded `sets_down=False`**, so a lift
    that rests on the floor got the bench convention and its eccentric taken
    from the wrong side. `_full_cycles` has always documented `sets_down` as
    coming from the signal "so the lift is never named" — the call site never
    did it. Harmless while only bench and squat reached that line. It is now
    `len(anchors) == len(chosen)`: one impact per rep means the bar is set down
    every rep. `bench_92.5x6_1` fires one anchor against six reps, so bench is
    untouched.

Window: 18.97–19.92 (43.8 cm, the drop) → 13.17–16.97 (28.1 cm, half a pull,
with only the ranking fixed) → **15.51–19.43 (55.0 cm)**, against a video pull
of 15.7–17.5. The ROM band is the independent check and it moves from failing
to mid-band.

**This also corrects a claim G1 itself made earlier in this session.**
`_upright`'s first docstring justified abstaining on deadlift by saying
"`deadlift_200x1`'s real pull scores 2.13, below several of its own non-reps".
Wrong: the lobe at 19.8 s had been assumed to be the pull without checking the
video. The real pull scores **2.59, the highest of that capture's ten lobes**.

**Two things that look like fixes and are not, both measured:**

  * Raising `similarity` to 0.83 breaks the false pair, and then the singleton
    fallback picks the 5.4 s unrack at 0.455 m — right count, wrong window.
    The [0.798, 0.872] plateau is real and measures the wrong thing.
  * Verticality computed from band-passed VELOCITY instead of detrended
    position — no new argument needed — collapses to overlapping (worst real
    1.69 against best non-rep 2.35). The detrend is doing the work.

### What this exposed about the corpus, which outlasts both fixes

**Deleting v1 removed this corpus's ability to tell two segmentation rules
apart, and two independent gates lost their teeth unnoticed.**

  * `test_segmentation.py` had `RAW` and `RAW_V2` both pointing at
    `data_v2/raw`, so every capture counted TWICE — F1's "28/32" is 14/16.
  * The cadence plateau's **ceiling is gone**. It came from
    `bench_spoto_90x5_1`, deleted with v1. Swept to `tol=1e6` — the cadence
    rule disabled outright — all 16 still count correctly. The constant is
    admissible, unfalsifiable from above, and its discriminator unexercised.
  * C31a's emptiness result no longer reproduces: the pre-C31a global-spread
    rule now reaches **16/16 at tol=2.49**. Not because it improved — because
    the capture that refuted it is gone and `_upright` removes the candidate
    cadence used to. Both gates now assert the new state with the reason.

**The most valuable capture that could be filmed for this module is a set with
a post-set movement inside the rep cluster** — a rest-pause, or simply pressing
"Finish Set" late after re-racking. It restores both gates at once.

**Two more gates are stale from the same deletion, left RED and untouched here
because they are not segmentation and G1 did not measure into them:**

  * `test_vtrack.test_data_v2_infers_vtrack` asserts
    `infer_tracker("data/video/squat_130x5.mov") == "plate"`. `data/video/` is
    gone and `infer_tracker` now raises. The assertion, not the code, is stale.
  * `test_tracked.test_the_implausible_flag_fires_on_the_clips_known_to_be_
    broken` expects `squat_170x1` to trip the implausible-travel flag. F1's
    `vtrack` rebuild fixed that clip's tracking, so the flag correctly does not
    fire and the gate is asserting a defect that no longer exists.

**And D1's headline is falsified on two of six deadlifts, which is NOT G1's
doing and is measured here because it was in the way.** `test_oracle.
test_the_deadlift_fore_aft_path_IS_one_parabola` pins median r2 > 0.70 and
records "0.76, 0.95, 0.95, 0.97, 0.98 and 1.00 across the six". Measured with
G1's anchors and without them:

    deadlift_150x4_1     before 0.23 (5 reps)    after 0.27 (4 reps)
    deadlift_170x4_3     before 0.47             after 0.47
    deadlift_160x6_1     before 0.97             after 0.97
    deadlift_185x3       before 1.00             after 1.00
    deadlift_200x1       before 0.88             after 0.43   <-- G1's doing

Two of the three failures pre-date this session, and the two captures the
parabola claim was measured on are untouched to two decimals. All three are
2026-08-08 captures — the session F1 found had never been under test. So "the
deadlift fore-aft channel is ONE NUMBER per rep" holds on the captures it was
derived from and does not generalise to the newest ones, and
`parabola_detrend`'s rejection rests on it. Left failing rather than re-pinned:
it is a finding, not a stale gate.

**`deadlift_200x1`'s IS G1's doing, and it is the good kind.** The gate was
passing at 0.88 on a **0.94 s window of the DROP** — a fragment that short fits
a parabola trivially. Against the corrected 3.91 s window, which is the real
pull and moves ROM from 43.8 to 55.0 cm, it scores 0.43. The metric got worse
because the window got right; that is CLAUDE.md's standing rule (correctness
outranks score) and it is recorded rather than smoothed. It also means one of
the six captures behind D1's headline was never measuring a rep.

### Corrections to F1's record

Two of F1's three structural claims do not survive measurement, and are
corrected in `CLAUDE.md` where they were made. `tol=1.47` did not fail because
the plateau closed; it failed because of the doubled corpus and an unrelated
miscount. And the bench single's mechanism is NOT the predicted singleton
tie-break picking the re-rack — the cluster has size 2, the singleton branch
never runs, and the false window is a setup movement 11 s before the press.
F1's third claim stands: `deadlift_170x4_3` rep 4 is wrong extent without a
miscount and remains the only entry in `KNOWN_ROM_FAILURES`.

### The pipeline against the cached tracks

`analysis/54`, all sixteen, and `run.py --vstracked`. **Six cannot be scored at
all** — four squats (`vs_truth` refuses), and both SINGLES, because
`bench_sync` needs a rep cadence and the deadlift clock fit needs two landings.
Two of the three captures repaired here are those singles, and neither can be
checked against the video at all.
*(SUPERSEDED: G2 lifted the squat refusal the same day and G3 scored the three
singles on 2026-08-15. All sixteen are scored now, and `analysis/54`'s figure
and docstring were written against the six-refusal state. The reasoning above
was correct when measured and is kept for the trail.)*
Of the ten scored, **all six deadlifts lose to a flat line** (0.14–0.81×) and
three of four benches beat it; the best capture in the corpus is 1.23 cm
horizontal against a 1 cm spec.

---

## F1 — delete v1 entirely: the corpus, the plate tracker, and `truth.py` (2026-08-14)

Owner's instruction, both scopes chosen by them explicitly after being shown
what each would cost. Merged `c29-jump-state` to `main` first (fast-forward,
24 commits, nothing lost).

**Deleted:** `data/raw/`, `data/video/`, `data/synthetic/`, `src/truth.py`'s
plate-template tracker, `analysis/tracking/v1/`, `tests/test_video_truth.py`,
and `run.py`'s `--stages`, `--splice` and `--b3oracle` drivers (all three called
the deleted `bar_path`). `data/raw/` was gitignored, so its 17 labelled captures
and 4 diagnostic logs are **unrecoverable**. History was NOT rewritten, so the
10 tracked `.mov` files remain retrievable.

**`src/capture.py` is what survived `truth.py`**, and the split is by whether v2
needs it. Kept: `lift_of`, the plate diameters and `sticker_plate_diameter`,
`VERTICAL_ROM_M`/`rom_flags`, `FORE_AFT_ACCEL_MAX`/`fore_aft_flags`, the decode
helpers `markers.py` uses, `find_plate` **as a single-frame rim detector only**,
and `landings`/`sync`/`to_imu_time` — which ARE the deadlift clock match at
9-19 ms and the best-validated sync in the project. Gone: `bar_path`, `track`,
`SEEDS`, `template_half`, `validate`, `top_of_travel_score`, `GOOD_SCORE`.
`metrics.TRACKERS` is `("markers", "vtrack")` and `infer_tracker` RAISES outside
`data_v2/` rather than falling back to a referee that no longer exists.

**THE FINDING, and it is worth more than the deletion.** Every gate in
`tests/test_real_data.py` and `tests/test_segmentation.py` globbed `data/raw`.
So when the 2026-08-08 session arrived, **it was never segmented under test** —
the gates silently had nothing to run on for those captures. Deleting v1 forced
the constants to be repointed at `data_v2/raw`, and the suite went from **109
passing to 311**, immediately exposing defects nobody had seen:

    deadlift_150x4_1_20260808   5 windows for a labelled 4   (video says 4)
    bench_117.5x1_20260808      2 windows for a labelled 1   (video says 1)

plus per-rep ROM out of band on those two and on `deadlift_170x4_3` (68.0 cm
against 40-61, at a CORRECT count of 4/4 — wrong extent without a miscount,
the `squat_160x1` shape), `deadlift_200x1` reaching the displacement fallback
C5 built for singles, and **C31a's cadence plateau closed**: tol=1.47 now gives
28/32 where C31a measured 1.4598-1.5306 and warned the 2.4% margin was thin.

The bench single is the sharpest of them because **CLAUDE.md predicted it in
writing** — "if you capture a bench single, expect this to fail", from
`_similar_cluster`'s lateness tie-break picking the re-rack when every cluster
is size 1. One was captured. It failed.

Per-capture reasons are in `WRONG_REP_COUNT` and `KNOWN_ROM_FAILURES`. **The two
structural failures are left RED, not xfailed** — they are the finding, and an
expected-failure mark is how the earlier ones stayed invisible.

**Removed rather than re-tuned:**
`test_the_pause_concentrates_the_correction_on_SQUAT_but_NOT_on_BENCH`. It
contrasted paused squats against continuous ones, and every continuous squat
was v1. What is left is three paused squats and one continuous SINGLE, so it was
computing the contrast from one capture of one rep. It failed at 3.84 against
2.95 x 1.4; lowering the factor would have made it pass, which is precisely
what must not happen when the sample supporting the claim is gone.

*Evidence:* `src/capture.py`, `tests/test_real_data.py`, CLAUDE.md P1.

---

## F1 — `src/vtrack/`, a new referee for `data_v2/` (2026-08-14)

Owner's task, over three rounds: fix the `data_v2` video tracking, then land it.
`markers.py` is untouched and still reachable as `tracker="markers"`.

**What was wrong, and it was never detection.** C31/D2 left six of eleven squat
clips unusable, two reporting 14.0 and 24.7 cm of whole-clip travel for 60-70 cm
squats behind 96-100% coverage and healthy residuals. Rounds 1-2 found the
deadlift dropouts were runs of ~85 frames from each rep's descent, with the
plate ranking **top-1 on a restricted search throughout** — the tracker let go
at the drop and never asked again — and that `squat_170x1` walked off the plate
at 1.000 coverage because a circle fitted through a clipped 180-degree arc has a
free centre along the arc's perpendicular, which is the fore-aft axis.

**Round 3 is the one worth reading, because both of my own round-2 fixes were
the problem.** The owner reported remaining artifacts and signal drops.

*The gaps were my own residual post-filter.* Genuine track loss was 14 and 2
frames on the two clips; the filter dropped 34 and 26 more. And it did not
work: on `deadlift_150x4_1` the fit residual correlates with the actual fore-aft
error at **r = +0.007**, dropping 14 frames deviating under 2 cm while leaving
the worst frame in the clip (14.0 cm, residual under the cap). On
`deadlift_160x4_2` the same correlation is +0.505 — coincidence on one clip, not
a mechanism. Removing it improved coverage on **8 of 8** clips, travel unchanged
to 0.3 cm.

*The artifacts were unverified multi-start seeds.* `_reacquire` proves itself by
trial-tracking; the starts never did, though a start is trusted for a whole
direction of travel. `deadlift_150x4_1`'s worst frame is the LAST frame of the
clip, reached from a start planted where the lifter is re-racking. `_start_ok`
applies the same test: worst frame **14.0 -> 5.5 cm**, inert on every clip that
did not need it.

**Two fixes measured and REJECTED, both recorded in `track.py`:**

- *Radius pinning.* Artifact frames sit at a radius inflated 3-4% and the guard
  only fires outside 0.75-1.33x the lock, so it never fires; legitimate
  variation is 1.05-1.25%. But pinning left the worst frame **unmoved at 14.6
  cm** — clutter simply drags the centre at the locked radius — and cost
  residual on every clip, `bench_spoto_95x5_1` 0.56 -> 2.85 px on a path it did
  not change at all. Radius inflation is a CORRELATE of clutter admission.
- *An appearance veto.* Admitted clutter really is dimmer (worst-inlier sector
  contrast 0.036 against 0.164, 4.5x). But at a 0.10 cut the artifact frames
  retain 2 inliers of 6, below the 4 a fit needs, so it DELETES them rather than
  repairing them — the post-filter's mistake with a better statistic — and costs
  16-19% of motion-blurred frames. The usable discriminator it did expose, not
  built: **blur dims all eight stickers together, clutter produces a mixed
  constellation** (33% bright against 100%).

**State: 16 of 16 clips track**, 0.97-1.00 coverage, eight slots median, none
implausible, **16 of 16 rep counts match the label**. Per-rep video fore-aft is
**4.4-6.0 cm on all six deadlifts** against C27's independent 4.3-6.2, three of
them captures C27 never saw. That replication is the strongest evidence here.

**What re-refereeing did to the pipeline, and the negative half matters more.**
Scored through `metrics.vs_truth` on `c29-jump-state` (step 6 on, C31a's
segmenter):

    capture              CLAUDE.md d ON     vtrack referee
    bench_spoto_95x5_1     3.54 / 0.88        3.64 / 0.89   unchanged, still under
    bench_spoto_95x5_2     4.45 / 0.72        2.41 / 1.52   CROSSES THE NULL
    deadlift_160x6_1       6.65 / 0.25        7.52 / 0.20
    deadlift_160x6_2       4.39 / 0.35        4.40 / 0.35
    deadlift_185x3        10.61 / 0.15       10.72 / 0.14

So **half of P2's referee-versus-pause dissent was a referee artefact and half
is real**, which names `bench_spoto_95x5_1` as the single capture to explain.
Deadlift is untouched — a better referee did not rescue it, so P2's deadlift
horizontal problem is in the reconstruction, exactly where P2 puts it.

**Squat, INDICATIVE ONLY** (`vs_truth` still refuses it; bypassed in
`analysis/tracking/v2_rebuild/code/squatcheck.py`): `beats_null` 0.95-1.31 over
three paused squats, between deadlift's 0.13-0.38 and bench's best.
`squat_pause_140x4_3` is newly scoreable at all — C31's bypass could not use it,
the old tracker putting it at 24.7 cm. `bench_sync` remains unvalidated on squat
and squat still has no phase anchor, so none of it is a result.

**One defect this surfaced and did NOT fix**, since it is the segmenter's:
`deadlift_150x4_1` segments **5 reps against a labelled and video-confirmed 4**
under C31a's rule, with 30.11 cm vertical rms; `deadlift_170x4_3` reads 12.14
against 1.7-4.9 elsewhere. Both 2026-08-08 captures, postdating P1's 124/124.

**A trap fixed in passing:** `metrics.resolve_path`'s cache is keyed by clip and
not by tracker, which was safe only while a directory's inferred tracker never
changed. It changed. A cached read now checks the CSV header's own
`# tracker =` field, so `markers.py`'s paths are re-tracked rather than handed
back as `vtrack`'s.

*Evidence:* `analysis/tracking/v2_rebuild/REPORT.md` and its `code/`,
`tests/test_vtrack.py`, `src/vtrack/path.py`.

---

## C31 — the squat tracker: mechanism found, obvious fix measured and rejected (2026-08-07)

The referee IS the video tracker, so this sits upstream of every number measured
against it. Six of eleven squat clips are unusable and squat has never once been
refereed in this project.

**The mechanism is `static_points`, and it is the limit its own docstring
already named.** C21 added suppression of detections that recur at a fixed pixel
— the camera is on a tripod, so furniture projects to the same pixel and the bar
does not. `recur_max = 0.7` was tuned on `bench_95x2`, whose three real stickers
recur at 0.19 / 0.23 / **0.48**, the 0.48 "because the bar sits racked for much
of the clip". A squat single is motionless for far more of its clip than that.
The docstring says outright that a capture whose bar is still for more than
`recur_max` of its length has ITS OWN STICKERS suppressed and that nothing
detects it happening.

Measured directly, whole-clip travel against a true ~65-70 cm squat:

    clip                    0.70    0.90    1.01
    squat_170x1             14.8    78.9    25.4
    squat_pause_140x4_3     26.1    21.8    55.7
    squat_pause_145x4_1     62.9   194.4      -    <- the one that WORKS

A 5x swing from one number, so suppression is squarely implicated. **But there
is no constant to re-tune to.** 0.70 is right for the capture that works and
wrong for both that do not; 0.90 rescues one and destroys the working one; 1.01
rescues the other. Disjoint, exactly as C31a found for the cadence tolerance.

**The obvious generalisation was built, measured and REJECTED, and why it fails
is the useful part.** Making suppression strength a hypothesis — try several
`recur_max` and let `_trial_merit` choose, exactly as C23 made it choose between
the triangle and conic families — regressed three benches, `bench_92.5x4_1`
going from 27.8 cm of travel to **0.6**.

**`_trial_merit` cannot referee this choice, because it rewards RIGIDITY and
furniture is maximally rigid.** A rack upright gives a perfect full-marker
fraction, a near-zero residual and a zero apparent-size spread — the three
things the merit is built from. So the moment suppression is relaxed, the
merit's favourite object is the thing suppression existed to remove. The merit
was written on the assumption that static points were already gone and is only
valid inside it. A short-circuit that only explored when the default seeding
scored below `MERIT_OK` did not save it either: the regressing benches score
below any threshold that also admits the failing squats.

**What a fix has to do.** Give `_trial_merit` a MOVEMENT requirement before it
can be trusted at low suppression. "The bar is the thing in a gym that moves" is
already this module's stated principle, and `_trial_merit` is the one place that
does not apply it — it measures rigidity, residual and scale stability, all of
which furniture satisfies perfectly. Do not re-propose a `recur_max` ladder
without that; it is measured and it regresses three benches.

Recorded in `markers.static_points`'s docstring so it is read by whoever
next touches suppression. `markers.py` is otherwise unchanged; test_markers
78 passed.

## C31 — the tracking protocol, and the owner's two-class model (2026-08-07)

**Track once, cache to CSV, render a review figure, and LOOK AT IT.**
`src/tracked.py`, `python run.py --track`. Two problems that turned out to be
one.

*Re-tracking was the dominant cost of every analysis* — 1-2 minutes of ffmpeg
per clip, paid afresh on every `metrics.resolve_path` call. The CSVs live in
`<dataset>/tracked/` and are COMMITTED, so the cost is paid once for the life of
the repo. A cached read is ~2 ms against 1-2 minutes and reproduces a fresh
track to 1e-8 m (12 significant figures; at 6 it drifted 1.6e-3 cm, which is
negligible against the spec and still wrong to ship in a repo that checks
regressions by bit-identity).

*And nobody had ever looked at the tracking.* That is the half that mattered.
Running the protocol over the whole corpus found **six unusable squat clips**:

    squat_140x4_3, squat_160x1      REFUSED by the tracker (0.2 and 0.4 cm travel)
    squat_140x4_1, squat_140x4_2    12.5 and 12.7 cm travel
    squat_170x1                     14.0 cm
    squat_pause_140x4_3             24.7 cm

against squats of 65-70 cm, all behind coverage of 96-100% and healthy
residuals. Of eleven squat clips in the corpus, six are unusable and the three
template ones that do track do so at NCC 0.39-0.41. `tracked.review` flags
`implausible` when whole-clip travel falls under the lift's own
`VERTICAL_ROM_M` — the one statistic that catches it — and it is gated on both
the known-bad clips and known-good ones, because a flag that fires on everything
says nothing.

**Two costs of the cache, both real and both documented:** it does not carry the
tracker's own diagnostics, and a cached read does not run `markers.validate`, so
its per-capture warnings do not fire. Re-track with `--track --force` after ANY
change to `markers.py` or `truth.py`.

**The owner's two-class model — IMPACT vs SMOOTH — with the measurement behind
it.** Per-rep fore-aft excursion growth, IMU only:

    deadlift (impact)   n=6    +29.2 %/rep median   6 of 6 POSITIVE
    bench (smooth)      n=11    +0.3 %/rep
    squat (smooth)      n=9     +1.9 %/rep

The invented fore-aft compounds on impact lifts and scatters around zero on
smooth ones, and it resets between sets. The step-by-step allocation — which
steps are shared, which have a premise that breaks at the impact, and which
supplementary steps are measured to help — is in CLAUDE.md under the pipeline
list. Full suite 600 passed / 1 skipped / 8 xfailed / 7 xpassed.

## Done

### B1 — stop applying the pause-derived gyro bias `17d5eee`
Applying `calibrate.gyro_bias` was worse than doing nothing on **13 of 13**
captures. Median per-rep horizontal residual **71.5 cm → 4.2 cm (17×)**, better
on 10/10, worse on none. The correction is now opt-in via `apply=True`.

We log `dm.rotationRate`, which Core Motion has already bias-corrected, and the
residual is smaller than the tremor we measure it in: ~7 °/s p-p at 6.5 Hz
against a 0.1–0.9 °/s bias, block-resampled SEM 0.16–0.36 °/s. A significance
gate was tried and rejected — it passed on 4/10 captures and made all 4 worse,
because SNR tests whether a mean is reproducible, not whether it is bias.

### A1 — rep segmentation `e8a8a0b` `efd5f5c`
**44/44 reps across all 10 captures, zero false positives**, against the old
stationarity segmenter's 0/14 bench and 1/15 squat. *(True as measured. The
2026-07-30 session took it to **71/72** — see P1; `bench_spoto_90x5_1` counted
the re-rack as a sixth rep, and the variant token in its name had kept it out
of the gates entirely. **C5 restored it to 72/72 on 2026-07-31.**)* Shape
matching in a
fixed-*duration* window, floor-impact anchors where the lift provides them
(6/6, 6/6, 3/3), and lateness as the tie-break. Every rep window now contains
both a concentric and an eccentric phase of comparable size (0/44 unbalanced,
was 9/15 deadlift reps holding only the pull).

Phase error later found by A2 and fixed — see below.

### A2 — video ground truth `374392b` `f6ff01c` `09c6bfc`
`src/truth.py`. Plate tracked from footage; first external truth for the
horizontal axis. Video landings match IMU floor impacts 6/6, 6/6, 3/3 at
**11–16 ms rms**, clock drift <0.25%. Deadlift is automatic and unattended.
Bench and squat were "warns" and "raises" here until C8 — see that entry; the
short version is that bench is truth now and squat is further from it than this
line implied. Full detail and ten drawbacks in `src/README.md`.

### #13 — rep-window phase, on deadlift
Windows ran lockout-to-lockout, half a rep out of phase. The cause was not a
bug in `segment.py`: band-passed IMU vertical correlates **-0.82** with video
truth, with 145 cm of in-band error against a 69 cm signal, already present at
the acceleration stage (-0.16). That is P3 — accel bias through a rotating
forearm sits at rep frequency, so no filter removes it. The segmenter was
finding real structure in the error, which is why the count was right and the
phase was wrong.

Where the bar sets down, boundaries now come from the impacts alone, which use
raw acceleration magnitude and match video to 13.5 ms. **All 15 deadlift
windows contain exactly one video lockout.** Bench and squat have no anchor,
still segment on the corrupted velocity, and their phase is unverified — that
needs B2 and B6, not a segmentation change.

### Acceleration sign inversion `3c2cbed`
**Core Motion's `userAcceleration` is the negative of physical acceleration.**
`io.load_log` negates it at the boundary; `synth.py` emits the device
convention so the CSV means the same thing whichever wrote it.

Invisible for months because at rest `userAcceleration` is zero — the gravity
check at the pause, `to_world` returning ~0 while still, and the synthetic
round trip are all evaluated exactly where the term vanishes. `synth.py` shared
the wrong convention with `orient.to_world`, so they agreed with each other and
disagreed with the watch.

Caught two ways: integrating world acceleration over 0.2-0.3 s windows
correlates **-0.76** with the video bar and **+0.76** negated (short window, so
it tests sign not drift); and the floor impact gave a negative velocity step on
all 9 impacts where a floor decelerating a falling bar demands positive. Both
are gates now. Segmentation needed cadence selection afterwards to stay at
44/44.

### A3 — real-data error metrics
`src/metrics.py`. The first measurement of error in this project. Absence of
this is why every stage could pass while the product failed.

`dispersion(reps)` needs no truth and measures rep-to-rep spread on the
normalised-time grid. `vs_truth(result, video)` measures against A2 and raises
rather than returning a number from footage that is not truth. It was deadlift
only when written; C8 added bench, on 3 of 7 captures, and squat still raises.

**Horizontal, as the pipeline ships it: 5.1, 9.2 and 15.4 cm rms per rep**
against a 1 cm spec. **Vertical: 6.8, 8.7 and 3.2 cm rms** against ±2–3 cm.

Three findings that change the work, not just the record:

- **It is 5–15×, not two orders of magnitude.** The older figure came from
  whole-set excursion, which counts between-rep divergence that per-rep error
  does not. Excursion itself is now 3.4–35.9 cm across the ten captures; the
  "66–253 cm" in the A4 note below predates the acceleration sign fix.
- **Vertical is out of spec too.** "Vertical timing and structure come out
  fine" has been repeated since the first analysis and had never been measured
  per rep. It misses ±2–3 cm on all three deadlifts.
- **The per-rep detrend is not where P2 lives.** `vs_truth` reports the error
  with step 7's closure applied to the *video* as well: it moves the number by
  0.2–0.9 cm. B3 is still a real fix — the tracked bar misses closing by
  1.9–4.3 cm horizontally, which step 7 forces to zero — but it is worth a few
  centimetres, not the fifteen that matter. **This demotes B3 and promotes
  B6.** The error is upstream, in the acceleration reaching the integrator.

A fourth finding, unlooked for. `vs_truth` resolves the fore-aft sign **once
per set**, because that is what step 8 can do — resolving it per rep would let
a mirrored rep be corrected for free and flatter the metric. Doing it properly
then exposes that **4 of 6, 2 of 6 and 1 of 3 reps individually prefer the
opposite sign**. The horizontal reconstruction does not agree with itself about
which way forward is, within a single set. That is B4 evidence nobody had, and
it raises the question of whether a per-set axis is the right object at all.

`analysis/19` shows the shape: horizontal error is a single smooth arch across
each rep, peaking 0.5–0.7 through it. That is P3 seen directly rather than
inferred.

Two gates in `tests/test_real_data.py`: ceilings pinned at today's numbers so
they can only improve, and an `xfail` carrying the actual 1 cm spec so it is
executable and visible on every run.

**dispersion flatters a broken pipeline and the tests say so.** It reports
0.7–1.3 cm on bench and squat, inside spec, where nothing is verified at all —
because error that repeats every rep lands in the mean rep and cancels. Never
quote it alone.

### B5 — accelerometer saturation: there isn't any
**Nothing in `data/raw/` clips.** `deadlift_180x3` peaks at 21.78 g and used to
trip `check_log`'s 16 g threshold, which was an assumption about a sensor
nobody had checked. It is a genuine reading: every per-axis extreme is reached
by exactly one sample and none is a round number. A railed sensor repeats one
value across consecutive samples. `io.clipped_runs` now tests for that instead
of for magnitude, and `check_log`'s warning went with the threshold.

**The impact impulse survives 100 Hz too**, which was the follow-up question
and the more interesting one. A 20–30 ms impact is 2–3 samples and looks
unrecoverable, but measured against video the integrated velocity step comes
out at ratio 0.77–1.19 on both 155 kg captures, median **1.04** over all 15
impacts. See `analysis/20`.

**I got that wrong first and the plot caught it.** The first measurement said
16–27% of the impulse was lost, from two mistakes: predicting arrival velocity
as `sqrt(2gh)` when a touch-and-go deadlift is *lowered under control* and
arrives at ~2 m/s rather than 3.3; and measuring the step as a net change
across a window that spans the rise and the fall into the next descent. Both
are recorded in `io.py` and in the test, because they are easy to repeat.

**What is real: `deadlift_180x3` over-reads the impact step by 58–72%**, alone
among the three, and it is also the worst capture by horizontal error (15.4 cm
against 5.1 and 9.2). Heaviest bar, hardest landing. That is the first specific
hypothesis anyone has had for why that capture is an outlier, and it points at
strap ring — which is what #14's `strap_resonance` was written to detect and
currently detects backwards. Pinned per-capture in the gates rather than
averaged away.

Also killed on the way past: per-rep peak g does **not** predict per-rep error.
Correlation +0.17 across all 15 deadlift reps. A 3-rep pattern in `180x3`
suggested otherwise and did not survive the other 12.

### B7 — floor-impact anchor: REJECTED on measurement
Proposed after B5, on the reasoning that the bar's state at the floor is known
(velocity zero, same height every rep) and the pipeline spends that on
segmentation alone. Built, measured against a decision rule stated in advance,
and it lost. `analysis/22`.

| variant | horizontal, per capture | vertical |
|---|---|---|
| shipping | **5.1 / 9.2 / 15.4** | **6.8 / 8.7 / 3.2** |
| anchor + all-axis closure | 10.4 / 7.4 / 10.2 | 15.3 / 18.0 / 4.5 |
| anchor + vertical-only closure | 19.2 / 29.2 / 46.9 | 15.3 / 18.0 / 4.5 |
| vertical-only closure, no anchor | 495 / 522 / 337 | — |

**Why it failed, and it is not the detector.** The A3 error is a smooth arch
peaking mid-rep. An impact anchor acts only at the rep boundaries, where the
error is already ~0 by construction — a true constraint in the wrong place. The
third panel of `analysis/22` is the whole argument in one picture.

**What the ablation settled, which is worth more than the feature.** Row 4 says
the horizontal closure everyone (including me) has been calling false is doing
**metres** of load-bearing work: remove it with nothing in its place and error
goes to 3–5 m. It remains wrong — the bar really does miss closing by 1.9–4.3 cm
— but it is wrong and *essential*, so B3 cannot simply drop it. That reframes
B3 from "remove a false assumption" to "find something that can replace it".

**Kept:** `segment.rest_instants`, which is validated and gated against video
— 13 of 15 impacts within 0.05 m/s of true rest, against 0.4–1.0 m/s at
`impact_anchors`, which marks the spike ONSET rather than rest. The two it
rejects are the final impact of a set, where the lifter releases the bar; the
`max_accel` gate drops them rather than returning them wrong.

*B6 did want it, used it for the splice, and the splice lost too — for the same
reason B7's anchor did. The detector still survives both: it is what
`metrics.momentum_closure` measures against, and that is now the sharpest
diagnostic in the project. The DETECTOR was never the problem; what fails is
using one instant per rep to replace a constraint that spans the whole rep.*

**A claimed win, since retracted.** This entry originally recorded that fitting
`detrend_rep`'s line through a 5-sample median took horizontal from 5.1/9.2/15.4
to 4.6/7.8/13.4. B2 found that was an artefact: the drift was measured between
the two medians, which sit at t[edge/2] rather than at the ends, then applied
across the full window — a 1.7% under-correction. The gain was that accidental
shrinkage, not the median. With the baseline fixed, `edge=5` gives 10.08 cm mean
against 10.01 at `edge=1`; the median is worth nothing and now defaults off.

**Reverted:** `correct.anchor` and the pipeline wiring, deleted rather than
left behind a flag.

### A4 — end-to-end driver `91ed978`
`src/pipeline.py` + `run.py`. The pipeline had never been executed end to end
against a gym capture; every prior real-data result came from scripts outside
the repo. Does not raise on unimplemented stages — records them as blocked and
returns what worked. Surfaced `io.check_log` and `segment.quality_flags`, both
previously dead code.

### C4 — measured plates and ROM bounds
Two tape measurements turned into gates. Plate diameters (425 notched / 445
bumper / 450 calibrated) replaced `truth.PLATE_DIAMETER_M`'s single assumed 450
and moved A3 by under 1%. Per-rep vertical ROM ceilings (bench 35, squat 76,
deadlift 61 cm) became `truth.VERTICAL_ROM_M`, applied by `pipeline.run` to the
reconstruction and by `metrics.vs_truth` to the video.

Four results, in descending order of how much they change what we believe:

1. **The video's vertical scale is wrong, per capture, by up to ±20%.** The
   referee for P2. Three deadlifts, one lifter: 59.1 / 66.8 / 47.6 cm. Diameter,
   radius quantisation and tracker drift all tested and ruled out.
2. **The reconstruction passes on all 17 captures** bar two known defects, and
   is more self-consistent on vertical ROM than the video judging it.
3. **Rep counting went to 71/72, not 44/44** — `bench_spoto_90x5_1` counted the
   re-rack, hidden by a regex that did not match the variant token in its name.
   *Fixed by C5 on 2026-07-31; counting is 72/72.*
4. **`squat_160x1` reconstructed 18.0 cm at a correct count of 1 of 1** — the
   first right-count-wrong-window failure any gate here has caught.
   *Fixed by C5; it reads 67.0 cm.*

`analysis/23_rom_bounds.png`, `python run.py --rom`.

### #14 — the strap-resonance flag, REMOVED on measurement (2026-07-30)
It was promoted by B5 and again by B6, on the reasoning that the ringing after a
hard landing is strap compliance and this flag exists to catch it. It does not
catch it, and cannot.

**It rejected 33 of 73 real reps** — worse than the 12 of 44 recorded here, the
gap being captures added since. Rejection rate by lift: bench **26/30 (86.7%)**,
deadlift **6/15 (40.0%)**, squat **1/28 (3.6%)**. Hard landings happen on
deadlift and nowhere else, so the flag was ANTI-correlated with the phenomenon
it claimed to detect, firing hardest on the quietest lift.

**Neither formulation can work.** As a *fraction* of band energy it flags quiet
reps for having little signal at all — the bug recorded above. As *absolute*
energy, which its docstring intended, it separates by lift and nothing else:
squat 3e3–4e4, bench 6e3–1.4e5, deadlift 5.8e5–7.4e6. An absolute threshold is a
deadlift detector, because the floor impact is real broadband signal.

**And there is no resonance to find at 100 Hz.** The spectrum of the 400 ms
after each of the 15 floor impacts peaks at 10, 12.5, 15, 20, 22.5, 27.5, 30,
32.5, 35, 42.5 and 47.5 Hz — no repeatable frequency — with peak/median of
2.7–12.5, which is not narrowband. Nyquist is 50 Hz and a watch-on-strap
resonance is plausibly above it, so whatever exists aliases to an arbitrary bin.
You cannot detect what you cannot resolve.

The ringing B6 measured is still real and still where the deadlift's error
enters. But a broadband transient is not a detectable resonance, and discarding
the rep was never the right response — the fix belongs in the reconstruction.

`clipped` survives and now delegates to `io.clipped_runs`, a real rail test,
instead of thresholding against an assumed 16 g full scale that B5 disproved in
`io.check_log` a day earlier and that this copy outlived. Rejections are now
0 of 73, which is correct: nothing in `data/raw/` clips.

### C16 — the watch workout session, restored on measurement
`watch/`. **C7 (below) is reversed.** Its own named falsifier has been collected,
by accident, in a real gym session: captures stopped surviving the wrist going
down, and a workout already running in the Workout app took priority while the
wrist was down, so this app was the one suspended. Too few samples to use — that
session's raw data is unusable.

**What C7's drop tests actually proved is narrower than what was concluded from
them.** Both were taken with the app FRONTMOST and the screen merely DIMMED.
Core Motion does keep streaming through that state and those numbers stand. It
is not the gym state: there the wrist drops, watchOS returns to the clock or
hands the foreground to whichever app has a live workout, and a backgrounded app
with no session of its own is suspended. *Frontmost-and-dimmed* and *replaced*
are different cases, and only the first was ever tested.

This is the project's recurring failure shape, in the watch code this time: an
aggregate that passes while the thing fails exactly where it matters. Same as
`truth.validate` checking a whole-clip median while the tracker was lost at
lockout (C12).

**What shipped.** The `HKWorkoutSession` is back, and back as the workout of
record rather than a hidden keep-alive — one session per device means there is
no way to share, join or even detect the Workout app's, so taking it quietly
would end the owner's workout, which was the original bug report. So the app
replaces the Workout app for a lifting session:

- **Workout screen**, reserved for it — elapsed clock, heart rate with average
  and peak, active and total calories, captures saved this workout, and
  `Start Workout` / `End Workout & Save`. Ending is disabled while a capture
  runs, since ending drops the keep-alive mid-recording.
- **Capture screen**, the protocol unchanged — name, opening anchor, reps,
  closing anchor — and a red warning when no session is running during a
  recording.
- **Effort rating**, 1-10 on Apple's wording, saved with
  `relateWorkoutEffortSample` so it attaches to the workout rather than
  free-floating. `Skip` is first class.
- `Calibrate` auto-starts a session if the lifter went straight there, because a
  capture recorded without one is invisible until the CSV is on the Mac.
- The session delegate announces a stolen or lost session with a haptic. It
  cannot be prevented, only noticed; the original build had no delegate at all,
  which is how the first collision went unseen for the life of the app.

**Deliberately not done: a pause control.** A paused session is not a running
session, and "the session is running" is the whole reason the app can record
with the wrist down — a pause button is a one-tap way to break a capture
silently.

**Minimum deployment is now watchOS 11.0**, and it is exactly four symbols, all
in the effort rating: `workoutEffortScore` (twice), `HKUnit.appleEffortScore()`
and `relateWorkoutEffortSample`. Measured, not assumed: the sources typecheck
clean at `-target arm64_32-apple-watchos11.0`, `...12.0` and `...26.0`, and fail
at `...10.0` on those four and nothing else. The `#available` guards an earlier
build used to hold the target at 10.0 are gone.

The watch target needs the **HealthKit** capability and the **Workout
Processing** background mode again, plus `NSHealthShareUsageDescription` and
`NSHealthUpdateUsageDescription`. `watch/README.md` carries the full record.

*Not yet verified on device.* The reversal rests on the owner's gym report and
on the mechanism, not on a fresh instrumented capture. The check is a capture
with a session running and 30+ s of genuine wrist-down: look for gaps in `dt`,
not at the sample counter, which rises either way.

### C7 — the watch workout session, removed on measurement
***Superseded by C16 above, 2026-08-01. Kept because the reasoning trail is the
point: this entry is what a well-measured wrong conclusion looks like.***

`watch/`. The app held an `HKWorkoutSession` while recording, on the documented
belief that it was the only thing keeping Core Motion alive once the wrist drops.
That cost the owner their own workout — watchOS allows one primary session per
device, so logging ended whatever the Workout app was running.

The first fix kept the session and made this app *be* the workout: saved to
Health, live metrics, effort rating. It worked, and it imposed a workflow change
to solve a problem nobody had measured.

**Measured, 2026-07-30. The premise was false.** Two captures with no session:
47.08 s with zero gaps over 15 ms, and 58.78 s with **zero gaps at any
threshold** — including a 19.9 s and a 16.5 s span with the wrist still and the
screen dimmed, and a notification raised and dismissed mid-capture. 100.06 Hz
throughout, zero repeated rows, `check_log` clean.

So the session, the workflow change, the metrics screens and the effort rating
are all deleted, and the watch target no longer needs HealthKit or any
background mode. The sources now typecheck at watchOS 9.0.

*Untested, and the thing to check first if captures ever truncate:* the app being
genuinely REPLACED mid-capture — watch face or another app — for longer than the
~6.5 s the first test covered. Return to Clock will not fire inside a single set,
which is why this is judged safe. `watch/README.md` carries the full record.

**That paragraph was right about what to check and wrong about the risk.** It
happened, it cost a session's captures, and "Return to Clock will not fire inside
a single set" missed the case that actually bit: another app holding a live
workout takes the foreground while the wrist is down. See C16.

*(Numbering note: the watch code called this C4, which collides with C4 above.
It is C7.)*

### C6 — the two anchors, measured
`calibrate.anchor_tilt`. The measurement C1 was built for, on the seven captures
that carry both holds. **A set does no lasting damage to Core Motion's
attitude**: tilt error bounds at 0.05° at the opening anchor and 0.14° at the
closing anchor, worst case 0.27°, across 39–56 s with 20 g impacts in it.
Gyro-only propagation over the same span drifts 0.35–1.49°, so the fusion is
working, not being corrupted.

*Two limits, both found by asking whether the watch is in the same posture at
both anchors. It is not — it rotates 3.5–161° between them, mostly yaw.*

- **These are upper bounds and the change between them means nothing.** The
  residual is tilt leak plus body-frame accel bias rotated into the world, and
  0.0025 g of accel bias is exactly g·sin(0.143°) — the closing-anchor median.
  True tilt is between zero and 0.14°.
- **Yaw is unobservable.** Gravity constrains roll and pitch only, and the
  logger uses `.xArbitraryZVertical`. Bounded indirectly at 0.0–1.4° per set,
  which is 2.4 mm on a 10 cm excursion — below spec, so the question closes
  anyway.

Four consequences:

1. **B1's default is confirmed on the evidence its docstring asked for.** The
   two-anchor baseline gives 0.014 °/s of effective drift against a pause
   estimate of 0.1–0.9. Ten to sixty times too large.
2. **P4's two-degree attitude error is retracted.** It converted a *vertical*
   residual with the *horizontal* leak formula — 0.035 g of vertical needs
   15.2°, not 2.0° — and the figure is pre-sign-fix and does not survive anyway
   (`bench_92.5x2` now reads 0.0005 g).
3. **C1 cannot see P3's error, by construction.** The anchors sample the
   attitude when it is most likely right: still, no linear acceleration. P3
   lives during the rep. What sees it is the per-rep mean, which must be zero.
4. **P3 has a location for the first time.** Bench and squat leave 0.003 g per
   rep, the sensor's own floor. Deadlift leaves 0.010–0.030 g, and ±100 ms
   around each impact — 6% of samples — carries three quarters of it.

Plus a defect nobody had recorded: deadlift vertical momentum does not close.
Not a contradiction of B5, whose 1.04 is a local step measurement; the deficit
is in the rest of the rep, and step 7 hides it.

*Two corrections since, both narrowing it rather than withdrawing it.* C6 first
read −0.05 to −2.36 m/s on 15 of 15, measured over impact-to-impact rep windows;
those windows put every boundary 10 ms after its impact, one sample into a 2–3
sample spike, so the figure inherited the boundary placement. Measured between
`segment.rest_instants` instead it is **−0.37 to −1.48 m/s on 8 of 9**. C11 then
localised it: see B6.

`analysis/24_c6_two_anchors.png`, `python run.py --anchors`.

### C8 — bench becomes truth; the referee gets its own test file
`src/truth.py`, `src/metrics.py`, `tests/test_video_truth.py`. Bench video was
the third referee this project has had and the first that had to be argued for
rather than measured, so the argument is recorded in full.

**Bench tracks.** Two changes, and the second was the real blocker. A
hand-placed `truth.SEEDS` entry per capture, because four automatic seeders all
preferred the bench-and-lifter silhouette. And `truth.template_half`, because
`track`'s default `half=48` builds a 97×97 px template — larger than a bench
plate's inscribed square, so its corners held static ceiling and the tracker
part-anchored to the gym. On `bench_90x4_1` whole-clip travel reads
**16.8 / 22.4 / 30.9 / 31.0 cm at half = 48 / 40 / 32 / 24** against a real ROM
of ~29 cm. All seven now track at 0.75–0.95 NCC with 21.8–29.8 cm of travel and
a video rep count matching the label 7 of 7.

**Bench syncs, on 3 of 7, and the calibration is the interesting part.** There
is no floor impact, so `metrics.bench_sync` cross-correlates the video's
vertical bar velocity against the reconstruction's. That is only usable because
the same correlation can be tested on deadlift, where `truth.sync` already knows
the answer from landings matched to impacts — it recovers it to **+3, −14 and
−18 ms**. The correlation VALUE there is only 0.774 / 0.708 / **0.595**, which
is what set the threshold: `SYNC_MIN_CORR` is 0.55, the midpoint of a gap
between the highest bench correlation that must be refused (0.509) and the
lowest deadlift correlation known to be correct (0.595). Margins ~0.04 each,
neither large.

**Two corrections to work that arrived in the same diff, both caught by running
it.** The version handed over claimed bench correlations of 0.96–1.00 and shipped
`SYNC_MIN_CORR = 0.70`; measured, they are 0.37–0.70 and all seven captures
raised. And `metrics.vs_truth` was calling `_video_on_imu_clock(log, ...)` after
its signature changed to take `result`, so **every** call raised `KeyError` —
including the three deadlift A3 regression gates, which were dark. The suite was
17 failed / 288 passed and was reported as passing.

**A rejected anchor, recorded because it looked convincing.** The obvious check
on a bench sync is the re-rack: video sees the bar stop, IMU sees a transient.
Tested on deadlift where truth is known, it misses by **+615, +660 and +510 ms**
— a systematic half-second, because "last motion" and "last transient above 3 g"
are not the same event. On bench it appeared to disagree with the correlation by
53–706 ms, which read as evidence against the sync until the deadlift control
showed the error was the anchor's own. `truth.rack_impact` was deleted; a
comment marks the spot. **Do not re-propose it without a way to separate the
two events.**

**What bench measures, now that it can.** Horizontal **3.67, 2.69, 2.63 cm rms**
per rep — outside the 1 cm spec by 2.6–3.7×, where deadlift is out by 5–15×. And
`reps_disagreeing_on_sign` is **0, 0, 0**, against deadlift's 4 of 6, 2 of 6 and
1 of 3. Whatever makes deadlift's fore-aft direction disagree with itself within
a set is not doing so on bench.

**The load-bearing assumption, stated so it can be attacked.** Bench sync's
validation is *transferred* from deadlift, not measured on bench. Its falsifier
is a bench capture whose correlation clears 0.55 and whose lag is demonstrably
wrong, which needs a synchronous event visible in both modalities — a
clapperboard would do. Nothing in `data/raw/` can currently test it.

**And the peak is weakly isolated on bench.** Its best rival more than 0.4 s
away reaches 0.80–0.81 of the peak, against 0.51–0.74 on deadlift where the peak
is known correct — so bench is outside the range the method is validated in. The
cause is that a set is periodic: the rival lags are −2.81, +0.85 and −3.465 s
against a ~2.9 s cadence, so the alternative pairs rep *n* with rep *n+1*.

The cost of that turns out to be nil for what is quoted. Scoring at the rival lag
gives horizontal 3.11 / 3.23 / 2.44 cm against 3.67 / 2.69 / 2.63 — no worse.
**And that is a fact about the metric, not about bench:** shift a deadlift by
3 s and horizontal moves 5.05 → 4.62, 9.19 → 7.23, 15.44 → 15.17 while vertical
goes 5.24 / 6.60 / 5.24 → 19.08 / 20.19 / 32.41. `vs_truth`'s horizontal rms
does not test time alignment on any lift. Worth knowing before anyone cites it
as phase evidence.

Squat moved the other way: `find_plate` no longer lets a disc hanging off the
frame edge win by being scored against zero-padding, which stopped three
2026-07-30 squats crashing — but two still raise and two report ~12.5 cm against
a 45–76 cm band. **That converted a crash into an honest refusal, not into a
track.** `vs_truth` refuses squat. *(Superseded 2026-08-15: the refusal is
removed and squat is scored through `src/vtrack/` — see G2 at the top. The
tracker and footage this paragraph is about were deleted by F1.)*

`analysis/29_bench_video_truth.png`, `tests/test_video_truth.py`.

**What this unlocked: P1's bench phase question**, which C9 answered the same
day. See the next entry.

### C10 — the null model, and why four benches were being refused
`src/metrics.py`. Started as a diagnosis of C8's 3-of-7 split and turned up
something larger on the way.

**The null model. Six of ten captures are worse than a flat line.** `vs_truth`
now reports `null_h_rms` — what you score by drawing NO fore-aft motion at all —
and `beats_null`. Measured:

| capture | pipeline | null | |
|---|---|---|---|
| bench_90x4_2 | 0.64 cm | 3.08 | **4.80× better** |
| bench_90x4_3 | 0.76 | 3.06 | **4.03× better** |
| bench_92.5x2 | 2.75 | 3.13 | 1.14× |
| bench_90x4_1 | 1.88 | 2.07 | 1.10× |
| bench_spoto_90x5_3 | 2.63 | 2.42 | **0.92× worse** |
| bench_spoto_90x5_2 | 2.69 | 2.16 | **0.80× worse** |
| bench_spoto_90x5_1 | 3.67 | 2.63 | **0.72× worse** |
| deadlift_155x6_1 | 5.05 | 3.55 | **0.70× worse** |
| deadlift_155x6_2 | 9.19 | 3.23 | **0.35× worse** |
| deadlift_180x3 | 15.44 | 1.96 | **0.13× worse** |

P2's "5–15× outside spec" is measured against the spec. Measured against doing
nothing, **all three deadlifts are worse than useless on the horizontal**, by up
to 7.9×. One line of arithmetic, never run before. It is a permanent output now.

**Two bench captures meet the 1 cm spec — the first in this project.** 0.64 and
0.76 cm. Checked for the obvious artefact and it is not one: those two have the
LARGEST video fore-aft travel of the seven (5.41 and 5.61 cm) and beat the null
by 4×, where a flat-line artefact would show small error on small travel.

**Why four benches were refused, and it was our fault not theirs.** C8's
`SYNC_MIN_CORR` was a peak-height threshold, and peak height here conflates
agreement with what fraction of the record contains lifting — the correlation
runs over the whole overlap. Bench clips are 20–30% reps; deadlifts are 50–56%.
Restrict the correlation to the rep span and every bench rises to 0.886–0.996
while deadlift moves only to 0.883–0.892: the gap that justified 0.55 vanishes.
The correlations ordered perfectly by rep count (2 reps → 0.367, 4 → ~0.50,
5 → ~0.69), which is what gave it away.

**Restricting is not the fix, and that is the interesting half.** The non-rep
time is what breaks the degeneracy. Restricted, bench sidelobes climb to
0.86–0.99 — `bench_90x4_1` reaches 0.985, a coin flip — because "align rep n
with rep n" stops being distinguishable from "align rep n with rep n+1".
Deadlift survives restriction (0.55–0.76) because it is genuinely aperiodic.
**Dilution is the price of identification.**

**So accept on the SHAPE of the curve.** Every rival above `RIVAL_FRAC` of the
peak must sit within `PERIOD_TOL` of a whole rep period. Measured across all
seven captures, as offsets from the peak in each capture's own cadence: **eleven
rivals, every one at 0.96–1.05 periods.** Not one fractional. So bench's lag is
identified modulo one rep, always, and never worse — and both quantities
measured through it are invariant to a whole-rep shift. All seven sync.

A fractional-period rival would be a real failure and is what it refuses on. No
capture produces one, so **that branch is unexercised on real data — a guard,
not a measurement.** And a bench single cannot be synced by this route at all,
since a cadence needs two reps; it raises rather than guessing.

`analysis/29` redrawn.

### C9 — bench rep-window phase, measured for the first time
`tests/test_real_data.py`, `analysis/30_bench_window_phase.png`. The half of P1
that CLAUDE.md called the one that matters, on the lift that just acquired an
external clock.

**Bench windows are in phase: 15 of 15 hold exactly one video chest touch**, at
0.567–0.648 through the window. The failure mode is 0.0/1.0 — that is where
deadlift's old 44/44 segmenter actually sat, holding the descent of one rep and
the ascent of the next — and nothing is near it.

**The touch sits at ~0.60, not 0.50, and that is the bar rather than a bias.**
Checked rather than argued: measured in the video alone, with no IMU and no
sync, the descent takes **0.573 / 0.590 / 0.582** of a rep against the IMU
windows' **0.593 / 0.613 / 0.619**. A bench descent is controlled and a press is
not — 1.6–1.9 s down against 1.2–1.3 s up. The modalities agree to 0.02–0.04 of
a rep, i.e. 60–100 ms.

**It survives C8's weakest point rather than depending on it.** `bench_sync`'s
peak is weakly isolated with rivals one rep period away, but a whole-period
error is invisible to a phase test *by construction* — a periodic set looks
identical shifted by one rep. So the ambiguity the sync cannot resolve is
exactly the one that cannot corrupt this. A fractional-period error would show
and does not: the three agree to 0.03 despite offsets of +0.040, −2.320 and
−0.585 s.

**What it does not say.** It fixes where the window sits relative to the bar,
not whether the path reconstructed inside it is right — that is P2's
2.63–3.67 cm. And it says nothing about squat, which has no external anchor of
any kind and is now the only lift whose phase is unverified. Squat's fix is the
capture protocol, not code.

### C11 — the vertical deficit is the landing, and only the landing
`src/metrics.py` (`momentum_closure`), `src/plot.py`, `run.py --closure`,
`analysis/31_c11_momentum_closure.png`, `tests/test_real_data.py`. The
impact-free control the C6 deficit had been waiting for since it was found.

**The identity.** Between two instants where the bar's velocity is zero, the
integral of its vertical acceleration must be zero. No model, no assumption
about how lifting behaves, nothing tunable. It is also **immune to the defect
that flags half the vertical numbers in this project** — the video's per-capture
vertical scale can be 20% wrong and still cannot move a zero crossing, so the
video is used only to say *when* the bar was still, never how far it went.

| intervals | n | median | worst |
|---|---|---|---|
| bench, real lifting | 44 | −0.013 m/s | 0.102 |
| deadlift, floor→lockout (the pull) | 8 | −0.010 m/s | 0.063 |
| deadlift, interval containing a landing | 9 | −0.589 m/s | −1.428 |

**The middle row is the result, and it took two wrong readings to see it.** Those
are 55–66 cm loaded pulls *from the same captures as the failing row* — the dwell
detector splits a deadlift rep at the lockout, so the concentric and the
descent-plus-landing are measured separately. Same lift, same load, same wrist,
same calibration, same thirty seconds of tape. Only the landing differs. That is
a within-capture control, which the bench-vs-deadlift comparison this was built
to make is not; bench then confirms it independently on a lift with no landing
anywhere in it.

*Both wrong readings are worth keeping.* They were first taken as "deadlift
closes except across an impact" (over-claiming: it does, but the evidence had to
be shown to contain lifting) and then as "the bar sitting on the floor"
(under-claiming, from a max-|accel| of 0.6–1.1 g). **A 155 kg pull leaves the
wrist's total acceleration barely above 1 g, indistinguishable from resting.**
The video's bar travel is what separates them; peak acceleration cannot.

**Where it enters.** Split each failing interval at the impact: before it the
reconstruction tracks the video's descent velocity to +0.14…+0.71 m/s, small and
of the *opposite* sign to the deficit. The error in the step across the impact is
−0.11…−1.54 and tracks the interval total. Injected at the landing, not
accumulated through the descent.

**And B5 is reconciled, not contradicted.** B5's 1.04 is min-to-max AMPLITUDE
within ±0.3 s and its docstring explicitly warns off net-change windows; C11
measures the NET, which is what the identity constrains. Same 15 impacts:
amplitude 1.10, net 0.41. **The spike's size is captured; where the velocity
settles afterwards is not.** That is B6's ringing, promoted from a described
wobble to the whole deficit, and it tells B6's splice what to preserve.

**What this closes.** The integrator, the attitude and the calibration are not
the problem on the vertical: 52 intervals of loaded lifting close at the
sensor's own noise floor. Gated as a PASS in `test_bench_vertical_momentum_
closes`, unusually for this file, so a regression in the one lift that works
will fail the suite.

### C12 — the deadlift referee is lost at lockout
`src/truth.py` (`top_of_travel_score`, `validate`), `src/metrics.py`
(`video_top_ncc`), `tests/test_video_truth.py`,
`analysis/34_video_truth_lost_at_lockout.png`.

**Found by eye, not by a gate.** The owner read `analysis/33` and objected that
the deadlift video truth traces a flat ~10 cm horizontal line at the top of the
pull, which is against the logic of the lift — at lockout the bar is held
against the thighs and is very nearly still. Correct, and it had never been
checked: nothing in the project asked whether the referee was right *anywhere in
particular*, only on average.

**Total, and stratified perfectly by height.** Top-of-travel NCC
**0.371 / 0.395 / 0.440** against whole-clip medians of 0.830 / 0.846 / 0.937.
Frames in the top 10 cm scoring below `GOOD_SCORE`: 166/166, 149/149, 146/150.
In the bottom 10 cm: 1/743, 0/780, 0/588. Bench is the control and holds at
0.563–0.850, higher than its own median on the spoto captures.

**Why nothing caught it:** `validate` checked the whole-clip MEDIAN, and lockout
is 8–15% of a clip. The same shape as milestones 1–6, as C8's peak-height
threshold, as C10's clip-composition artefact — an aggregate that passes while
the thing fails where it matters. That is now four times. **A referee needs
checking where it is used, not on average.**

**The cost runs opposite to intuition.** The invented fore-aft motion is part of
the video's fore-aft signal, and `null_h_rms` is the rms of that signal — so the
failure INFLATED the yardstick `beats_null` divides by. Deadlift `beats_null`
restricted to well-tracked frames: **0.70 → 0.59, 0.35 → 0.21, 0.13 → 0.07.**
Horizontal magnitude barely moves, so P2's 5–15× stands; the `beats_null`
figures were too generous by 15–45%.

**Not the template size**, which was the first guess: shrinking `half` raises
NCC to 0.69 and makes the track worse, ROM inflating 60.5 → 74.1 cm against a
61 cm ceiling. The fix is the camera, not code — see Capture protocol.

**And it probably explains C4's ±20% vertical scale error.** Per-rep ROM is
lowest-to-HIGHEST tracked point, so the highest point is measured exactly where
the tracker is least reliable. C4's surviving guess was right in location and
now has a mechanism. Unproven: testing it needs footage that tracks at lockout.

### C11b — `beats_null` is executable
`tests/test_real_data.py`. C10 measured the null model and nothing asserted on
it. Now two gates: a per-capture non-regression floor at 20% headroom, and an
xfail carrying the target (`beats_null > 1` everywhere) that reports 6 xfailed
and 4 xpassed — the four benches that genuinely beat a flat line. The cheapest
available guard against reporting a change as an improvement when it still loses
to drawing nothing.

### C13 — the concurrency protocol (2026-08-01)
Process, not pipeline: nothing here touches a reconstruction. Agents now work
this repo concurrently and independently, so `HEARTBEAT.md` — committed empty in
`88c8585` — becomes the board that keeps two of them off the same file. Rules in
`CLAUDE.md` **Concurrency protocol** (binding), format in the board's own header,
gated by `tests/test_heartbeat.py`.

Claim before you write, release when you stop, and if what you need is held do
other work or stop — do not break the lock. Races resolve by **earlier `since:`
wins**, which works only because blocks are appended and never rewritten.

Four decisions worth keeping, because each was a live failure mode rather than a
style choice:

- **The board is at the shared checkout, by absolute path.** A claim written
  inside a worktree is invisible to every other agent, so it is not a claim. This
  bites precisely the agents most likely to be running concurrently.
- **Its churn is never committed**, so the file that prevents conflicts does not
  itself generate merge conflicts on every branch. The cost is a permanently
  dirty `HEARTBEAT.md` in the shared checkout, and the hazard that `git stash` or
  `git reset --hard` there destroys every live claim in the repo.
- **Shared docs are claimed late and briefly.** `CLAUDE.md`, `TASKS.md` and the
  READMEs are touched by nearly every task, and the same-commit docs rule means
  an agent holding them for the length of its work blocks everyone.
- **`analysis/NN_*.png` numbers are reserved by claiming the filename** before
  the plot exists. Two agents otherwise both take the next free number and one
  overwrite is silent.

The gate is a **format** gate and says so in its docstring: it checks the board
parses, that a block's status matches its section, that no two *active* claims
overlap (subtree-aware, so `src/` collides with `src/segment.py`), and that
nothing claims immutable `data/raw/`. Verified against a populated board on 11
hand-built cases — the healthy two-agent board, both overlap forms, the plot-
number collision, each malformed field, a released block left under Active, and
the two that must *not* fire: released claims may overlap freely, and the worked
example in the fenced header is not a live claim.

**What it does not do.** It is advisory and there is no enforcement at the
filesystem, so it fails exactly when an agent skips the read — and a skipped
claim is invisible until two edits collide. A clean board means "nobody has told
me otherwise", not "the repo is free".

### C14 — task focus, and CLAUDE.md trimmed (2026-08-01)
Process, like C13. Working style gains **"Stay on the task you were given"**:
one problem at a time named up front, findings off to the side get *recorded not
fixed*, no refactoring code you merely had to read, and if the task looks wrong
say so in a sentence and do it anyway rather than silently substituting a better
idea.

Open problems was **566 of 776 lines** — CLAUDE.md had become the work log
`TASKS.md` is supposed to be. Trimmed to 526 by compressing four things whose
detail was verified to exist here first: P5 (a CLOSED problem carrying 67 lines
inside *Open* problems), P4's retracted 2° attitude error, P1's C5 mechanism
walkthrough, and a P2 paragraph that re-explained the C12 finding stated at the
top of the same section. **Nothing was deleted outright** — the detail moved to
C5/C6 here, and CLAUDE.md now points at them.

Deliberately left long: P1's live caveats, P2's measurement tables, P3 and P6.
That is the live state of the problems, and `Working style`'s "correct the old
reasoning rather than deleting it" makes the corrections themselves load-bearing
— this project has been bitten four times by a claim outliving its evidence, and
the stacked corrections are the defence. If more trimming is wanted, P2's
chronological "READ THIS FIRST / SECOND / third / fourth" stacking is the next
target, and it is a reorganisation rather than a deletion.


### C15 — the sticker tracker (2026-08-01)

`src/markers.py`, `tests/test_markers.py`, `analysis/35`, `36` and `37`.

The 2026-08-01 gym session produced **video only, no IMU** — so `data_v2/` has a
`video_only/` directory and five clips, and nothing here can be scored against a
reconstruction. What it did produce is a tripod and markers: three
retroreflective discs near the plate rim about a third of the circumference
apart, one on the bar's end cap, ~1.5 cm each.

**What it fixes, and it is a feature change rather than a code change.**
`truth.py`'s two measured defects both come from tracking a dark plate by
template. `analysis/36` reproduces both on the new footage: NCC falls from ~0.85
at the floor to ~0.3 at lockout on all three deadlifts (C12, on captures C12
never saw), and on `bench_85x6` the template scores its *highest* median NCC of
the five, 0.95, while reporting 0.2 cm of travel over six reps. A bright marker
on a dark plate has contrast regardless of the background; three in a rigid
triangle measure their own scale every frame.

All five captures track 100% of frames with all three rim markers, at 0.15-1.10
px fit residual. All five sit inside `truth.VERTICAL_ROM_M`. Deadlift travel
spans 4.8 cm against the template's 10.7 cm on identical footage. Rep counts
read off the vertical trace match all five labels — 5, 5, 1, 6, 1 — which
nobody designed for and which is the cheapest confirmation in the set.

**Four things this cost, worth keeping because each was a wrong first answer.**

*Markers cannot be tracked independently.* Nearest-peak per marker let the
triangle's rigid sides vary by 69.5% over one clip. The pose is fitted to the
group.

*A two-marker fit is exact and proves nothing.* A similarity has four degrees of
freedom and two points supply four equations, so the residual is zero whatever
it is looking at — an early version reported `0.00 px` over 85% of a clip while
tracking the wrong pair. Physics gates the fit instead: bounded per-frame change
in scale, rotation and position, plus an **absolute** scale bound, because
per-step limits compound (6% a frame is 5.7x over thirty, and on `bench_85x6`
the fitted plate "changed size" threefold with every step legal).

*Re-acquisition must not chase an extrapolated position.* The tracker followed
the bar cleanly to the floor on `deadlift_150x5`, lost it in the impact carrying
15.6 px/frame of downward velocity, and walked its search box through the floor
and off the frame — 397 attempts looking at blank tarmac while the bar sat
visible where it had landed. It searches around the last *known* position now,
widening with the gap.

*Auto-seeding cannot lean on `truth.find_plate`.* It does not find the plate on
bench — `truth.py` says so — and anchoring to it seeded `bench_110x1` on the
bench frame and floor shadow for 19 s. Seeding is now unaided and uses two
things a single frame cannot see: the end-cap marker sitting at the triangle's
centroid, and **movement** across the clip, because the bar is the thing in a
gym that moves.

**The weak spot, stated plainly.** Absolute scale rests on one constant,
`STICKER_RATIO = 0.858`, measured on the three deadlifts and **transferred** to
bench, which is a different plate with its own stickers. Three rim detectors
were tried and are recorded in the source; one was consistent to 0.005 across
captures and wrong, having locked onto the bumper's inner step. Per-*frame*
scale is measured properly and is worth 0.6-1.4 cm on deadlift.

**What it does not do.** No sync, no `vs_truth`, no `beats_null` — there is no
IMU capture to compare against. It says the referee got better, not the
pipeline. `data/video/` has no markers, so every number the pipeline is
currently scored on is still measured through `truth.py`.

**A correction made while drawing `analysis/37`.** The comparison plot was first
captioned "no height dependence" for the sticker tracker, against the template's
collapse. The scatter falsifies it: pooled over the three deadlifts the sticker
fit residual runs 0.16 px at the floor to 0.81 px at lockout, correlation +0.54,
with per-capture lockout medians of 0.78, 0.71 and **1.60** px — the last above
the 1.5 px gate, which passes only because it tests the whole-clip median. The
marker is smaller and dimmer at the top of frame and the centroid is noisier for
it. The surviving claim is narrower: the stickers degrade **within** tolerance
and never lose the bar, where the template degrades **past** the point `truth.py`
says to stop believing it — 100% of its top-10 cm frames below `GOOD_SCORE`
against 31% at the floor.

*The gate described above is gone as of C17 (2026-08-02); see that entry. Noting
the whole-clip median could not see the defect, and then leaving it as the gate,
was this project's recurring failure written down instead of repaired.*


### C17 — the marker referee is gated where it is used (2026-08-02)

`src/markers.py` (`top_of_travel_residual`, `MAX_TOP_RESIDUAL_CM`, `validate`),
`tests/test_markers.py`. The first half of making `data_v2` the scoring path:
before the marker tracker can referee anything, its own gate has to be able to
see it failing.

**C15 recorded the defect and left it in place.** Its closing correction says the
1.60 px lockout residual on `deadlift_190x1` sits above the 1.5 px gate "which
passes only because it tests the whole-clip median". That is a true sentence
about a broken gate, written down rather than acted on — and the whole reason
`markers.py` exists is that `truth.validate` did exactly this with NCC (C12).
**That is now five times: milestones 1–6, C8's peak-height threshold, C10's
clip-composition artefact, C12's whole-clip NCC median, and this one.**

**Measuring it across all five captures rather than C15's three deadlifts
sharpened it into something worse than a missed threshold:**

| capture | whole-clip | top 15% | ratio | top 15%, cm |
|---|---|---|---|---|
| deadlift_150x5 | 0.519 px | 0.775 | 1.5x | 0.177 |
| deadlift_160x5 | 0.611 | 0.724 | 1.2x | 0.168 |
| **deadlift_190x1** | **0.150** | **1.595** | **10.6x** | **0.333** |
| bench_85x6 | 1.096 | 1.311 | 1.2x | 0.279 |
| bench_110x1 | 1.066 | 1.075 | 1.0x | 0.226 |

**`deadlift_190x1` is the best capture we hold by the old statistic and the worst
by the new one.** It passed at 0.150 px against a 1.5 px limit — a tenfold margin
— while being the single worst fit at the height where the measurement is taken.
An aggregate did not merely hide the failure; it inverted the ranking.

**And the fix is in centimetres, not pixels, which changes the conclusion.**
Converted through each frame's own scale, the worst lockout fit in the set is
**0.333 cm against a 1 cm spec**. So the stratification is real and the tracker
is still comfortably usable at its worst point — C15's claim against the template
survives being measured properly, and it is now the gate rather than a caption.
A referee whose own error approaches the spec cannot judge it, so
`MAX_TOP_RESIDUAL_CM` is half the spec. The residual over-states position error
by about sqrt(3) anyway: three markers determine one centroid.

`truth.TOP_FRAC` is reused rather than redefined, so "at lockout" means the same
span of travel for both trackers and C12's numbers stay comparable with these.

**Three gates, and the third is the one that matters.** A per-capture limit in
cm; a non-regression floor pinned at 25% headroom over the table above; and an
*algebraic* test that builds the blind spot directly — a track that is excellent
everywhere except the top of travel — and asserts the old whole-clip median
passes it while the new statistic fails it. Replacing an aggregate with a
stratified statistic is worth nothing unless the stratified one demonstrably
responds, and that test is the demonstration. It needs no `data_v2`, so it runs
on a fresh clone.

**Part two, the same day: the scoring path takes either referee.**
`metrics.resolve_path` / `infer_tracker` / `_video_quality`,
`metrics.vs_truth(..., tracker=)`, `metrics.momentum_closure(..., tracker=)`,
`pipeline.find_video`, `tests/test_video_truth.py`, `tests/test_pipeline.py`.

The bottleneck this removes: `data_v2` now holds the better referee and nothing
could be scored through it. Every horizontal number in the project ran through a
single hardcoded `truth.bar_path` call inside `_video_on_imu_clock`. Feed it
marker footage and nothing happened.

**It turned out to be a five-line change surrounded by tests, and the reason is
worth recording because it was not luck.** `markers.bar_path` already returned a
superset of `truth.bar_path`'s keys, and `truth.landings`, `truth.sync`,
`truth.to_imu_time` and `bench_sync` read only `t` and `height` — both trackers
zero `height` at the lowest tracked point and report seconds from clip start. So
the entire sync apparatus was tracker-agnostic before anyone tried it. The only
thing that ever needed to know the difference was which tracker to call.
Confirmed rather than assumed: `truth.landings` on the marker `deadlift_150x5`
returns exactly **5 landings**, matching the label, and that is now a gate.

Three ways to choose, in order of precedence: pass a **path dict** already
tracked by either module (so a caller can track once and score several ways
without paying for the decode twice); pass **`tracker=`**; or pass neither and
let it infer from where the clip lives, since anything under `data_v2/` is
marker footage. **The inference is about the directory, not the footage** — the
layout already records the answer, and sniffing frames for markers would be a
second tracker running on every call and a new way to be wrong.

`pipeline.find_video` was the other half and would have been missed: it searched
`parents[2]/data/video` unconditionally, so a `data_v2/raw` capture would have
been paired against `data/video` footage its inferred tracker cannot read, and
the failure would have surfaced as a tracking error rather than a pairing bug.
A capture now stays inside its own dataset.

**The safety argument is a measurement, not a promise.** A plain path outside
`data_v2` still resolves to `truth.bar_path` with its own defaults, so every
pre-existing call is bit-identical — checked against the C10 table: 5.05 / 9.19 /
15.44 / 1.88 / 0.64 cm horizontal and 3.55 / 3.23 / 1.96 / 2.07 / 3.08 null,
all exact, with `video_top_ncc` reproducing C12's 0.371 / 0.395 / 0.440.

`vs_truth` gains `video_tracker`, and `video_top_residual_cm` alongside
`video_top_ncc` — each referee reports the statistic that means something for it
and NaN for the other, rather than one field that silently means two things.

**What this does NOT do.** It says the plumbing works, not that the marker
referee agrees with the template one. Nothing in `data_v2/` has an IMU log, so
no `vs_truth`, no sync and no `beats_null` has ever been computed through
markers. The specific unmeasured thing: whether a landing found on marker
footage falls at the same INSTANT as one found on template footage. The deadlift
sync matches landings to IMU impacts at 13.5 ms, so that is the tolerance the
first paired capture should test — and it is written into the gate's docstring
so it is not left to be rediscovered.

*`analysis/38_marker_referee.png` was claimed and not drawn.* The finding is a
five-row table and it is in three documents already; a plot would have meant
claiming `run.py` and `plot.py` and adding a CLI flag to regenerate it, which is
more surface area than the picture is worth. **38 is free again.**

### C21 — the marker seeder on the first paired captures (2026-08-03)

Six captures arrived on 2026-08-03 with an IMU log and a marker clip side by
side — 2 squat, 4 bench, 24 reps, in `data_v2/raw` and `data_v2/video`. They are
the captures C17 was built for. **`markers.bar_path` does not seed on any of
them**, and C17's "there is nothing to build" is therefore falsified.

**PARTIAL. Three of four blockers are fixed and measured; the fourth is open.**
Do not read this entry as a fix.

*What the failure looked like.* `bench_95x2` reported 0.4 cm of travel against a
29.5 cm rep, the seeder having locked a triple of rack holes. Every quality
number the module reports was healthy — 100% coverage, three markers "matched",
sub-pixel residual — because a rigid triple of gym fixtures fits a rigid model
perfectly. This is the project's recurring shape: an aggregate that passes while
the thing fails.

*Three gates rejected the true constellation, and every one was already at zero
margin on the footage it was tuned against.* Measured on `bench_95x2` frame 450,
where all three stickers are detected cleanly at strengths 0.62/0.54/0.47:

| gate | needs | old footage | 2026-08-03 |
|---|---|---|---|
| `max_dets = 30` | all three stickers in the top 30 detections | ranks 20/23/24 | ranks 0/22/**48** |
| `require_hub`, `0.45·circ` | end cap near the rim centroid | 0.41·circ | **0.55·circ** |
| `top = 5` | the triple to outscore the ceiling grid | rank 3 | rank **9** |

The hub gate was a *model* error rather than a tight constant: the end cap
protrudes toward the camera, so where it projects is parallax — this module's
own header measures that offset swinging −111 to +57 px, r = 0.949 with height —
and a fraction of the plate's apparent size does not track it. What is
physically true is that the cap projects inside the plate disc. Now 0.80.
`top` is now 20 and `static_points` removes the fixtures before triples are
enumerated at all, which is the principle `seed_frame`'s docstring always
stated — "the bar is the thing in a gym that moves" — applied before the
appearance filters rather than after them.

*A second, separate bug that suppression fixed.* With the seed CORRECT on
`bench_95x2`, the backward pass still lost the plate and re-acquired on the
bench-and-floor structure, holding it for frames 0–950 at 1.3 px. Suppression
is applied to re-acquisition **only**: applying it to ordinary association as
well cost `deadlift_190x1` 72% of its frames, because a heavy single leaves the
bar on the floor long enough for its own stickers to read as static. That
asymmetry is measured, and it is in the `track` docstring.

*The finding that matters most, and it redirects the next attempt.* **`track` is
not implicated.** Hand it the correct constellation and it follows `bench_95x2`
through the entire clip: 100% coverage, three markers in 1229 of 1235 frames,
median residual **0.11 px**, worst 1.21 — better than on any capture it was
originally tuned against. Gated by
`test_tracking_is_not_what_fails_on_the_2026_08_03_captures`. So nothing should
be spent on the tracker, on detection thresholds, or on reshooting the footage.

*What is still open, stated precisely.* `seed_frame` picks the wrong hypothesis.
The specific defect found: groups are pooled by circumradius within 15%, so the
true constellation is absorbed into a size bucket alongside spurious ones —
`bench_95x2`'s true 94.2 px sits inside the winning group's 100.9 px — and the
group's representative is then reselected by per-frame appearance score, which
is the discriminator already known not to work. Three candidate replacements
were measured and **rejected**: triangle shape rigidity across a group (SD
0.017–0.027, no separation), centre-trajectory smoothness (no separation), and
a 120-frame trial track (near its own seed even a wrong constellation holds
together). A full-clip trial track is the obvious next thing and was not
finished; note that its merit function must not reward a low residual, since a
two-marker fit is exact and scores 0.00 px.

*No regression.* All five original `data_v2` captures seed identically and track
identically — coverage 1.000, residual p95 1.13–1.85 px. Full marker suite 47
passed. `analysis/39_marker_seeding.png`; 39 is taken, next free is 40.

### C33 — paying down 41 hours of doc debt (2026-08-06)

Docs only, no code, no measurement. `CLAUDE.md`, `TASKS.md` and
`analysis/README.md` were held by **C30b**'s claim from 2026-08-05T06:40Z until
the owner released it on 2026-08-06T23:20Z — 41 hours — during which C31, C31a,
C31b and C32 landed a2494b4, 7bc4bcb, bc66fb1, 18501a3 and 70b2a63. Each of
those commits recorded its own doc debt in its commit message rather than
editing around an active claim, which is what the protocol asks for and is why
nothing was lost. **C30b's uncommitted working-tree edits were preserved and
built on, not reverted.** This entry records what was corrected; the substance
is in the C31/C31a/C32 entries below.

**What this cost, and it is the point worth keeping.** The protocol's stall
behaviour worked exactly as designed at the level of individual agents — four in
a row correctly refused to break a lock that merely looked stale, and each left
a full account in its commit message — and it still produced a `CLAUDE.md` whose
headline finding (P2's "the horizontal channel is EMPTY") had been overturned
for a day, whose rep counts were three sessions out of date, and which described
a pipeline default that had been inverted. **The same-commit docs rule and the
never-break-a-claim rule are in direct tension whenever a claim on the shared
docs outlives its agent**, and the resolution the protocol offers — hand it to
the owner to adjudicate — depends on the owner being in the loop within hours,
not days. Nothing here proposes a change to the protocol; the tension is
recorded so the next agent that hits it recognises it in one read.

Corrected, in `CLAUDE.md`: a step-6 banner at the top of the Pipeline section
(every horizontal and vertical number in all three docs predates step 6 being
on); the tape `d` and its sign convention; the camera geometry, in the
two-referees section; C27's sticker-ratio paragraph, with C32's failed
independent attempt and the `STICKER_PLATE_DIAMETER_M` question; the corpus
line (30 labelled captures, 124 reps, 13 in `data_v2`); P1's cadence rule; P2's
head, with C31's overturning of C30 and the post-`d` tables; the falsification
of C30b's own lever-arm argument, written in place under the argument it kills;
P3's C28 ladder with `lever` pinned; P6's step-6 warning; and the squat
external-check paragraph.

In `TASKS.md`: this entry, C31a, C31/C31b and C32; B2 closed as to availability
and explicitly NOT as to fitting; the C30b entry corrected in place; the C5
to-do's "a rest-pause set would be split" caveat, which came true; and four
capture-protocol items (`d` done, markers done, three holds added, sticker
diameter added). In `analysis/README.md`: a step-6 banner over figures 01–47,
entries for 47 and 48, and a second correction on 46.

**Two defects found while reading and RECORDED rather than fixed**, per the
working-style rule:

- `pipeline.run`'s docstring contains a **duplicated paragraph** — "B2's finding
  is not superseded and should not be re-tried…" appears twice, once before and
  once after the "every number recorded before 2026-08-06" note. A copy/paste
  artefact of 70b2a63. Harmless, three lines to delete.
- `plot.plot_bar_path_with_d` labels its orange series **"step 6 OFF (ships)"**,
  which named the default correctly when it was written and does not now.
  `src/plot.py` was held by another agent's active claim at the time.

**One number in a commit message that the evidence does not support**, recorded
because both the commit and the handoff repeat it: 70b2a63 says `d` fixed the
benches "where C10 had four of them losing". C10's own table has **three**
benches under 1.0 (0.72 / 0.80 / 0.92) and reaches six of ten only by counting
the three deadlifts. The docs now say three.

**One thing corrected outside the three docs**, under a separate short claim:
`correct.py`'s comment block above `WRIST_OFFSET_M` still read "**THIS IS NOT
THE SHIPPING DEFAULT** … `pipeline.run(wrist_offset=)` is still None", and its
module docstring said "the DEFAULT has not moved". Both were true when C31b
wrote them and were inverted about an hour later by 70b2a63. Comment text only.

### C31a — the paused squat's cadence drifts, and no constant could see it (2026-08-06)

Branch `c29-jump-state`, commit `a2494b4`. Two of the four paused squats of
2026-08-06 counted 3 of 4 — `squat_pause_140x4_2` dropped its FIRST rep, `_3`
its LAST. Both are real reps: they sit in `_similar_cluster`'s winning cluster
with their siblings at 0.75–0.97 shape correlation and reconstruct 65.4 and
69.7 cm, in line with the reps either side. `_longest_cadence` then discarded
them.

**Diagnosis.** C5's function and C5's mechanism in the opposite direction: the
tolerance was too TIGHT for a real set, not too loose for a post-set gap. **Not**
C22's chain-versus-cluster failure — the cluster is correct on both captures and
holds all four reps.

A paused squat's cadence lengthens rep by rep as the lifter takes longer to
re-breathe and re-brace:

    squat_pause_140x4_3   gaps 5.43, 5.85, 8.53 s   spread 1.573
    squat_pause_140x4_2   gaps 4.88, 5.53, 7.27 s   spread 1.490
    squat_pause_145x4_1   gaps 6.08, 6.32, 6.53 s   spread 1.074  (counts 4/4)

Measured by the run's global max/min spread, a drifting set is indistinguishable
from a set with a post-set movement tacked on, and **the two constraints are
DISJOINT**: `bench_spoto_90x5_1` is correct only for tol ≤ 1.572,
`squat_pause_140x4_3` only for tol ≥ 1.576. **C5's 1.35–1.55 plateau had closed
to nothing and no re-tune was available.** A count-only gate hides this — at tol
1.573 `bench_spoto_90x5_1` still counts 5, but they are the WRONG 5 (ROM 88.7
and 62.9 cm on a bench press). This repo's recurring shape: the count is right
and the windows are not.

**The fix, and both halves are needed.** `_longest_cadence` admits a run on
LOCAL drift — each gap against its neighbour — instead of the run's global
spread, and breaks length ties on cadence EVENNESS before lateness:

    rule                              admissible tol      width
    global spread + lateness (old)    none - disjoint         -
    global spread + evenness          none - disjoint         -
    local drift   + lateness          [1.4598, 1.4882]     1.93%
    local drift   + evenness (ships)  [1.4598, 1.5306]     4.74%

Evenness is needed because with local admission `bench_spoto_90x5_1` grows a
post-set run of five that ties the true five on length and wins on lateness
alone, despite cadence 44% worse (1.488 against 1.036). Lateness is kept as the
last key, so `bench_92.5x2` — the capture it exists for — is decided exactly as
before, its admissible range unchanged at [1.02, 1.97]. **tol is 1.50**, the
round value nearest the midpoint 1.495.

**Gate.** All 30 labelled captures in `data/raw/` and `data_v2/raw/` count
correctly, and across all 34 CSVs every window that was already correct is
BIT-IDENTICAL — only the two short-counting squats move. The plateau's edges are
two different captures on two different lifts. **Read the margin honestly: 2.4%
either side, against the 8–11% the old constant enjoyed before these captures
existed.** A capture that pauses harder will push the floor into the ceiling.

`tests/test_segmentation.py` gained `ALL_CAPTURES` so the plateau gate finally
sees `data_v2/` — being blind to it is how the plateau closed unnoticed — plus
`test_the_old_global_spread_rule_has_no_admissible_tolerance`, which asserts the
emptiness result so nobody re-tunes their way back in.

*Not fixed, recorded:* the other tests in `test_segmentation.py` still only
cover `data/raw/`. And a discriminator that is not a gap ratio at all is
available and unexplored — both paused squats have a rejected low-velocity lobe
INSIDE the long gap (43.20 s and 44.61 s) where `bench_spoto_90x5_1`'s post-set
gaps have none, which would separate the two cases without any tolerance.

*Evidence:* `analysis/47`, `python run.py --pausedsquat`,
`tests/test_segmentation.py` 22 passed. The full suite did not complete — it
aborted at 425 of 539 outcomes on `OSError: [Errno 28] No space left on device`
with the volume at 99%, and the reported "1 failed" IS that crash, with no
`FAILED tests/...` line anywhere in the output. 408 passed, zero real failures.

### C31 / C31b — `d` is measured, step 6 goes ON, and the C28 ladder survives it (2026-08-06)

Branch `c29-jump-state`, commits `7bc4bcb`, `bc66fb1`, `70b2a63`. C31b was a
subagent killed mid-flight by the owner's session limit; C31 released its board
claims explicitly, with the reason recorded, because a terminated agent can
never release its own lock — and a silently broken lock is what the protocol
exists to prevent. Running state for a cold reader:
`analysis/C31b_STATE.md`.

**THE FACT.** The owner tape-measured step 6's wrist-to-bar offset on
2026-08-06. It is `correct.WRIST_OFFSET_M`:

    squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4 cm
    bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5 cm

`apply_offset` computes `p_bar = p_watch − R(t)·d`, so its `d` points BAR→WATCH
and is the negative of what a tape reads from the watch. The constant's
docstring derives it, because **a sign error here is invisible** — it produces a
plausible curve of the right size pointing the wrong way.

**Corroborated, not fitted.** Sweeping `d`'s direction over a 300-point sphere
grid (neighbours ~12°) at the measured magnitude and scoring by C30's
acceleration correlation:

    capture              lit    best    gain   angle(lit, best)
    deadlift_160x6_1    0.641  0.664   0.023        16.3 deg
    deadlift_160x6_2    0.579  0.594   0.015        16.3
    deadlift_185x3      0.432  0.465   0.033        16.3
    bench_92.5x4_1      0.888  0.911   0.022        50.6
    bench_92.5x4_2      0.917  0.939   0.022        52.9
    bench_92.5x4_3      0.814  0.875   0.061        60.3
    bench_95x2          0.935  0.960   0.025        50.6
    bench_spoto_95x5_1  0.910  0.934   0.025        60.3
    bench_spoto_95x5_2  0.937  0.960   0.023        64.3

On deadlift the tape sits at the optimum **within one grid cell, identically on
all three captures**, while `d` carries the correlation from 0.12 to 0.64. On
bench the optimum is 50–64° away and worth 0.02–0.06 on a baseline already at
0.81–0.94 — the objective is flat, so **bench does not identify `d`'s direction
at all**. The tape is corroborated on deadlift and merely not contradicted on
bench. Anyone tempted to refine `d` by fitting it on bench should read B2 first.

**C30's HEADLINE IS OVERTURNED.**

    lift        best-dir horizontal corr, d OFF -> d ON
    deadlift        0.118-0.232  ->  0.432-0.641
    bench           0.798-0.919  ->  0.814-0.937   (6 of 6 improve)
    vertical        0.967-0.994, unmoved either way (the control)

The deadlift horizontal channel was never empty; it was masked by the
uncorrected wrist lever — the term C30 itself named as prime suspect while
lacking `d`, and the term C30b argued the next day could not be the
discriminator. **C30's measurement code was never committed** (`ceba50a` holds
only docs and the PNG), so C31 reimplemented it from the method in that commit
message; it reproduces C30's own baseline to within 0.03. *Commit the code that
makes a headline.*

**AND IT DOES NOT CASH OUT IN POSITION**, which is the finding rather than a
footnote — `metrics.vs_truth`, step 6 off → on:

    capture              h_rms        beats_null    v_rms
    deadlift_160x6_1     7.22->6.65   0.23->0.25    4.57->4.57
    deadlift_160x6_2     4.55->4.39   0.34->0.35    4.51->4.62
    deadlift_185x3      11.44->10.61  0.14->0.15    2.79->2.78
    bench_92.5x4_1       3.08->1.23   0.71->1.78    3.25->2.46
    bench_92.5x4_2       1.12->1.18   2.44->2.32    3.44->2.62
    bench_92.5x4_3       1.39->1.92   1.65->1.19    3.52->2.69
    bench_95x2           1.46->0.80   2.96->5.39    2.90->2.11
    bench_spoto_95x5_1   1.17->3.54   2.65->0.88    3.72->2.91   (new capture)
    bench_spoto_95x5_2   2.76->4.45   1.16->0.72    3.83->3.02   (new capture)

Correlation is shape agreement and blind to gain; rms after double integration
is not.

**STEP 6 IS ON BY DEFAULT, and the reason is not the metric (owner's call).**
`pipeline.run(wrist_offset=)` defaults to `"auto"`. This project reconstructs
the BAR path and the sensor is on the WRIST; `R(t)·d` is the only term between
them, so omitting a measured geometric term does not make the answer more
conservative, it makes it an answer to a different question. *C31b had left the
default deliberately OFF on the metric alone, and the owner overruled it on the
geometry — the disagreement is recorded because the reasoning is the interesting
part, not the outcome.*

*What it bought:* three captures crossed `beats_null = 1.0`, and **all seven
template-refereed benches now beat a flat vertical line**, where C10's table had
three of the seven losing — the 2026-07-30 paused benches at 0.72 / 0.80 / 0.92,
exactly the three that crossed. *(70b2a63's commit message says "four of them";
C10's table shows three benches under 1.0 and six of ten only with the deadlifts
counted in.)* The three deadlifts still lose and stay `xfail`.

*What it cost, recorded rather than absorbed:* `bench_90x4_2` and `_3`, the only
two captures where the horizontal reconstruction had ever demonstrably carried
information, fall **4.80 → 3.45** and **4.03 → 2.25** against the null. Both
still beat it comfortably. Those two were re-recorded in `tests/test_real_data.py`
with the old values kept beside them; every other capture stayed inside the
existing 20% headroom. `test_step_six_runs_and_is_off_by_default` is INVERTED,
not deleted, and its docstring says why it was right before and what changed.

**THE C28 LADDER WITH `lever` PINNED AT THE TAPE.** Decision rule fixed in
writing before any number was read. Three `data_v2` deadlifts:

    rung                     arm     nfree  ceiling               LOO (held-out)
    baseline                 free      0    7.22 [7.22 4.55 11.44]  7.22
    baseline                 PINNED    0    6.65 [6.65 4.39 10.61]  6.65
    bias                     free      3    2.06                    6.50 [6.50 2.47  6.53]
    bias                     PINNED    3    2.14                    5.72 [5.72 2.78 15.14]
    bias+tilt                free      6    2.02                    6.61 [6.61 2.47 24.85]
    bias+tilt                PINNED    6    1.62                    5.60 [5.60 2.88  5.86]
    bias+tilt+scale          free      9    1.80                    6.36 [6.36 2.54 25.22]
    bias+tilt+scale          PINNED    9    1.42                    5.71 [5.71 2.55 15.00]
    bias+tilt+scale+lever    free     12    1.29                    6.59 [6.59 2.67 14.20]
    bias+tilt+scale+lever    PINNED    9    1.42                    5.71 [5.71 2.55 15.00]
    ...+gravref              free     15    1.92                    4.25 [4.25 2.76  6.69]
    ...+gravref              PINNED   12    2.16                    4.34 [4.34 2.90 11.45]

RULE 1 (ceiling) — pinning removes 3 dof so the ceiling could only worsen, and
on two rungs it IMPROVED anyway (2.02 → 1.62, 1.80 → 1.42). On the rung
containing `lever`, pinning cost 0.13 cm of ceiling and saved 3 parameters.

RULE 2 (transfer, the actual test) — **PASSES: pinned beats free on 4 of the 5
fitted rungs.** So the three `lever` degrees of freedom WERE absorbing something
real, and C28's ladder was handicapped by not knowing `d`.

**But the family is still dead, and that is the finding.** Best LOO anywhere is
4.25 cm against a `d`-only baseline of 6.65 with nothing fitted and a flat-line
null of ~1.6. Held-out `deadlift_185x3` is destroyed by most rungs (11–25 cm).
**C28's conclusion survives `d` being known: the error is not a constant in any
frame, and knowing the lever arm makes the failure less bad rather than fixing
it.**

RULE 3 (corroboration) — **fails, and re-confirms B2 instead.** Fitting `lever`
on top of the tape gives residuals of 47.9 / 17.7 / 2.4 cm, totals
44.0 / 17.8 / 11.8 cm at 108 / 74 / 4 degrees from the tape. Only one capture
stays near it. The corroboration that DOES hold is the acceleration-domain
direction sweep above: **the position-domain objective cannot identify `d`, the
acceleration-domain one can**, which is C30's point restated — double
integration and the detrend destroy the conditioning.

**THE CAMERA GEOMETRY (owner, 2026-08-06), which nothing in this repo had
recorded.** Squat and bench are filmed from the lifter's RIGHT, deadlift from
the LEFT, and the watch is on the LEFT wrist. It cannot touch `d`, which lives
in the watch body frame, and it cannot corrupt the fore-aft sign, because
`vs_truth` picks one sign per set from the correlation. What it DOES do is put a
confound in every bench and squat number: **the referee tracks the plate on the
opposite end of the bar from the sensor**, so bar tilt or an uneven press is
scored as pipeline error. Deadlift is the only lift where camera and watch are
on the same side. Untested and testable: a tilting bar should give a
bench-only, load-dependent residual that no wrist-frame correction can reach.

**AN UNRESOLVED TENSION, recorded not smoothed.** C32 nominated the PAUSE as the
explanation for the bench dissent. Switching step 6 on falsified the simple
version: all three paused benches beat the null under the TEMPLATE referee while
`d` still hurts the paused benches under the MARKER referee. **The surviving
split is by REFEREE, not by pause**, and neither referee has been shown right —
C24 already had them disagreeing ~20% on ROM. Highest-value open question now.

*Also established:* the six new captures of 2026-08-06 run clean through the IMU
pipeline with per-rep ROM inside `VERTICAL_ROM_M`; counting is 30 of 30 labelled
captures and 124 of 124 reps; and **the 8-sticker squat plate TRACKS** at 100%
coverage and 0.883 px median residual, the first squat footage in the project
that does — which makes `metrics.vs_truth`'s hardcoded squat refusal stale for
`data_v2`, since its stated reason describes the old template footage. An
exploratory bypass through `bench_sync` gave `squat_pause_140x4_2` h 2.57 → 2.00
(bn 1.31 → 1.68) and `squat_pause_145x4_1` h 3.90 → 2.95 (bn 0.88 → 1.16) with
`d`, while the guards correctly REFUSED the other two. **Indicative only** —
`bench_sync` is unvalidated on squat and video ROM reads 57.5–58.1 cm against
the IMU's 66.1–69.1.

*Evidence:* `analysis/48_bar_path_with_d.png`, `python run.py --dpaths`,
`analysis/C31b_STATE.md`, `src/oracle.py`. Full suite at 70b2a63: 523 passed /
1 skipped / 8 xfailed / 7 xpassed; xfail moved 11 → 8 and xpass 4 → 7 because of
the three captures that crossed the null.

**NOT DONE, in priority order.** (a) C29's rest-window jump correction WITH `d`
— do the two compose, or correct the same thing twice? C29's 10.66 → 3.93 was
measured with step 6 off. (b) Explain the referee split above. (c) Lift the
squat refusal in `vs_truth` properly.

### C32 — `bench_spoto_95x5_1`'s 0.68 warning is the rim DETECTOR (2026-08-06)

Branch `c29-jump-state`, commit `18501a3`. `markers.validate` warned that this
capture puts the sticker circle at 0.68 of the plate radius against the 0.858
`STICKER_RATIO` scales by — a 26% discrepancy on the one capture where step 6's
measured `d` also made the horizontal much worse (h_rms 1.17 → 3.54,
`beats_null` 2.65 → 0.88). **VERDICT: the capture IS fit to referee.** Comments
and one warning string only; no measurement, no constant and no behaviour
changed.

**1. The track is sound, checked where it is used rather than on average.** 100%
coverage, all 7 model slots matched in every frame, median fit residual 0.260 px
(0.055 cm). By height: **0.158 px over the top 15% of travel** against a 0.5 cm
gate, and 0.820 px (0.172 cm) in the bottom decile — which on a paused bench is
the pause itself, and is the second best of the six `data_v2` benches, better
than `bench_95x2`'s 0.198 cm, an accepted referee. Drawn back over the frame at
the start, the chest pause, lockout and the end, the constellation sits on the
real stickers throughout.

Sync and phase are clean: exactly one video chest touch in each of the five IMU
rep windows, at 0.543–0.651 through them — inside C9's 0.567–0.648 and C25's
0.53–0.69, and indistinguishable from the four 2026-08-03 benches (0.541–0.688).
`bench_sync` does carry whole-period rivals at 0.71–0.77 of the peak on both
paused benches where the four 2026-08-03 benches have none, **so a paused set is
more periodic-ambiguous**; the touch-per-window count is an anchor outside the
periodicity and it confirms the chosen alignment.

**2. The warning is measuring `truth.find_plate`.** Drawn over the seed frame,
the detected rim circle misses the plate on **all six `data_v2` bench captures**
— displaced 32–94 px and oversized — which is the dark-disc-on-a-dark-background
growth `STICKER_RATIO`'s own comment already records. `bench_spoto_95x5_2`,
filmed minutes later on the same plate, reports 0.692 against `_1`'s 0.681, so
nothing singles `_1` out. On deadlift the same detector sits on the rim, which
is why the check is worth keeping there.

**3. The absolute scale is still open, and closing it without a tape FAILED
instructively.** Re-measuring the rim with no matched filter (per-ray intensity
edge outward from the tracked centre, median over 720 rays and 25 frames) gives
0.936–0.947 on the five eight-sticker captures against 0.907–0.926 on the old
three-sticker ones. It looked like a 9% error in `STICKER_RATIO` until it was
run on the constant's own source footage: **this is the radial-gradient search
`markers.py` already tried and rejected**, whose recorded failure is
0.928/0.938/0.929 on those clips with the overlay showing it on the bumper's
inner step, and today it returns 0.919/0.922/0.926 there. It reproduces its own
rejection, so it carries a positive bias of unknown size and cannot set a scale.
What survives is the DIFFERENCE between plates — the eight-sticker circle sits
perhaps 1.5–3% closer to the rim than the old one, C27's direction but nowhere
near enough to confirm C27's size. **Nothing re-tuned:** `STICKER_RATIO` and
`truth.sticker_plate_diameter` cancel one another on the older captures, so
moving one alone silently rescales all of them. The answer remains a tape into
`bar_path(sticker_diameter_m=)`.

Two negative controls recorded with it, because both look like confirmation and
are not. Scaling the referee up improves `pipeline_v_rms` on every bench capture
*including the three-sticker ones*, so that is the known IMU-vs-video vertical
disagreement (C24). And the 2026-08-03 benches are light blue calibrated discs,
so a dark-plate edge test barely applies to them. Also verified: `bar_path`
still reproduces `STICKER_RATIO`'s calibration on its own source footage after
four rewrites of the seeder — 0.861/0.877/0.898 today against the recorded
0.862/0.878/0.834.

**4. The scale does NOT explain the `d` dissent.** Sweeping the referee's
absolute scale from ratio 0.681 to 1.000 — a 47% span, far wider than any
plausible error — `bench_spoto_95x5_1` is worse with `d` on at every point (0.81
vs 3.05 at 0.681; 1.67 vs 3.94 at 1.000) and `beats_null` with `d` on never
exceeds 0.92. `bench_spoto_95x5_2` likewise. `bench_95x2` and `bench_92.5x4_1`
are better with `d` on at every point in the same sweep. **The split is
scale-invariant, so it is not the ruler.**

*Recorded, not fixed:* `truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06 entry,
so bench falls through to 0.425 m and squat to 0.450 m by accident rather than
by decision. **If one stickered 425 mm plate was moved between the two bars,
squat is 5.9% out.** One question to the owner; noted in `truth.py`.

*Evidence:* `test_markers` + `test_video_truth` + `test_heartbeat`: 156 passed.
`analysis/50` was claimed and NOT used — `src/plot.py` and `run.py` were held by
C31 throughout — so 50 is free.

### C30b — C30 overgeneralised: the horizontal works on BENCH (2026-08-05)

Branch `c29-jump-state`. **The owner rejected C30's conclusion — "I don't think
the horizontal channel is empty, the deadlift movement is just much more
vertical than bench or squat" — and was right.** C30 measured three captures of
one lift and stated the result as a property of the axis. Run on bench, the same
test, same filter, same code path:

    lift        HORIZONTAL r      best over all dirs   VERTICAL r
    bench        +0.68 .. -0.91       0.79 - 0.94        0.99
    deadlift     -0.08 .. -0.16       0.10 - 0.23        0.97-0.99

**The horizontal channel is not empty.** Per capture, best direction: 0.82, 0.89,
0.79, 0.89 on the four marker-refereed benches and 0.10, 0.92, 0.90, 0.37, 0.94,
0.92, 0.93 on the seven template ones. Both referees agree, so it is not a
tracker artefact. Nor is it the sync: deadlift's is the BETTER one, landmark-
matched at 9-19 ms against bench's cross-correlation, and it correlates worse.

*(`bench_90x4_1` is the one outlier at 0.10, and its vertical control is also
degraded at 0.751 against 0.99 elsewhere, with a_h sd 0.525 against 0.08-0.15.
Something is wrong with that capture specifically; 1 of 11.)*

## The mechanism C30 proposed is also wrong

> **FALSIFIED THE NEXT DAY (C31, 2026-08-06). This section is wrong and C30 was
> right about the lever arm.** The owner tape-measured `d`; applying it took the
> deadlift horizontal correlation from 0.118–0.232 to 0.432–0.641 while moving
> bench only 0.798–0.919 → 0.814–0.937. **The lever WAS the dominant contaminant
> on deadlift.** The specific sentence "it should no longer be sold as the fix
> for P2" was the worst call in this entry — `d` is the single largest
> improvement anyone has made to the deadlift horizontal channel, and if the
> owner had taken this advice the measurement would not have been made.
>
> **Where the argument went wrong, which is the reusable part.** It computed the
> lever's ABSOLUTE contamination — swing angle × |d|, 3.6 vs 4.5 cm — and
> inferred equal DAMAGE from equal size. Damage is contamination measured
> against what survives it, and the two lifts differ there: bench's correlation
> was already 0.80–0.92 with the lever uncorrected, deadlift's 0.12–0.23. A
> symmetry argument over a term's magnitude does not transfer to a ratio.
> *(Why the same absolute term is near-fatal on one lift and not the other is
> still not explained.)* Note also the `|d| = 12 cm` assumed in the table below
> is 9.5 cm on both lifts by the tape, so the sweeps are ~20% overstated.
>
> The FLOOR IMPACT section that follows is NOT falsified by this — it stands on
> its own evidence from C11, B6, P6, C28b and C29 — but it no longer inherits
> this section's argument, and with `d` applied the residual deadlift deficit it
> has to explain is 0.43–0.64 against bench's 0.81–0.94, not 0.12 against 0.92.

C30 blamed the wrist lever arm `R(t).d` — the watch is on a wrist that rotates
about a bar constrained to move vertically. Measured, per rep:

    lift        wrist swing    |d|=12cm sweeps    peak gyro      peak |a|
    bench          17.3 deg        3.6 cm        229-428 deg/s   2.1-6.4 g
    deadlift       21.8 deg        4.5 cm        595-1034        15.3-21.8 g

**The wrist swing is nearly the same.** If the lever were the dominant
contaminant, bench would be almost as broken, and bench is fine. So the lever
arm is not the discriminator, and C30's "d is the highest-value measurement"
follows from a hypothesis that this weakens. Measuring `d` is still worth doing
— it is a real unmodelled term and step 6 is implemented and waiting — but it
should no longer be sold as the fix for P2.

**What separates the lifts is the FLOOR IMPACT: 15-22 g against 2-6 g, and 2-3x
the peak gyro.** That is the one thing a deadlift has and a bench does not. It
is also exactly where C11 localised the vertical momentum deficit (-0.589 m/s
across a landing against -0.010 through a pull), where B6 found several hundred
ms of strap ringing, and what P6 has called the trustworthy-but-unused anchor.
**Nobody had connected it to the horizontal channel.**

## What survives from C30, and it is not nothing

- On DEADLIFT the fore-aft acceleration is uncorrelated with the bar's, even
  optimising the projection direction post hoc over all 90. That measurement
  stands; only its generalisation was wrong.
- Step 7 removes a linear function of t, whose second derivative is zero, so the
  acceleration error is identical before and after the detrend. Every correction
  B7, B6, C19, C28b and C29 tried was downstream of the problem.
- The flat-line null wins on deadlift because predicting the mean is optimal
  when you have no information, so `beats_null < 1` is a signature rather than a
  score. Bench's two captures that beat it 4x were the clue, and C30 noted them
  without weighing them.
- The method itself is validated by the vertical control at r = 0.97-0.99 on
  both lifts.

## What this reorders

P2 is a **deadlift** problem, not a horizontal-axis problem. The bar's fore-aft
acceleration on bench (0.079-0.147 m/s^2) is SMALLER than on deadlift
(0.13-0.21) and tracks far better, so "not enough signal" is not the
explanation either — the owner's phrasing pointed at the right lift for a
reason that turned out to be the impact rather than the geometry.

*Evidence:* `analysis/46_accel_error_shape.png` (deadlift), this entry (bench).

### C30 — the DEADLIFT horizontal channel is empty (2026-08-05, overgeneralised; see C30b)

Branch `c29-jump-state`. The owner asked why the reconstruction still invents
fore-aft travel after C29. The answer turned out not to be a magnitude problem
at all. **Nobody had ever measured the acceleration error as a TIME SERIES** —
every statement about P3 came from its integral or from a summary statistic.

*Method, and it is feasible because C27 made it so.* Differentiate the marker
path twice (Savitzky-Golay, 0.70 s window, order 3) to get the bar's true
acceleration, and put the reconstruction's position through the IDENTICAL
filter so both sides have the same bandwidth. Noise floor, measured where the
bar is provably still: **0.00125 g**, about 15x below the signal. That only
works because the conic tracker holds 0.28 px residual at 100% coverage.

*Note the detrend cannot affect this at all.* Step 7 removes a linear function
of t from position, whose second derivative is zero. **The acceleration error is
identical before and after step 7**, which is worth stating plainly: no detrend,
of any order or on any boundaries, can change what follows.

## The measurement

    capture            corr(recon, video) HORIZONTAL   ... best over ALL directions   VERTICAL
    deadlift_160x6_1              -0.077                        -0.103 (at 152 deg)     0.990
    deadlift_160x6_2              -0.156                        -0.233 (at 146 deg)     0.975
    deadlift_185x3                -0.102                        -0.115 (at 168 deg)     0.971

**The vertical is the positive control** — same footage, same clip, same filter,
same differentiation, same code path — and it reproduces the video at r = 0.97
to 0.99. The horizontal, optimised post-hoc over all 90 projection directions so
that B4's unresolved axis cannot be blamed, reaches -0.10 to -0.23.

**So the reconstruction's fore-aft acceleration is uncorrelated with the bar's.**
Its magnitude is comparable or larger — sd 0.26/0.30/0.10 against the video's
0.21/0.19/0.13 — so the pipeline draws fore-aft motion of roughly the right
size that bears no relation to what the bar did.

*And P3's stated mechanism is not it.* Regressing the error on `u(t) = R(t)^T
axis` — the exact linear model "a body-frame bias projected through a rotating
forearm" implies, with a known time-varying regressor — explains only **17-23%**
of the variance and needs |b| = 0.42-1.25 g against P4's table measurement of
0.0025 g. That is 170-500x too big: the fit is absorbing, not explaining.

## Why horizontal and not vertical

    quantity                                    sd, m/s^2
    the bar's true HORIZONTAL acceleration      0.13 - 0.21
    the bar's true VERTICAL acceleration        0.86 - 1.27      (6-7x bigger)
    noise floor of this measurement             0.012
    wrist lever R(t).d for |d| = 12 cm          ~1.9 - 3.3       (order of magnitude)

**The bar's fore-aft acceleration is the smallest real thing in the system.** It
is 6-7x smaller than its own vertical, so any wrist-versus-bar error term is
6-7x more damaging to the horizontal — and THAT ratio is the robust part of this,
because it needs nothing to be known about `d`.

The wrist lever arm is the obvious candidate for the term itself: the bar is
constrained to move nearly vertically while the forearm ROTATES about it, so the
watch's fore-aft motion is the bar's plus `R(t).d`, and step 6 — which exists
and would remove it — is OFF because `d` has never been measured.

**Treat the ~2.5 m/s^2 as an order of magnitude and no more.** It is a median
over random directions of `d`, and the vertical's r = 0.976 bounds the TRUE
lever term well below it, since a term that large would corrupt the vertical
too. What survives is that a plausible `d` puts this term at or above the
horizontal signal while remaining a modest fraction of the vertical.

## What this reframes

P2 reads "horizontal is 5-15x outside spec", which sounds quantitative — a
signal that needs cleaning up. **It is qualitative: there is no horizontal
signal to clean.** That explains, at a stroke:

- why `beats_null` is below 1 everywhere (a flat line beats uncorrelated motion
  of the right magnitude, necessarily);
- why five corrections in a row failed (B7, B6, C19, C28b, C29 were all
  rearranging noise);
- why C28's oracle capped at the null across every constant error model (there
  was nothing to recover);
- why C29 improved `h_rms` 44% without touching excursion (it improved the
  low-frequency ALIGNMENT without adding any signal).

**The implication for the project is that `d` is not worth "1-2 cm" as B2
estimated.** B2 measured its effect on POSITION after the detrend. In
ACCELERATION, before anything, it is plausibly the dominant term on the one axis
the spec is about. A tape measure from watch centre to bar centre, in watch
axes, is now the highest-value measurement available — ahead of the sticker
circle.

*Evidence:* `analysis/46_accel_error_shape.png`. 46 is taken, next free is 47.

### C29 — the jump state, and fixing the structure that annihilated it (2026-08-05)

Branch `c29-jump-state`, cut from `c28-imu-video-oracle` (d329a2a) rather than
from main, because it builds on `src/oracle.py`. **The owner needs to know that
before landing either.** Two halves: the jump fails on the shipping detrend for
a structural reason, and moving the detrend's boundaries fixes it.

## Part 2, the fix — and BOTH changes are needed

Correcting at the impact only works if the detrend's boundaries are somewhere
else. `oracle.jump_rest_windows` keeps step 7's machinery exactly — independent
endpoint lines, start-aligned, `correct.detrend_set` — and moves the windows to
rest-to-rest. Measured on all six deadlifts, all three axes corrected:

    arm                                h rms   beats_null   v rms
    SHIPPING (impact windows)           8.21      0.29       4.90
    rest windows, NO correction          10.66      0.21      11.92   <- CONTROL
    rest windows + 0.20 s                3.93      0.69       3.22
    rest windows + 0.30 s                4.10      0.70       3.30

**Read the control row first: moving the windows ALONE is worse than shipping.**
And C29's part 1 shows the correction alone is annihilated. Neither change helps
by itself; together they take the frame-internal horizontal from 10.66 to 3.93
and the vertical from 11.92 to 3.22. All six captures improve, and
`deadlift_155x6_1` and `deadlift_180x3` cross **beats_null = 1.0** for the first
time in this project (1.19 and 1.03).

*The window width is not a fudge factor.* The optimum is a broad plateau from
**0.10 to 0.50 s**, and B6 independently measured the strap ringing at "several
hundred milliseconds" without reference to any of this. A single-sample jump
(0.00) is WORSE than the control at 13.83 — the error accumulates over the
ringing, it does not arrive as a delta.

*The failed first attempt is the informative one.* `detrend_knots` applied one
CONTINUOUS piecewise-linear drift with knots at the rest instants and cost
8.21 -> 17.00 with ROM at 70-138 cm. The shipping detrend fits INDEPENDENT lines
— two free parameters per rep with no continuity — and a continuous drift has
about one per knot. **So what makes step 7 load-bearing is not the closure, it
is the per-rep INDEPENDENCE**, which nobody had named. `rest_windows` keeps that
and moves only where the boundaries fall.

## Evaluated properly, and one number qualifies the rest

*The rep-subset worry is real but small.* Dropping the first and last rep from
SHIPPING too — the ones the rest frame cannot see — moves it 8.21 -> 7.05, not
to 3.93. So the like-for-like gain is roughly **7.05 -> 3.93, 44%**, and the
frame-internal control-vs-treatment is **10.66 -> 3.93, 63%**.

*The whole distribution moves, not the median.* Per rep, shipping's interior
reps against the treatment: median 6.02 -> 3.98, p25 4.18 -> 3.05, p75
8.11 -> 5.96, worst 15.44 -> 13.13. **And zero reps in either are under 1 cm.**
Nothing here is in spec; the spec is not in sight.

**THE QUALIFICATION: it improves TRACKING, not invented travel.** P2's actual
complaint is that the reconstruction draws fore-aft motion the bar never made.
Per-rep fore-aft excursion, median in cm:

    video   7.2      shipping  12.4  (1.7x)      fixed  14.4  (2.0x)

On the three marker-refereed captures alone, where the referee can be trusted at
lockout, it is video 5.4, shipping 14.4, fixed 13.8. **So the fix makes the path
follow the video's shape and timing much better point-for-point while still
sweeping roughly 2.5x the fore-aft range the bar actually moved through.**
`h_rms` improves on 6 of 6 captures; excursion improves on only 3 of 6. Anyone
quoting the 44% must quote this next to it.

## What this is NOT

**The frame scores 19 of 30 reps against 30/30.** `rest_instants` needs an
impact either side and rejects the final one of each set, where the lifter
releases the bar, so the first and last rep of every set drop out. The
shipping-vs-treatment comparison is therefore NOT like-for-like on two counts,
different windows and a different rep subset. **The control is, exactly** — same
windows, same 19 reps, same everything but the correction — so 10.66 -> 3.93 is
the number to quote and 8.21 -> 3.93 is not.

Still deadlift-only and always will be: no rest anchor on bench or squat. Six
captures. And `beats_null` at 0.70 median is still below 1.0, so the median
capture remains worse than a flat line — this is a large step, not an arrival.

### C29 part 1 — the jump state at the impact: annihilated by construction (2026-08-05)

Branch `c29-jump-state`, cut from `c28-imu-video-oracle` (d329a2a) rather than
from main, because it builds on `src/oracle.py`. **The owner needs to know that
before landing either.**

C28b ended by pointing at a jump state: the impact predicts horizontal error at
r = 0.772, every correction tried spreads that information smoothly across the
rep, and B6 measured the error to be localised at the landing. C29 built it.
**It does not work, and the reason is structural rather than empirical.**

*One experiment, not two.* `oracle.jump_correction` removes the same observable
`dv` over a WINDOW of `width_s` starting at the impact; `width_s=None` uses the
whole rest-to-rest interval and reproduces `impact_correction` exactly (pinned
by a test). Sweeping the width therefore interpolates between C28b's failure
and a pure jump, and the curve is the result.

    width_s    160x6_1  160x6_2   185x3  155x6_1  155x6_2   180x3   median
    SHIPPING      7.22     4.55   11.44     5.05     9.19   15.44     8.21
    0.02          7.20     4.57   11.45     5.07     9.11   15.43     8.16
    0.10          7.12     4.67   11.53     5.21     8.82   15.55     7.97
    0.30          6.97     5.04   11.69     4.77     8.12   15.77     7.55
    1.00          7.66     4.76    8.28     6.11     5.56   11.32     6.88
    FULL(=C28b)   7.94     7.39   11.58    10.00     7.98   10.57     8.99
    NULL          1.68     1.54    1.59     3.55     3.23    1.96

## The pure jump does nothing, and it was PREDICTED to

At 0.02 s the numbers are shipping's to within a few hundredths. That is not a
tuning failure — it is exact, and the reason is a structural incompatibility
between the two things this project has been trying to combine:

**`segment.rep_bounds` ends every rep AT a floor impact.** So a velocity error
that steps at the impact is constant within each rep, its position error is
linear in t within each rep, and `correct.detrend_rep` removes a line. **The
correction lands exactly in the detrend's null space.** Gated as algebra in
`test_a_velocity_step_at_a_rep_BOUNDARY_is_annihilated_by_the_detrend`.

So: "use the impact, the one externally true instant" and "close each rep with
a line whose boundaries are the impacts" are not merely hard to combine. Any
correction localised at the boundary is INVISIBLE to what follows it. That is
the sharpest statement of the bind B7, B6, C19 and C28b were all pushing
against, and it is new.

## The wider window looks like a win and is regression to the mean

At width ~1.0 s the median improves 8.21 -> 6.88 cm, 16%, and the window turns
out not to be a tuned parameter at all: it clips at 0.72-1.00 s, which IS the
[impact -> rest instant] span, exactly B6's ringing window. Three captures
improve by 27-40% and three degrade by 5-21%.

**But the three that improve are the three worst, which is what regression to
the mean looks like.** Measured per rep, n = 20:

    median h_rms                         6.15 -> 6.62 cm   (WORSE)
    improved on                          10/20 reps        (a coin flip)
    corr(improvement, |dv_h|)            +0.523
    corr(improvement, baseline error)    +0.551
    PARTIAL(improvement, |dv_h| | base)  +0.184            <- does not survive
    PARTIAL(improvement, base | |dv_h|)  +0.272            <- does

**The screening structure is the exact INVERSE of C28b's.** There the observable
screened off the confound (0.472 vs 0.184) and that is why C28b's correlation
was believable. Here the baseline screens off the observable. The per-capture
16% is not physics.

*What is safe about it, at least.* Horizontal-only, so per-rep vertical ROM is
untouched — 56-57 -> 56-57 cm — where B6's splice pushed it to 82.6 against a
61 cm ceiling. That is the one design lesson worth carrying: B6's splice was
vertical and "could not move a metric that reads columns 0 and 1", so the
horizontal jump had genuinely never been tried before this.

## Five for five

    B7    anchored position at the impacts            lost
    B6    spliced velocity across them (vertical)     lost
    C19   raised the detrend to a quadratic           lost
    C28b  constant accel per rest-to-rest interval    lost
    C29   a jump state AT the impact                  annihilated

**And C29 says the next one will too, unless it moves the detrend.** The
correction and the detrend's null space coincide at the impact. B7's ablation
already showed the detrend cannot simply be dropped — error goes to 3-5 m — so
the remaining move is a detrend whose BOUNDARIES do not sit on the impacts, or
a constraint that replaces closure entirely. Nothing here has tried that.

*Evidence:* `analysis/44_jump_state.png`, `oracle.jump_correction`,
`tests/test_oracle.py` (14 passed). 44 is taken, next free is 45.

### C28b — the impact IS informative about horizontal, and every use of it misspends it (2026-08-05)

Branch `c28-imu-video-oracle`. The owner asked whether a Kalman filter could
help once the reducible error is reduced. A filter is an information FUSER, not
a noise reducer — with no measurements it is dead reckoning with a covariance
attached — so the question is what measurements exist. This entry measures that
rather than answering it by architecture.

*What the impacts actually supply.* At a rest instant the bar's true velocity is
~zero, so **the reconstruction's velocity there IS its velocity error**, and it
is readable without the video. `segment.rest_instants` places those instants
from raw acceleration and gyro alone, so it inherits none of the drift it
measures. That is the entire information content the impacts add: one sample of
the velocity error per rep. **Deadlift only** — bench and squat have no
raw-signal rest anchor and provably cannot be given one, since a bar descending
at constant velocity reads |a| = g with a quiet gyro exactly as a bar at rest
does (`metrics.momentum_closure`).

The scale of it is not small: the reconstruction claims **0.17-1.28 m/s of
horizontal velocity at moments the bar is provably still.**

## The information is there

Pooled over all six deadlifts, 20 rest-to-rest intervals, each matched to the
rep it most overlaps (|r| > ~0.47 at p~0.05):

    corr(|dv_h|, h_rms)              +0.772
    partial(|dv_h|, h_rms | span)    +0.472
    partial(span,  h_rms | |dv_h|)   +0.184

**The observable screens off interval length; the reverse does not hold.** The
naive reading — "longer interval, more drift, more error" — is refuted by the
third row: once you know `|dv_h|`, span predicts nothing. And the VERTICAL
velocity error, which is C11's quantity, is a clean negative control at -0.254
raw and +0.098 partial, so this is specifically the horizontal observable rather
than a generic drift magnitude.

## And using it loses

`oracle.impact_correction` applies the minimal thing the measurement licenses —
a constant horizontal acceleration over each rest-to-rest interval, sized to
zero the observed velocity change. **Zero free parameters**; nothing is fitted
against the video, which is what makes it a fair test.

    capture             shipping   + impact correction
    deadlift_160x6_1      7.22            7.94
    deadlift_160x6_2      4.55            7.39
    deadlift_185x3       11.44           11.58
    deadlift_155x6_1      5.05           10.00
    deadlift_155x6_2      9.19            7.98
    deadlift_180x3       15.44           10.57

Worse on 4 of 6, median 8.21 -> 8.99.

## The two together are the finding

**The measurement carries information and the model wastes it. The bottleneck
is the correction's SHAPE IN TIME, not the measurement.**

This is the **fourth** correction to fail in the same way, and the pattern is
now the durable part:

    B7    anchored position at the impacts            lost
    B6    spliced velocity across them                lost
    C19   raised the detrend to a quadratic           lost
    C28b  constant accel per rest-to-rest interval    lost

Every one imposes a correction that is smooth across the rep, and B6 measured
the error to be **localised at the landing** — a few hundred ms of strap ringing
where the watch is still moving and the bar has stopped. C19 already generalised
half of this: the obstacle was never the detrend's ORDER, since any basis smooth
across the whole rep spreads a landing-localised error across the whole rep.
C28b extends it past the detrend entirely — it is not about step 7 at all, it is
about every correction anyone has applied.

**So, for the Kalman question specifically: a random-walk bias state would
reproduce this exactly.** A random walk distributes its correction smoothly in
time; that is what a random walk IS. It would take the same information and
spread it the same wrong way. What the evidence points at is a process model
with an **impulse or jump state at the impact** — velocity permitted a discrete
step there, with the smooth part constrained tightly. That is the one
configuration consistent with all four failures plus the r = 0.77, and it is
what B6 meant by "a correction local in time". A smoother is the right CLASS of
tool; the default process model is the wrong instance of it.

Note also that a KF inherits C28's observability limit rather than escaping it.
In ZUPT-aided INS a body-frame accel bias is observable only in directions
excited by the rotation between measurement epochs — the same condition as the
rank-2 result above. Adding states to a filter does not create observability.

*Limits, and they are real.* n = 20 with the partial correlation sitting on the
significance threshold, so this wants more deadlifts before anything is built on
it. Deadlift-only, permanently, for the reason above. And every number here is
downstream of C27's unresolved sticker-circle scale, though `beats_null` is
nearly invariant to it.

*Evidence:* `oracle.rest_observables`, `oracle.impact_correction`,
`tests/test_oracle.py` (12 passed).

### C28 — the ceiling on constant error models, and why two holds cannot separate them (2026-08-04)

Branch `c28-imu-video-oracle`, per the reconstruction-modules rule. The owner
asked how close the IMU can be brought to C27's marker paths using only steps
that would be logical as error mitigation. **Answer: to about the flat-line
null, and nothing that gets there transfers.** `src/oracle.py`, `analysis/43`.

*The method, and the discipline that makes it evidence.* Every parameter names
a real defect and its FITTED VALUE is checked against what that defect is known
to be — B2's |d| = 21/64/60 cm against a real 10-15 is the cautionary case.
Every model is also fitted leave-one-out, because an error model is a property
of the watch and should transfer while an absorber should not. All parameters
are constant over the capture; per-rep bases reach any residual you like and
B3's oracle already showed that means nothing.

    model                        ceiling   leave-one-out
    baseline                      4.00          4.00
    +bias                         4.00          4.00
    +tilt                         2.00          4.07
    +tilt+scale                   2.00          3.26
    +tilt+scale+lever             1.45          4.55
    +tilt+gravref                 1.83          3.57
    all five (15 params)          1.23          3.47

**The null is 1.54-1.68 cm.** Fifteen parameters fitted directly against the
answer reach 1.23; `bias+tilt` at 2.00 is still worse than a straight line. And
nothing generalises — every model collapses to 3.3-4.6 under LOO and two make
the held-out capture worse, `bias+tilt` sending `deadlift_185x3` to 21.39 cm.

**This reproduces B2 independently, on new data and a better referee.** `lever`
fits at 10.6 / 10.0 / 21.7 cm — plausible, unlike B2's 21/64/60, which is worth
noting — and STILL loses under LOO, 4.55 against a 4.00 baseline. C28 initially
speculated B2's conclusion might have been an artefact of the lockout-broken
referee C12 later found. It was not. B2 stands.

*The conclusion is structural:* **P3's error is not a constant in any frame.**
Not body, not world, not a scale, not a lever arm. The whole constant-parameter
family caps out at the null, so no estimator for any of them was ever going to
pay off, and that is the thing this entry exists to save the next agent from.

## Two findings inside the negative result

**1. `calibrate.accel_bias` subtracts in the wrong frame — on deadlift only.**
It measures the mean world acceleration over the stillest pre-set second and
subtracts it as a WORLD-frame constant, while its own docstring says the bias
is fixed in the BODY frame. Those agree only while the watch does not move, and
P3 is that the forearm rotates. Rotating it properly: **deadlift better on 5 of
6** (median 8.21 -> 4.61, `deadlift_185x3` 11.44 -> 3.82), **bench worse on 10
of 11** (median 1.88 -> 2.99, `bench_90x4_2` 0.64 -> 2.32 destroying the best
capture in the project).

**Not proposed as a change.** A fix that halves deadlift and doubles bench is
not a fix; it is evidence that the pause residual is a MIXTURE, which is what
C6's `anchor_tilt` docstring already says it is — "the tilt leak plus the
body-frame accel bias rotated into the world".

**2. Two still holds can NEVER separate those two terms. This is a theorem, not
a conditioning problem.** The C3 phase column gives two holds at two postures,
which looks like six equations for six unknowns:

    r = tau + R . b        (tau world-frame tilt leak, b body-frame bias)
    r_open - r_close = (R_open - R_close) . b

But `R_open - R_close = R_open (I - R_open^T R_close)`, and the relative
rotation fixes its own axis, so `(I - Delta) n = 0` identically. **The
difference of two rotation matrices is always rank <= 2, exactly**, verified at
5-179 degrees of separation with the third singular value at machine zero every
time. The body-bias component along the axis the wrist turns about is
unobservable from two holds, permanently.

C28 met this as |b| = 1.8e12 m/s^2 out of `np.linalg.lstsq(..., rcond=None)`,
which divides by the zero singular value rather than declining it. Truncating to
the observable plane gives the minimum-norm answer, and there the method WORKS
and validates against P4:

    rel. rotation between holds   noise amplification   recovered |b|
    3.6 deg                            16.1x               0.417
    6.6 / 13.8 deg                    8.7 / 4.2x       0.104 / 0.339
    33-150 deg                        0.5-1.8x           0.008-0.023

Above ~30 degrees the recovered bias lands on P4's table value of **0.0245
m/s^2** — the first time the accelerometer bias has been measured ON THE WRIST
rather than on a table. Below it, it recovers noise.

**Capture protocol, and it costs five seconds:** hold the bar still at THREE
deliberately different wrist postures before the set, ~1.5 s each, at least 30
degrees apart. Three pairwise differences have three different null axes, so
only b = 0 lies in all of them: the decomposition becomes fully observable and
well-conditioned. A tape-measure-class change, no code.

*Note what this does NOT buy.* Even where the decomposition succeeds it does not
improve horizontal rms, because — see the ladder — a correctly measured constant
bias is not what P2 is. It is worth having as a measurement of the sensor, not
as a correction.

*Evidence:* `analysis/43_imu_video_oracle.png`, `src/oracle.py`,
`tests/test_oracle.py` (10 passed). 43 is taken, next free is 44.

### C27 — the conic path meets real 8-sticker footage, and P2 gets a referee (2026-08-04)

Three 8-sticker deadlifts arrived — `deadlift_160x6_1`, `_2`, `deadlift_185x3`,
15 reps — and they are the **first captures able to test anything C26 shipped**.
C26 said so itself and the record was right to insist on it: four separate
defects surfaced, three in C26 and one in this entry's own first fix.

*It crashed immediately, and the reason generalises.* `_reacquire` returns a
TRIANGLE and `_best_correspondence` fits it against the model, so a nine-point
model raised `operands could not be broadcast together with shapes (3,) (10,)`.
Worse than a shape bug: `_reacquire` gates on `_triangle_ok(tol=0.22)` and
**eight evenly spaced stickers have no admissible triple** — best is every third
at 135/135/90, chord spread 0.255 — so the layout chosen precisely so spacing
would stop mattering could not re-acquire at all. **The same 0.255 that
motivated C26 recurs one function down, unfixed, because C26 grepped for the
seeder and not for every consumer of triangle geometry.** Fixed with
`_reacquire_conic` and `_conic_correspondence`; the second is the interesting
one, since on a circle a labelling IS a rotation, so it tests the
`len(found) x len(local)` rotations that put a found point on a model point —
81 — rather than 504 ordered triples.

It matters on deadlift specifically: with association alone coverage is **73.6%**
against bench's 98-100%, because the tracker loses the plate at the floor
impact. Bench has no impact; these three have 15.

*The detector fires more than once per sticker.* Seed models came back with 9
and 10 slots for 8 physical stickers, extras separated by **0.07-0.26 px**, and
`deadlift_160x6_1` carried a TRIPLE at 73.0/73.1/73.1 degrees. `fit_ellipse` is
unweighted least squares, so a doubled sticker votes twice. It showed as a
sticker-radius spread about the model centroid of 69.2-110.1 px — a 0.63 ratio,
MORE eccentric than the conic's own fitted 0.82, so it could not be
foreshortening. `_merge_close` fixes it and the effect is large: whole-clip
travel 76.2 -> 57.5 cm and 95.6 -> 55.2 cm. It also fixed, on its own, the
`deadlift_185x3` sync failure ("1 video landing against 3 IMU impacts"), which
had looked like a separate defect and was a symptom of the same one.

*`layout="auto"` never reached the conic.* It fell through only on an EMPTY
triangle list, and the assumption behind that — "an 8-sticker plate cannot
produce an admissible triple, so it falls through" — is true of the eight
stickers and says nothing about the rest of the frame. `candidates` returned
clutter triples on all three, so `vs_truth` scored them on a three-marker model
riding two markers for 37% of frames while the eight sat plainly in shot. A
silent wrong answer to a caller who asked for the default.

**Pooling both families into one shortlist was the first fix and it was wrong**
— worth recording because the failure is not the obvious one. `max_trials` is a
fixed budget of 12, group quality leads on `len(rim)`, so spurious conics off a
3-sticker plate crowded genuine triangles out of the shortlist *before
trial-tracking ever saw them*: `bench_92.5x4_3` fell to 8.2 cm of travel against
a real 24-31. Each family now gets its own selection budget and only the winners
are compared, on `_trial_merit`, whose three ingredients — full-marker fraction,
residual, apparent-size spread — are dimensionless and family-neutral. All four
benches return to C23's numbers exactly: `bench_95x2` 29.0 cm, residuals
0.13-0.38 px.

*And one defect of this entry's own making.* The re-acquisition path reported
`n_markers` as the conic's raw inlier count, giving 20 and 26 against a 10-slot
model, which then divided through `score` as if the fit were better than
perfect. It counts model slots filled now.

**The stickered plate is not the widest plate, and on a deadlift it is not**
(owner, 2026-08-04: "one bumper plate of diameter 44.5 and then black notched
plates after with a diameter of 42.5"). `plate_diameter` answers "what outline
does the template tracker see" — for deadlift the 445 mm bumper — and
`markers.py` needs a different quantity, the disc the stickers were stuck to,
which here is a 425 mm notched plate loaded outboard. Worth 4.7% of every marker
distance in the session. `truth.sticker_plate_diameter` splits the two and falls
through to `plate_diameter` everywhere else, so nothing earlier moves. The bar
still starts 22.25 cm up: that is set by the bumper, which carries the load.

## What the footage says

*The referee works, and that is the headline.* Coverage 99.2 / 100 / 100%,
median residual 0.55 / 0.59 / 0.28 px, and **every marker found in every decile
of travel, floor to lockout**. Contrast C12: the plate template is below
`GOOD_SCORE` in 166/166 top-of-travel frames. The referee that P2's deadlift
numbers were measured through fails exactly where the measurement is taken; this
one does not.

Per-rep video ROM is **51.4 / 51.9 / 51.5 cm — a 0.5 cm spread**, against the
three template-refereed deadlifts' 59.1 / 66.8 / 47.6, a 19 cm spread on a range
of motion fixed by the lifter's own limbs. `video_rom_flags` is empty on all
three, a first for any deadlift here. Sync lands at 19.2 / 16.0 / 9.3 ms.

*And the verdict on the reconstruction is worse, and more certain:*

    capture            h rms   null   beats_null   v rms   sign
    deadlift_160x6_1    7.22   1.65      0.23      3.45    1/6
    deadlift_160x6_2    4.55   1.55      0.34      3.70    1/6
    deadlift_185x3     11.44   1.60      0.14      1.76    0/3

All three are **3-7x worse than drawing no fore-aft motion at all**. The video
puts the bar inside 4.3-6.2 cm of fore-aft; the reconstruction sweeps 20-35.
Read these as replacing rather than confirming the old 0.70 / 0.35 / 0.13: those
were measured through a tracker C12 showed inventing ~10 cm of fore-aft at
lockout, which inflates `null_h_rms` and therefore FLATTERED the pipeline. These
are the first deadlift `beats_null` figures that mean what they say.

Two things improved: sign disagreement is 1/6, 1/6, 0/3 against 4/6, 2/6, 1/3,
and `deadlift_185x3`'s vertical at 1.76 cm is inside the +/-2-3 cm spec.

**Open, and it is the absolute scale.** `STICKER_RATIO = 0.858` is still
borrowed from the old three-sticker plate, and against it the video reads
**4.6-9.3% BELOW** the reconstruction (51.4-51.9 against 54.0-56.7). The video's
own consistency is excellent, so this is one constant and not noise: a ratio of
~0.92 — stickers ~1.75 cm in from a 21.25 cm rim — would close it exactly, which
is physically ordinary and must NOT be adopted by fitting it. The measurement
that settles it is the sticker-circle diameter with a tape, into
`bar_path(sticker_diameter_m=)`. Note `beats_null` barely moves under it
(0.24/0.35/0.15 at 445 mm, 0.23/0.34/0.14 at 425), so the horizontal verdict
does not depend on the open question.

*Evidence:* `analysis/42_conic_deadlift.png`, `python run.py --dlconic`,
`tests/test_markers.py`. 42 is taken, next free is 43.

### C26 — a conic fit, so a plate can carry more than three stickers (2026-08-04)

**Built for footage that does not exist yet, which is unusual here and is
stated up front.** The owner is stickering the next plate with **eight** rim
markers, and the shipping seeder cannot admit them: `candidates` enumerates
triples and `_triangle_ok` wants near-equilateral, but eight evenly spaced has
no admissible triple — the best is every third one at 135/135/90 degrees, chord
spread **0.255 against a tolerance of 0.25**. It misses by 0.005 and the
candidate list comes back empty, so without this the session would have produced
another untrackable capture.

*What was added.* `fit_ellipse` (five-point conic), `ellipse_candidates` (a
seeder with the same output contract as `candidates`, so `seed_frame`'s grouping
and C23's trial-tracking apply unchanged), `conic_track` (a per-frame refit),
and `layout=` on `seed_frame`/`bar_path`. `track` now works for any number of
rim markers rather than exactly three.

*What it buys, synthetically.* Two separate terms, and they are not equally
interesting:

| term | 3-marker centroid | 8-marker conic |
|---|---|---|
| centre, real bench spacing 129/102/129 | 7.38 px | **1.71 px** |
| centre, real squat spacing 94.9/111.4 | 13.55 px | **1.71 px** |
| scale at 40 deg of tilt | **-11.23 %** | +0.09 % |
| perspective, ideal 120 deg spacing, 20 deg tilt | **0.86 px** | 1.72 px |

**The first two rows are one number twice, and that is the finding.** The
conic's centre error is 1.71 px on both plates because it does not depend on the
spacing at all — it is the perspective floor of the last row, arriving unchanged.
The centroid's error is the spacing term *added on top of* its own 0.86 px floor,
and it grows 7.38 -> 13.55 as the plate gets worse. That is why the same code
refereed bench and could not referee squat.

**Read the last row.** The conic is *not* a perspective fix and is twice as bad
on that term — the ellipse centre is not the projected circle centre under true
perspective, and both estimators are biased outward. So on a plate stickered at
exactly 120 degrees this change would make the centre slightly WORSE. What it
removes is the SPACING assumption, which on real plates dominates that
difference, and the TILT dependence of the scale, which is larger still and has
no workaround on three markers.
`test_the_conic_centre_is_NOT_a_perspective_fix` pins the limitation so it
cannot drift into a claim.

*Two things worth carrying forward.* The physical requirement for the new layout
is a common **radius**, not even spacing — the opposite of what C23 told the
owner for the three-sticker plate, and easier with a tape. And
`bar_path(sticker_diameter_m=...)` retires `STICKER_RATIO` whenever the sticker
circle has actually been measured, which is the module's own stated weakest
point.

*Two bugs worth recording because both looked like something else.*
`np.linalg.svd(..., full_matrices=False)` on a 5x6 design returns only five rows
of `Vt`, so `vt[-1]` is the smallest NON-zero singular vector rather than the
null vector — the fit silently returned a conic through none of the points, at
exactly the five-point minimum, and surfaced as three unrelated test failures.
And the first residual scaled by the semi-minor axis, so a near-degenerate
sliver reported tiny distances for points nowhere near it and RANSAC preferred
slivers to plates.

*Seeding is by circumcircle, not by five-point RANSAC, and the arithmetic
forced it.* At a realistic 24% inlier ratio a clean five-point draw comes up
once in 4,200 samples, so 400 trials finds the plate ~9% of the time. Triples
come up once in 97 and can be enumerated outright, so there is no RNG.

**Ungated on real footage, and it must stay that way in the record until a
capture exists.** Three points cannot determine a conic, so none of the nine
captures held can regression-test any of this; the maths is gated synthetically,
which CLAUDE.md permits for algebraic identities and nothing more. What IS
gated on real captures is that the new path never runs on them —
`test_the_conic_path_is_inert_on_a_three_sticker_capture`, plus `bench_95x2`
still reading 29.02 cm of travel against C23's 29.0.

### C23 — the paired bench captures track; squat is blocked on the plate (2026-08-03)

C21 removed three admission gates and the six 2026-08-03 captures still did not
track. **All four benches now do. Both squats do not, and the reason is on the
plate rather than in the code.**

*What C21 left.* `seed_frame` chose its hypothesis on per-frame appearance —
the one signal its own docstring says does not work. C23 demotes that to a
FILTER and decides by **verification**: trial-track a shortlist and keep the
hypothesis that actually follows the bar.

*What made that affordable.* `detect` is essentially the whole cost of a track
— 15.4 s of a 15.4 s pass over `bench_95x2`. `track` now takes a per-frame
detection cache, so trials cost the association and fit arithmetic alone.
`bar_path` went 15.4 s to 24.5 s while doing twelve extra full-clip tracks.

*The merit has two terms and both were forced by a failure, not chosen.*

  - It leads on the **three-marker fraction**, and measures residual only on
    three-marker frames. A two-marker fit is exact, so a wrong hypothesis
    riding on pairs reports 0.00 px — which is exactly what the old seeder did
    on `bench_95x2` while tracking the bench.
  - It multiplies by **apparent-size rigidity**. Without it the merit picked,
    on `deadlift_190x1`, a hypothesis whose circumradius swung 88-128 px over
    the real plate at a spread of 0.013, and broke five tests. Measured
    spreads: real 0.013-0.04, impostors 0.20-0.43.

*Result on the four benches* — was 0.4-19.5 cm of travel against ~30 cm reps:

    capture           3 markers   residual med   travel   IMU rep ROM    err
    bench_92.5x4_1      1.00         0.38 px     27.8 cm     29.6      -6.1%
    bench_92.5x4_2      0.98         0.30 px     28.9 cm     29.4      -1.6%
    bench_92.5x4_3      0.99         0.37 px     29.5 cm     30.1      -1.8%
    bench_95x2          1.00         0.13 px     29.0 cm     29.5      -1.6%

C23 read that as three of four agreeing with the IMU to under two percent, and
called it the first independent confirmation of anything in this project.
**RETRACTED by C24, 2026-08-03 — the `travel` and `IMU rep ROM` columns above
are not the same quantity.** `travel` is the whole-clip marker range, which
spans the un-rack, where the bar is held ~3 cm above lockout; `IMU rep ROM` is
per rep. That ~3 cm is about the size of the disagreement the comparison was
covering. Measured per rep, with the video finding its own reps by peak
detection — no IMU, no sync — the video says **23.3-26.7 cm** across all 14 reps
against the reconstruction's **28.4-30.7**: **~20% apart, not 1.6%.**

The table is kept as run, because the numbers in it are right and it is the
reading of them that was wrong. `bench_92.5x4_1`'s -6.1% is still unexplained,
and C24 gives it company rather than an answer: it is also the only one of the
four whose horizontal loses to the flat-line null, at 0.71x.

**Neither instrument is convicted, and C24 declines to.**
`markers.calibration_report` declares a 7.3-11.2 cm spacing bias on these same
four clips — rim centroid 63-94 px off the detected plate centre, plate turning
32-33 degrees across the clip — which is larger than the ~5 cm in dispute. See
`analysis/41`, `python run.py --v2rom`.

*No regression, and two improvements.* The five 2026-08-01 captures keep their
travel to the decimal and two get better residuals — `bench_110x1` 1.07 to
0.09 px, `bench_85x6` 1.10 to 0.11.

*The scale was wrong, and the wrong SIGN is what found it.* Travel read 9-13%
low on all four, and the clip contains the un-rack, so it should if anything
read high. `truth.plate_diameter` keys on the lift alone and returned the black
notched plates' **425 mm** for a session shot on **450 mm blue calibrated
discs** — worth 5.9%, and it took three of the four from 9-13% out to under 2%.
Owner measured with a tape: blue calibrated 450, black bumper 445, black
notched 425. `truth.CALIBRATED_SESSIONS` now carries the exception, keyed on
the date in the filename so that moving a clip cannot silently change its
scale. Keying the table by lift alone was right while every capture came from
one plate set and became wrong the moment a session used another.

*Squat: the constellation was found by hand and the blocker is the sticker
placement.* On `squat_150x5` frame 900 the three stickers were read off the
colour frame and verified by drawing the circle through them — it lies on the
plate rim. Their angular spacing is **94.9 / 111.4 / 153.7 degrees**, not
120/120/120. Two things follow, and the second is the one that matters.

  1. `_triangle_ok` scores it **0.000** and rejects it outright; admitting it
     needs `tol` >= 0.28 against today's 0.25. Loosening it is not sufficient:
     hand-seeded, with the tolerance swept to 0.45, the track still holds only
     0.38-0.44 of frames at three markers with a 4.5-4.7 px residual, so a
     second cause remains unisolated.
  2. **Even a perfect track would not be a 1 cm referee on this plate.** The
     module assumes three equally spaced points project to a triangle whose
     centroid is the projected centre. At 94.9/111.4/153.7 the centroid sits
     **18.4% of the radius** from the true centre — 14.6 px, about 2.8 cm here.
     The bench plate is 129/102/129, i.e. 8.6% and 8.2 px, which is why bench
     works and squat does not.

**The cheapest fix is a tape measure, not code: re-sticker the squat plate at
120 degrees.** That removes the `_triangle_ok` rejection and the bias together.
Nothing in the reconstruction changes; this is the referee only.

*Still a tape measure, but the wrong one — superseded by C26 above.* Eight
stickers at a common radius, spaced however is convenient, removes both problems
without the plate having to be even at all, and removes a third the conic path
addresses and this entry does not mention: the 11.2% the similarity fit loses
from the SCALE at 40 degrees of tilt.

**Both squat captures were DELETED on the owner's instruction, 2026-08-03** —
`squat_140x5` and `squat_150x5`, video and IMU log, four files. They were
gitignored and untracked, so they are gone rather than recoverable. The
corpus is now 21 captures and 86 reps, all counted correctly. Note what went
with them: C22 below is measured entirely on `squat_150x5` and **cannot be
re-run**. Its numbers are kept there as the record; treat them as history, not
as something to reproduce.

*Evidence:* `tests/test_markers.py` (47 + 10 new), `analysis/39`.

### C22 — squat_150x5 counts 4 of 5, and two fix families are rejected (2026-08-03)

**The capture this is measured on was deleted later the same day (see C23), so
nothing here can be re-run.** The finding is kept because the mechanism is
about fatigue rather than about that one set, and it will recur on the next
heavy top set anyone films.

**NOT FIXED. Cause identified, two candidate fixes measured and rejected,
nothing shipped.** Counting stood at **22 of 23** captures and 95 of 96 reps
when this was written; after C23 deleted both squats it is 21/21 and 86/86,
which is a smaller claim rather than a better one.

`squat_150x5` (2026-08-03) segments **4 reps of 5**. There is a real fifth: a
concentric lobe at t = 50.2 s carrying 0.566 m against the other four's
0.604–0.633, at a peak velocity of 0.507 m/s against 0.564–0.647.

*The obvious suspect is innocent, and it was worth checking first.* CLAUDE.md
has predicted since C5 that a set with a genuine long mid-set pause would break
`_longest_cadence`'s 1.45 tolerance, and the inter-rep gaps here do lengthen
with fatigue — 4.58, 4.91, 5.32 s. But `_longest_cadence` never sees the fifth
rep: it is handed **four** candidates whose gaps ratio to 1.16, comfortably
inside tolerance. **The rest-pause failure mode remains hypothetical and this
is not an instance of it.** Neither is `peak_ratio`: every rep lobe sits inside
the 2.5x band.

*The actual cause is `_similar_cluster`, and it is a real assumption failing.*
Cluster membership requires mutual shape similarity above 0.7, and across a
heavy set the velocity profile drifts monotonically with fatigue:

    rep1   rep2   rep3   rep4   rep5      (shape correlation with rep 5)
    0.518  0.679  0.638  0.859  1.000

The fifth rep is similar to its neighbour and unlike the first. **The reps of a
fatiguing set form a CHAIN, not a CLUSTER**, and `_similar_cluster` tests for a
cluster. `squat_140x5`, the same lifter's lighter set from the same session,
holds 0.925 minimum and is unaffected — so this is fatigue, not the capture.
Against the median template of the accepted four the fifth scores 0.667 against
the 0.7 threshold; the best non-rep lobe scores 0.617. Lowering the threshold
would work on a **0.05** margin, which is the zero-margin trap C21 was about.

*Family 1, single-linkage chaining over the similarity graph: REJECTED.* It
fixes this capture at every threshold tried (0.70/0.75/0.80) and over-counts
badly elsewhere — `bench_spoto_90x5_1` reaches **11–12** windows against 5,
`bench_95x2` 4 against 2. Chaining is what lets a set walk into its own
re-rack.

*Family 2, extend the cadence run by a lobe that continues the rhythm AND
carries a rep's displacement: REJECTED, and this is the more interesting
rejection.* The fifth rep qualifies easily — gap ratio 1.30 against the
preceding 5.32 s, area ratio 0.94. But swept over a 4x5 grid of gap tolerance
(1.15–1.45) and area tolerance (0.70–0.95), **no setting reaches 23/23 and the
best reaches 21**, below shipping's 22. There is no plateau. The reason is
specific: bench's post-set movement continues the cadence and matches the area,
so the rule keys on exactly the thing that does not separate them.
`bench_90x4_1` and `_2` gain a spurious rep at every setting that admits the
squat's fifth.

*What a fix would have to do.* Distinguish "the next thing in the rhythm, at the
right size" on squat from the same description on bench. Neither cadence, area,
peak velocity nor shape does it alone. The `phase` column does not help — C5
already established the lifter re-racks before pressing Finish Set. An external
anchor would, and squat has none; see P1.

### C25 — the one-rep sync error was a search window too narrow to hold its own peak (2026-08-03)

Raised by the owner off `analysis/41`, as a segmentation fault dropping the
last rep. It is not the segmenter, and it is not the ambiguity C24 assigned it
to either.

*The segmenter was cleared before anything was changed.* Its candidate list
holds exactly **four rep-sized concentric lobes** on each capture — 0.26-0.31 m
at the rep cadence — and `_similar_cluster` chose all four. There is no fifth
candidate it could have dropped, so no change to `segment.py` could have
produced a different answer. Counting was and is 14 of 14.

*The cause.* `metrics.bench_sync`'s `max_lag_s` shipped at **5.0 s**, a default
never checked against a capture. The true correlation peaks on
`bench_92.5x4_2` and `_3` sit at **-6.37 s and -7.08 s**, outside it. The sweep
cannot report what it did not search, so it returned the best in-range point —
a sidelobe **exactly one rep period late** (0.44 and 0.38 against the true
peaks' 0.66 and 0.67). The other two captures peak at -0.08 and -0.44 and were
never affected, which is why the failure was total on two clips and invisible
in aggregate.

*Why C24 got the stage right and the cause wrong.* It read the rigid ~3 s shift
as `bench_sync`'s documented whole-rep ambiguity — peak and sidelobe of
comparable height on a periodic set. Given the whole curve the true peaks beat
those sidelobes by **50% and 76%**, so the peak was never ambiguous; it was
merely outside the window. The distinction matters because the documented
ambiguity is unfixable by construction and this was fixable in one constant.

*The window is load-bearing in BOTH directions, which is what makes the value
a measurement rather than a bigger guess.* Swept over all eleven bench captures
and the three deadlift controls:

| `max_lag_s` | what happens |
|---|---|
| < 7.00 | `_2` and `_3` return the sidelobe, silently |
| 7.00-9.75 | right answer, but the boundary guard fires on `_3` |
| **10.00-13.50** | identical answer on all fourteen |
| > 13.50 | `bench_92.5x2` prefers a spurious peak at **+13.59 s** (0.44) over its true peak (0.37) |
| >= 20 | `bench_90x4_2` and `bench_92.5x2` acquire fractional rivals and refuse |

`SYNC_MAX_LAG_S = 11.75`, the middle of that plateau, and as of part 2 below
it is where the sweep STARTS rather than where it stops. The deadlift control
is unmoved across the whole sweep — 3, 14 and 18 ms against the landings/
impacts fit — so the licence for trusting a bench number is intact.

*And a guard, because widening does not stop the next capture landing outside.*
The peak must have a full rep period of curve beyond it on both sides. Under
part 2 below this is what triggers widening; with an explicit `max_lag_s` there
is nowhere to widen to, so `bench_sync` raises. The reason is the acceptance rule rather than the peak:
this method accepts because every rival above `RIVAL_FRAC` sits a whole rep
away, and a peak within one period of the boundary is one whose ±1 P rival is
off the end of the sweep and cannot be examined — accepting there is accepting
on a test that did not run, the same shape as C12 and C17. It fires on all
three affected captures at the old 5.0 s, including `bench_95x2`, whose 5.0 s
answer was *right* but whose 4.75 s cadence left no room. Tightest margin at
11.75 s is 1.74 rep periods.

*Checked against something that is not the correlation curve*, since the fix
was found in it. All **14 windows now hold exactly one video chest touch, at
0.53-0.69 through the window** — independently reproducing C9's 0.567-0.648 on
a different dataset and a different tracker. Before, two captures had a window
holding none and a real rep outside every window.

*What moved, and what did not.* Horizontal rms on the two captures goes
1.86 → **1.12** and 1.66 → **1.39** cm, and `beats_null` 1.55 → **2.44** and
1.46 → **1.65**; `bench_92.5x4_2` also loses its one sign-disagreeing rep.
The other two captures are bit-identical. The ~20% per-rep ROM disagreement
C24 found is **untouched** — `own` and `IMU` never used the sync — so C24's
central retraction stands entirely. `bench_92.5x4_1` is still the lone
dissenter, now the only one of four losing to the null.

*The durable lesson, which outlives the constant.* `bench_sync` records that a
whole-rep ambiguity is harmless, and that was established for horizontal rms
and for window phase, both invariant to it. **Anything that PAIRS a video rep
with an IMU window is not** — `analysis/41`'s window bars read 2.4 and 1.4 cm
of a ~25 cm rep, having landed on the un-rack. A new rep-indexed quantity must
be checked against a whole-rep shift, not assumed into that box. And a
whole-rep sync error and a whole-rep segmentation error produce an identical
touch-minus-window table, so neither the figure nor that table can assign the
stage — only an anchor outside the periodicity can.

*Gated by* `tests/test_video_truth.py`:
`test_the_sweep_must_be_wide_enough_to_contain_its_own_peak` (both halves — the
peak is where it is recorded, AND 5.0 s refuses on the three captures that had
no room there while still syncing `_1`, which did) and
`test_every_paired_bench_window_holds_one_chest_touch`.

The first draft of that test asserted all four refuse at 5.0 s and `_1` failed
it, correctly: `_1` peaks at -0.08 s with a 2.83 s cadence and was never near
the boundary. Kept as written because a guard that fired on every capture would
be no evidence that it fires on the right ones.

*Recorded, not fixed, per the stay-on-task rule:*
`tests/test_markers.py::test_paired_bench_travel_agrees_with_the_imu` still
calls the whole-clip agreement "the closest this project has come to an
independent confirmation of anything", which C24 retracted in CLAUDE.md and
`analysis/README.md` but not in that docstring. C25 did not touch it — it is
C24's leftover, not something this change falsified.

### C25 part 2 — the search window is a starting point, not a bound (2026-08-04)

Raised by the owner against part 1: *"you've just hardcoded the fix, what
happens if there's a new set with bigger lag."* Correct. Part 1 claimed the
boundary guard turned a bigger lag into a refusal rather than a wrong number,
and that claim had not been measured.

*Measured.* Shift each bench video's clock by 0-30 s and ask `bench_sync` for
the offset back — 121 trials over the eleven bench captures:

| variant | ok | refused | SILENTLY WRONG |
|---|---|---|---|
| fixed 11.75 s (part 1, `c085599`) | 39 | 70 | **12** |
| widen until the peak is interior | 71 | 32 | **18** |
| ...plus the stability check | 71 | 35 | **15** |
| ...plus a 3-rep overlap floor | **72** | 34 | **15** |

Two things part 1 got wrong. Silent failures survive a fixed window — twelve of
them. And the usable headroom is **~9 s, not 11.75**: `bench_92.5x4_3` already
refuses at a 2 s shift, because its true lag of -7.08 s leaves 2 s of margin
against its own 2.68 s cadence. The constant was a bet that no future capture
exceeds ~9 s.

*The fix.* `max_lag_s` defaults to `None`, meaning start at `SYNC_MAX_LAG_S`
and widen by `WIDEN_FACTOR` until the peak is interior, capped by `reach` — how
far the two records can slide and still share `need` seconds. `reach` is
derived from the two recordings, so the only tuned quantity left is where the
search begins, and beginning in the wrong place now costs time rather than
correctness.

*Naive widening is the wrong trade and the table says so:* 39 -> 71 correct at
the price of 12 -> 18 silent errors. A refusal is recoverable and a wrong
number is not, so two guards pay it back.

  - **Stability.** A peak found only by widening must survive one MORE
    widening, or it was never a peak — it was the best point inside an
    arbitrary box, and a bigger box prefers somewhere else. Applied ONLY when
    widening happened, which is what keeps the eleven captures bit-identical:
    a peak interior to the starting window is accepted exactly as before.
  - **Overlap.** A lag is scored only where the records share
    `MIN_OVERLAP_REPS` rep periods. You cannot identify a periodic alignment
    from less signal than a few periods, and at the old flat 2 s floor a clip
    and its log match on noise. That is where the far-field failures were.

*What is left, and it is not a search problem.* Seven of the residual fifteen
are `bench_92.5x2` alone. **Excluding it, fixed and adaptive both leave eight**
while correct answers roughly double. It is a two-rep set — the least periodic
structure in the corpus — and it is the same capture whose true peak (0.37)
loses to a coincidence 13.6 s away (0.44), which is what caps the plateau in
part 1. Its lag is not identifiable once perturbed at all. Not fixed.

*The non-regression that licensed shipping it.* Every capture's unshifted
answer is bit-identical, asserted as an identity between the adaptive default
and a pinned sweep rather than by re-listing offsets — all eleven have an
interior peak, so none takes the new path.

*Gated by* `tests/test_video_truth.py`:
`test_a_lag_past_the_starting_window_is_found_by_widening` (a lag is
manufactured past the window by shifting the clock, since no capture held has
one) and `test_widening_does_not_disturb_a_peak_already_inside_the_window`.

*The durable lesson.* A constant wide enough for every capture you hold is
still a bet about the one you do not, and "it would refuse rather than lie" is
a claim about behaviour — it has to be measured like any other. Both C25 parts
began with a number nobody had tested against data.

---

## To do

Ordered by what unblocks the most. **Re-ordered by A3's measurements:** B6 and
B2 are where the error actually is; B3 dropped because measurement showed it
worth 2–4 cm, not 15.

### C5 — DONE 2026-07-31. Both segmenter failures fixed, by two mechanisms
Counting is **72/72** and every rep of all 17 captures sits inside its ROM band
bar `deadlift_180x3` rep 2 at 61.1 cm, which is inside the gate's slack and is a
different problem. Fifteen captures are unchanged rep for rep. Four lines of
behaviour changed; `WRONG_REP_COUNT` and `KNOWN_ROM_FAILURES` are now empty.
*Evidence:* `analysis/28`, `tests/test_segmentation.py`.

**The two defects looked alike and were not**, which is why they did not share a
fix. `squat_160x1`'s bad window was 1.26 s against 2.8–3.1 s for every other
squat — anomalous in *duration*. `bench_spoto_90x5_1`'s spurious windows were
2.1 and 2.6 s against real reps of 2.5–2.9 s — indistinguishable in duration,
anomalous only in *amplitude*. A criterion covering both would have been fitted
to the pair.

- `bench_spoto_90x5_1`: `_longest_cadence`'s tolerance was 1.6 and admitting the
  4.50 s post-set gap needs 4.50/2.86 = 1.573, so a run of six beat the true run
  of five on length alone. It is 1.45 now, the middle of a **1.35–1.55** plateau
  measured over all 17 captures: below 1.30 `squat_140x4_3` splits (its reps
  genuinely vary by a third, ratio 1.310), at 1.60 the failure returns. The old
  run of six was also *shifted* — it missed the real rep 1, so it was 4 real
  plus 2 spurious, not 5 plus 1.
- `squat_160x1`: `_similar_cluster`'s lateness tie-break encodes "set up first,
  lift second", which rejects everything *before* the reps and nothing after
  them. On a single, every cluster is size 1, so lateness decided alone and
  picked the re-rack. Singletons now rank by concentric displacement — an
  argmax, no threshold. Reads 67.0 cm.

**Two live caveats, neither hypothetical.** A rest-pause or cluster set has a
real mid-set gap above 1.45 and would be split. *(**That one came true on
2026-08-06** — a paused squat's cadence lengthens rep by rep, two of four counted
3 of 4, and the fix was a new RULE rather than a new constant because the
admissible band had closed to nothing. `_longest_cadence` now admits on LOCAL
drift and ties break on cadence evenness; tol is 1.50. See C31a above. The
caveat's replacement is narrower and thinner: 2.4% of margin either side, and a
capture that pauses harder still will push the floor into the ceiling.)* And the
singleton rule claims a
rep moves the bar further than the movements bracketing it, which is measurably
**false on bench** — `bench_92.5x2`'s unrack carries 0.433 m against 0.295 for a
real rep — so a bench *single* would pick the unrack. Clustering saves every
bench capture held, and a gate pins that containment.

`phase` cannot help either: the lifter re-racks before pressing "Finish Set", so
both spurious windows sat inside `phase == 1`. The C3 column marks the closing
hold, not the end of lifting.

**This fixes count and extent, not phase.** A window half a rep out of step has
the right count, duration and amplitude, so none of the above could see phase.
*C9 then measured it: bench is in phase, 15 of 15. Squat is still unverified.*

### B6 — attack the acceleration error itself  ← splice rejected; NOT unblocked by B3
A3 puts the error upstream of the detrend and gives it a shape: a smooth arch
at rep frequency, 5–15 cm of horizontal per rep. The metric B6 was waiting on
now exists, so this is unblocked.

**C6 narrowed the target sharply, and removed two candidates.** Not attitude:
Core Motion holds 0.05° → 0.14° across a set. Not gyro bias: the two-anchor
baseline gives 0.014 °/s. Not sensor bias on bench or squat, whose per-rep
residual is 0.003 g — the table noise floor, i.e. nothing to remove. What is
left is deadlift's 0.010–0.030 g, three quarters of it injected in the ±100 ms
around each floor impact, plus a vertical momentum deficit of ~1.5 m/s per rep.
Start there; the other three doors are closed.

**The constant-bias family is now measured and rejected, 2026-07-30.** Three
variants against video, all worse than shipping (5.05 / 9.19 / 15.44 cm):

| variant | horizontal rms |
|---|---|
| zero-mean acceleration per rep | 19.63 / 27.14 / 6.55 |
| zero-mean, no position detrend | 136.07 / 94.80 / 34.64 |
| constant bias from rest-to-rest velocity closure | 15.50 / 11.64 / 29.12 |

The arithmetic rules out the family, not just these attempts. A constant bias
`b` leaves `b·T²/8` after a linear detrend. The measured error implies
0.0016–0.0047 g; every closure-derived estimate is 0.0076–0.0266 g, 1.9–7.1×
larger. If the signal really held 0.0266 g it would show 37.7 cm of vertical
error and it shows 5.24. So the constraint is absorbing a **localised** error
and spreading it as a constant, injecting a parabola bigger than what it
removes. That is why the oracle cap sits at ~30%: a constant cannot represent
an impulse.

*The measurement that shows it directly:* cumulative vertical velocity across a
validated rest-to-rest interval is smooth and physical through the pull and the
descent, then rings for several hundred ms at the floor impact and settles
0.4–1.5 m/s short of zero. See `analysis/25`.

**What is left — and item 1 has now been measured and rejected.**

1. ~~**Integrate across the impact, not through it.**~~ **REJECTED 2026-07-31.**
   Built, measured against a rule fixed in advance, and it lost. See *The
   splice, measured and rejected* below.
2. Time-varying correction. Now the only survivor, and see the caution below —
   it inherits the same obstacle.

*Item 1 used to be "#14 first, not as a side quest", on the strap-resonance
detector. That is withdrawn: #14's detector was REMOVED as undetectable at
100 Hz — the post-impact spectrum has no repeatable peak (10–47.5 Hz across 15
impacts, peak/median 2.7–12.5) and Nyquist is 50 Hz, so a watch-on-strap
resonance aliases to an arbitrary bin. The ringing is real and is where the
error enters; it is simply not resolvable as a resonance, and rejecting the rep
was never the right response. The fix belongs in the reconstruction.*

**C11 (2026-07-31) sharpened what the splice has to preserve, and confirmed the
integrator does not need touching.** Measured between two moments the VIDEO says
the bar was still — an identity with no tunable in it, and immune to the video's
per-capture vertical scale error since a scale cannot move a zero crossing:

| intervals | n | median closure | worst |
|---|---|---|---|
| bench, real lifting | 44 | −0.013 m/s | 0.102 |
| deadlift, floor→lockout (the pull) | 8 | −0.010 m/s | 0.063 |
| deadlift, interval containing a landing | 9 | −0.589 m/s | −1.428 |

The middle row is the strongest: those are 55–66 cm loaded pulls **from the same
captures as the failing row**, because the dwell detector splits a deadlift rep
at the lockout. Same lift, load, wrist and calibration; only the landing differs.
Bench then confirms it on a lift with no landing at all. As residual
acceleration, 0.0019 g and 0.0008 g against 0.0300 g — the first two are the
0.0025 g measured on a table.

**And it reconciles with B5 rather than contradicting it.** B5's velocity-step
ratio of 1.04 is min-to-max AMPLITUDE; C11's is the NET. Both on the same 15
impacts: amplitude 1.10, net 0.41. The spike's size is captured and where the
velocity settles afterwards is not — so the splice must preserve the amplitude
B5 measured while correcting the settling point. `analysis/31`,
`python run.py --closure`, `metrics.momentum_closure`.

**The splice, measured and rejected (2026-07-31).** `analysis/32`,
`python run.py --splice`, pinned in
`test_the_impact_splice_fixes_the_closure_and_loses_anyway`.

At each validated rest instant the bar's velocity is zero, so the accumulated
velocity error there is known exactly. The splice removes it with a ramp across
the impact window — the ringing window C11 identified — rather than spreading it
over the rep as the constant-bias family did.

**It does exactly what it was built to do.** Vertical momentum closure across a
landing: −0.778 / −0.522 / −0.339 → **−0.049 / −0.004 / −0.019 m/s**. The defect
C6 found and C11 localised is gone.

**And it loses on every variant:**

| splice | detrend | horizontal rms, cm |
|---|---|---|
| none | xyz | **5.05 / 9.19 / 15.44** ← shipping |
| z only | xyz | 5.05 / 9.19 / 15.44 ← bit-identical |
| xyz | xyz | 10.09 / 5.90 / 14.61 |
| xyz | z only | 28.51 / 18.00 / 61.36 |

Three things that rules out. *A vertical-only splice cannot help the spec* —
`pipeline_h_rms` reads columns 0 and 1, so a correction confined to column 2
leaves it bit-identical. Measured, not argued, and it means **no vertical fix
can ever satisfy a horizontal decision rule.** *An all-axis splice
over-corrects*, because step 7 already removes that horizontal drift and doing
it twice is worse on the capture with the best baseline. *And the splice cannot
replace the detrend either*, which was the last live hypothesis — row 4 is that
test and it is 3–5× worse.

**The reason, and it generalises.** The detrend constrains position across a
whole rep; the splice constrains velocity at one instant per rep. **A sparse
true constraint does not substitute for a dense false one.** That is B7's
conclusion reached from the opposite direction — B7 put it as "a true constraint
in the wrong place" — and it now holds on the vertical as well as the horizontal.

**A second obstacle, which is the part that changes the plan.** The splice
breaks a bound it was never aimed at: per-rep vertical ROM goes to
**82.6 / 65.4 / 64.1 cm against a 61 cm ceiling**. Removing an error `e` over a
window `T` injects about `e·T/2` of position — 15–23 cm here — and step 7's
detrend is **linear**, so it cannot remove a quadratic. Any correction localised
in time hits this, including the time-varying models left in item 2. **B6 is
blocked on B3**: the detrend has to be able to absorb a local correction before
a local correction can be worth making.

**Corrected 2026-08-02 (C19): B3 is not the unblocker.** The quadratic detrend
this asked for was built — pinned by the rep's own velocity closure, needing no
new anchor — and the splice got *worse* under it, not better: ROM
78.1 / 70.4 / 116.4 cm against the linear detrend's 62.4 / 60.4 / 58.3, and
horizontal 16.41 / 19.27 / 24.87 against 10.09 / 5.90 / 14.61. A quadratic
spreads a landing-localised error across the whole rep exactly as a constant
does; it just spreads more of it. **What item 2 needs is a correction local in
time, and a detrend that is also local in time to sit under it** — not a
higher-order global one. See B3 and `analysis/38`.

Bench and squat need none of this — no impact, and both a per-rep residual and
now a vertical closure at the sensor's noise floor. Their problem, if they have
one, is a different problem, and nothing external measures it yet.

Every attempt is measurable against `metrics.vs_truth`, which is the whole point
of having built it. `analysis/25_b6_bias_models.png`, `python run.py --bias`.


### B2 — step 6 implemented; the term is 3× smaller than we thought
`correct.apply_offset` works and step 6 is no longer a blocked stage.

**CLOSED 2026-08-06 as to availability, STILL STANDING as to fitting.** This
entry used to end "it is **off by default** because `d` is unmeasured, and B2's
main finding is that it cannot be measured from what we have." Half of that is
now false and the more important half is not. **The owner tape-measured `d` and
step 6 is ON by default** — `correct.WRIST_OFFSET_M`, `pipeline.run
(wrist_offset="auto")`, C31 in 70b2a63. **B2's actual finding — that `d` cannot
be FITTED from the video — survives and was re-confirmed twice**: C31 fitted
`lever` on top of the tape and got residuals of 47.9 / 17.7 / 2.4 cm at
108 / 74 / 4 degrees, and C31b found position rms monotone in |d| out to 3× the
tape, i.e. no interior optimum for an optimiser to find. The sentence below,
"`d` wants a tape measure", was the right call and it was taken. Do not re-open
the fit. See TASKS.md C31 and CLAUDE.md's step-6 banner.

*Payoff against the prediction at the end of this entry (~1 cm bench and squat,
~2 cm deadlift): deadlift horizontal moved 7.22/4.55/11.44 → 6.65/4.39/10.61 cm,
so ~0.2–0.8 cm rather than ~2 — the right sign, smaller than predicted. Bench
horizontal was a coin flip and bench VERTICAL improved on 6 of 6 by 20–25%,
which this entry did not predict at all.*

**The 8–13 cm figure was wrong.** This entry and `pipeline.py` both claimed
`R(t)·d` varies by 8–13 cm horizontally on every lift, and called it the largest
unmodelled term in the system. Measured properly — within a rep, after step 7,
swept over every possible direction of `d` at |d| = 14 cm:

| lift | worst direction | typical |
|---|---|---|
| bench | 4.2 cm | 1.2 cm |
| squat | 4.4 cm | 1.3 cm |
| deadlift | 6.4 cm | 2.4 cm |

The rotation premise is fine — the watch turns 18–22° through a rep, so the ~16°
assumed in `correct.py` is right. Two things shrink it at the output: only the
arc component perpendicular to the rotation axis sweeps at all, and step 7 runs
afterwards and removes the linear part of what is left. Deadlift is the
*largest* of the three, which is the opposite of the old "deadlift is exempt".

**`d` is not identifiable from the video.** Fitting it against `vs_truth` is
ill-conditioned — joint optimum at |d| = 31 cm, per-capture fits at 21, 64 and
60 cm, against a real wrist-to-bar distance of 10–15 cm. Those are the optimiser
absorbing P3, which is also a body-frame constant swept by the same rotating
forearm and so nearly degenerate with `d`. Leave-one-out confirms it: one fold
returns |d| = 129 cm and makes the held-out capture worse, 5.1 → 16.2 cm.

**So `d` wants a tape measure**, watch centre to bar centre in watch axes, once.
Same class of thirty-second fix as measuring a plate. Expected payoff, from the
table above: ~1 cm on bench and squat, ~2 cm on deadlift.

### B3 — rework the per-rep detrend
**The endpoint-median fix was tried and is worth nothing.** `edge=5` gives
10.08 cm mean horizontal against 10.01 at `edge=1`. The reasoning behind it is
still sound — a line through two samples is maximally noise-sensitive at
exactly the indices it depends on — but on these captures it does not show, so
it defaults off with the measurement recorded next to it.

**A lead worth following, found by accident.** A buggy version of that change
under-corrected the drift line by 1.7%, and *that* improved horizontal by ~15%.
Sweeping the shrinkage deliberately: λ=0.99 gives 4.8/7.5/13.1 against
5.1/9.2/15.4 at λ=1. So **the closure over-corrects**, which is exactly what A3
predicted — the bar misses closing by 1.9–4.3 cm and step 7 forces that to
zero, so leaving ~1% of a ~2 m drift in puts back about the right amount.

Not usable as it stands: the optimum is sharp and inconsistent (capture 1 wants
0.99, capture 3 wants 0.97, λ=0.90 costs 39 cm), so a global λ is a fudge factor
tuned on the validation set. The principled version estimates the true
non-closure per rep and leaves that in — which needs a source for it other than
the video being validated against. That is the real B3.

**And harder than it looked.** The horizontal closure is false — the bar
misses closing by 1.9–4.3 cm — but B7's ablation showed it is also carrying
**metres**: drop it with nothing in its place and error goes to 3–5 m. So the
task is not "remove a false assumption", it is "find a constraint that can
replace it". The floor-impact anchor was the obvious candidate and it lost.

`axes` is now a parameter on `detrend_rep`/`detrend_set` so the next candidate
can be measured against the same numbers rather than re-deriving them.

**C19, 2026-08-02 — the quadratic is REJECTED, and the oracle above it is the
finding worth keeping.** `python run.py --b3oracle`, `analysis/38`, pinned in
`test_the_quadratic_detrend_is_worse_than_the_line`. The decision rule was
fixed and committed (`acf8c4e`) before any number was read; both thresholds are
the 1 cm spec rather than new constants, because nothing here is held out.

*First, the oracle, which caps the whole family.* Step 7 subtracts one
particular line per rep, so `err` minus the BEST line is a floor no linear
detrend can beat however it is estimated, and `err` minus the best
line-plus-quadratic is that floor one order up. Median over the ten scoreable
captures, per-rep horizontal rms in cm:

| | shipping | oracle: best line | oracle: + quadratic | null |
|---|---|---|---|---|
| median of 10 | 2.72 | 1.04 | 0.33 | 2.85 |

**Rule 1 (headroom) PASSES at +1.67 cm, and that is more than this file has
been claiming.** B3 has been described as worth 2-4 cm; the linear family alone
has ~10 cm in it on the worst capture, `deadlift_180x3` going 15.44 -> 4.89.
Today's endpoint line is simply not the best line.

**Rule 2 (the quadratic pays) FAILS at +0.71 cm.** But the per-capture split
matters far more than the median, and it is a clean split by lift:

- **Bench**: oracle-quadratic reaches **0.25-0.55 cm**, inside the 1 cm spec.
  A better per-rep detrend genuinely could bring bench to spec.
- **Deadlift**: oracle-*linear* is 3.64 / 3.78 / 4.89 against nulls of
  3.55 / 3.23 / 1.96 — **no per-rep line, however estimated, beats a flat
  vertical line on any deadlift.** Oracle-quadratic (3.11 / 2.02 / 1.89) only
  just does. The whole per-rep polynomial family is capped well short of spec
  on deadlift, the way B6's oracle capped constant-bias at ~30%.

*Then the buildable estimator, and it loses.* `detrend_rep(order=2)` adds one
quadratic term pinned by a second closure the rep already supplies: a rep is
periodic in VELOCITY as well as position, so the reconstructed `dv` across a
rep is drift exactly as `dp` is. Three constraints, three coefficients, no new
anchor, no video, no threshold, and it degenerates to today's line when `dv` is
zero. It is the obvious way to get the quadratic B6 asks for.

| capture | shipping h | order=2 h | order=2 v | order=2 ROM |
|---|---|---|---|---|
| deadlift_155x6_1 | 5.05 | 29.11 | 48.67 | 78.2 |
| deadlift_155x6_2 | 9.19 | 25.20 | 41.75 | 68.4 |
| deadlift_180x3 | 15.44 | 12.17 | 73.11 | 116.4 |

against a 61 cm ROM ceiling and a shipped vertical of 5.24 / 6.60 / 5.24.
**Vertical and ROM reject it on 3 of 3; horizontal does not** — `deadlift_180x3`
improves, 15.44 -> 12.17, so "it loses on horizontal" is not a claim these
captures support. **And do not read the median**, which improves 2.72 -> 2.23
because bench has no landing: that is the aggregate-that-hides shape again, and
it is why the rule was fixed per-rule and in advance.

**Rule 3 (the B6 unlock) FAILS, and this is the one that matters**, because
unblocking B6 is why B3 was promoted to first at all:

| | shipping | splice, order=1 | splice, order=2 |
|---|---|---|---|
| deadlift_155x6_1 | 5.05 cm / 57.8 | 10.09 / 62.4 | 16.41 / **78.1** |
| deadlift_155x6_2 | 9.19 / 58.5 | 5.90 / 60.4 | 19.27 / **70.4** |
| deadlift_180x3 | 15.44 / 53.7 | 14.61 / 58.3 | 24.87 / **116.4** |

A quadratic detrend does not let the splice keep vertical ROM in bounds. It
breaks the ceiling *harder* and loses more horizontally. (A prediction made
before the run — that the splice would zero `dv` and collapse order=2 back to
order=1 — was wrong: rep boundaries sit ~10 ms after the impacts, not at the
rest instants, so `dv` survives the splice. Measured rather than argued.)

**Why, and it generalises past this attempt.** C11 established the deadlift's
velocity deficit is injected AT THE LANDING and nowhere else. A quadratic
removes it correctly *in total* by spreading it smoothly across the whole rep,
injecting `dv·T/8` at mid-rep — ~31 cm at `dv` = 1 m/s and T = 2.5 s, an order
above the 5-15 cm being corrected. B6 measured that **a constant acceleration
correction cannot represent an impulse.** This measures that **a quadratic
cannot either.** The obstacle was never the detrend's ORDER: any basis smooth
across the whole rep spreads a landing-localised error across the whole rep,
and raising the order raises what it spreads.

**So the standing plan is wrong and P3 has been corrected.** "B3 first, because
it unblocks every localised correction after it" assumed the blocker was that
the detrend could not represent a quadratic. It can now, and nothing is
unblocked. What B6 needs is a detrend that is *local in time*, not one that is
higher-order — and B3 and B6 may be the same problem rather than two.

*Kept rather than deleted*, against B7's precedent of deleting rejected code:
`order` stays on `detrend_rep` defaulted to 1 and bit-identical, pinned by a
test asserting order=1 equals the shipped call. The reason is that TASKS.md B6
asks in so many words for a detrend that can absorb a quadratic, so the
measurement needs to sit next to the idea or it gets re-proposed on the
strength of the reasoning. Overrule if you would rather it went the way of the
splice.

*Still open, and the oracle says where to look:* bench is reachable and
deadlift is not, so a detrend improvement is a BENCH result, not a P2 fix. The
principled λ above still wants a source for per-rep non-closure other than the
video.

### B4 — step 8 implemented; the SIGN is still open  (2026-07-30)
`project_to_plane` and `confidence` no longer raise, and `principal_axis` uses
`eigh` — the `eig` call on a symmetric matrix was why every caller wrapped the
result in `np.real`. All nine steps now run on all 17 captures.

`confidence` is derived rather than tuned: `min_ratio(n_reps)` inverts
Anderson's asymptotic angular error for a principal eigenvector to find the
eigenvalue ratio that pins the axis to 20 degrees. The one judgement in it —
effective sample size is the REP count, not the sample count — is stated as a
judgement and checked by a bootstrap in `tests/test_projection.py`, which is
written as a distribution statement because it does not hold on every capture.

It vouches for **11 of 17** sets — 9 when this was written, before C5.

Half the evidence that it discriminates has since evaporated. It used to reject
both captures with a known segmentation defect (`bench_spoto_90x5_1`'s 91.6 cm
excursion, `squat_160x1`'s single rep); C5 fixed both defects and both now pass
comfortably (excursion 91.6 → 9.4 cm at ratio 20.2, and ratio 69.7). Confidence
was agreeing with the segmenter's failures, and stopped objecting when they
stopped happening — consistent with it working, but no longer independent
evidence that it does. What survives is the stronger half: it still rejects the
two deadlifts with the worst measured error (35.9 and 30.0 cm excursion, 9.19
and 15.44 cm rms) and accepts `deadlift_155x6_1`, the best at 5.05 cm — a
comparison against video rather than against this pipeline. Treat
`squat_160x1`'s 69.7 as weak: single-rep PCA, where `min_ratio(1)` is 10.1.

**Vouching for the axis is not vouching for the path**, and the code says so in
three places. An error at rep frequency (P3) lands in the covariance as variance
and makes the ratio look BETTER, so no function of ratio and excursion could
detect it. `analysis/27_bar_paths.png` labels every panel with what external
evidence exists for that lift.

**Still open — the sign.**

A3 confirmed the mirror is not hypothetical — on `deadlift_155x6_2` the axis
came out backwards and had to be flipped against the video. It also found
something the planned fix does not address: **4 of 6, 2 of 6 and 1 of 3 reps
disagree with their own set's sign.** Resolving the sign from wrist attitude at
the pause gives one answer per set, which cannot be right for a set whose reps
point different ways. Whether that is a step-8 problem or just P2 showing
through is open — fix the acceleration first (B6) and re-measure before
designing around it.

### C1 done, C2 abandoned, C3 added — watch logger
`watch/WatchApp/`. Typechecks clean against the watchOS 26.5 SDK.

**C1 and C3 are validated on lifts as of 2026-07-30.** Seven captures came off
the new logger — `squat_160x1`, `squat_140x4_1/2/3`, `bench_spoto_90x5_1/2/3` —
and every one carries a clean `phase` column: 4.2–4.8 s opening hold, the reps,
and a 3.0 s closing hold, exactly as designed. **The two-anchor measurement
C1 exists for has not been made.** The data is no longer the blocker; comparing
the attitude solution across phase 0 and phase 2 on those seven captures is the
next piece of work, and it is what answers P5's replacement question.

**C1 — closing stillness hold. Built.** "Finish Set" starts a 3 s countdown and
saves itself, driven off the device-motion callback rather than a Timer because
that callback keeps firing when the screen sleeps. Its *purpose* changed once P4
was re-measured: it is no longer about estimating gyro bias over a long
baseline, because there is barely any gyro bias. It is about answering whether a
SET perturbs Core Motion's attitude solution — two anchors bracketing 40 s of
lifting. That is now the live question.

**C2 — abandoned. `CMMotionManager.isGyroAvailable` is FALSE on watchOS.** Raw
gyro is not offered by the OS; tried on one motion manager and on two, and the
on-screen badge reported no hardware. There is no public-API route, so **P5 is
closed as permanently unobservable**. Two diagnostic captures carry the four
empty columns; `io.load_log` still reads them so those files load.

The loss is small, and P4's measurement is why: the residual *after* Core
Motion is 0.002 °/s, so its internal estimate has almost nothing to explain.

**C3 — a `phase` column. New, and the useful one.** `0` opening hold, `1` reps,
`2` closing hold. It tells the pipeline where the anchors are instead of making
`stillest_window` guess from quietness — which matters because the guess is
contaminated: the opening 3 s it searches is exactly when a finger is on the
Calibrate button. **The cleanest stillness in any capture is the tail of phase
2**, the only quiet window not followed by a screen tap. Using it is the first
thing to try on a capture that has a real closing anchor. `check_log` now
verifies the hold exactly where the column exists.

Also fixed: "Discard" used to write a CSV.

`synth.py` gained `settle_pause` so it models the protocol, not just the
sensors — otherwise every synthetic log trips the C1 warning.

**And it exposed a fake test.** `test_accel_bias_removal_meets_horizontal_spec`
asserted a 1 cm threshold on synthetic data and broke once the longer record
moved the noise draw. Across 12 seeds it spans 0.29–1.86 cm — it was **failing
on 5 of 12 and passing only because seed=0 landed at 0.39**. A threshold sitting
inside the generator's own spread constrains nothing; that is gates 5 and 6 in
miniature. Rewritten as a comparison — bias removal must beat no removal, 12/12.

### D — replace the remaining synthetic tests
Gates 5 and 6 are already deleted. Keep the algebraic-identity tests; replace
the rest with real-data gates. Largely done incidentally — worth a pass to
confirm nothing behavioural survives.

---

## Capture protocol

Not code, and the highest value per effort available:

- ~~**Measure a plate.**~~ **DONE 2026-07-30.** Black notched 425 mm, black
  bumper 445 mm, blue calibrated 450 mm. `truth.PLATE_DIAMETER_M` is now a
  per-lift table keyed on the largest plate in shot. It moved A3's numbers by
  under 1% — a useful negative result, since this was flagged for months as a
  scale risk and the real scale error is 20× larger and elsewhere.
- ~~**Put the watch on and re-shoot with the markers.**~~ **DONE, over three
  sessions.** `data_v2/raw/` now holds thirteen paired captures — four benches
  (2026-08-03), three 8-sticker deadlifts (2026-08-04), two spoto benches and
  four squats (2026-08-06). The squat ask at the end of this item was answered
  last and best, though only PARTLY: **two of the four 8-sticker squat clips
  track cleanly** (100% coverage, 0.69-0.88 px, travel 59-60 cm) and **two do
  not** — `squat_170x1` and `squat_pause_140x4_3` report 14.0 and 24.7 cm of
  travel against 65-70 cm squats. C31 first wrote "the plate tracks at 100%",
  having measured one capture and generalised; corrected 2026-08-07. So what
  remains is BOTH code and capture: `metrics.vs_truth` refuses squat by a
  [SUPERSEDED: the refusal was removed 2026-08-15, see G2 at the top] 
  hardcoded check whose stated reason describes the old template footage, AND
  half the squat footage is not yet usable. The original text follows.
- **Put the watch on and re-shoot with the markers.** ~~Now the highest-value item
  in this list, and it displaces the two below.~~ The 2026-08-01 session solved
  the referee and produced nothing to referee: five marker captures, zero IMU
  logs. C15 shows the markers work — 100% tracking, sub-pixel fits, and they
  hold at the lockout where the plate template is lost on every deadlift — so
  much of the two items below is answered by *marking the plate* rather than by
  moving the camera. What is missing is a capture with both. One session with
  the watch on would give this project a referee that works at lockout and
  something to score with it, and would let `vs_truth`, the sync and
  `beats_null` be re-measured on footage whose fore-aft at the top of the pull
  is not invented. Markers on the **squat** plate would go further still: squat
  is the one lift with no external horizontal check at all, and its footage
  fails for the same dark-plate reason the markers remove.
- **Re-shoot with a vertical reference in frame** — a metre rule against the
  rack, in shot for the whole clip. ~~Now the highest-value item here.~~ **Partly
  answered by C15**: the sticker constellation measures its own apparent size in
  every frame, so the per-frame scale is now measured rather than extrapolated
  from the bottom of frame. It is worth 0.6–1.4 cm on deadlift. It does not fix
  the *absolute* scale, which still rests on one measured constant, so a metre
  rule would still earn its place — it is no longer the top of the list. The
  video's vertical scale is wrong by up to ±20% per capture (per-rep ROM 59.1 /
  66.8 / 47.6 cm against a 61 cm ceiling) and the plate cannot fix it, because
  it calibrates at the bottom of frame for travel reaching the top. The referee
  for P2 is mis-scaled and no amount of code repairs footage. See `analysis/23`.
- **Step the camera back. Promoted to joint-highest by C12 (2026-07-31), because
  it turns out DEADLIFT needs it too.** The deadlift tracker is lost at lockout —
  97–100% of the frames in the top 10 cm of travel score below `GOOD_SCORE`,
  against 0% at the floor — and it invents ~10 cm of fore-aft motion there, on
  the one lift this project treats as its best-founded truth. Squat clips the
  plate at lockout and two of the four 2026-07-30 captures do not track at all,
  so this is also what converts squat to truth with no code. *(That last clause
  was overtaken on 2026-08-06: stickers converted squat to truth instead, at
  100% coverage — the camera never moved. What the deadlift half of this item
  asks for was independently answered by C27, whose conic marker path finds every
  marker in every decile of travel. The remaining case for stepping back is
  bench's hand-placed seed and the ~4% scale it carries.)* Bench sits the
  plate against clutter; it is truth already (C8) but only from a hand-placed
  seed in `truth.SEEDS`, and a clear plate would let auto-seeding work and drop
  the ~4% scale uncertainty the hand-read radius carries. **One camera change
  fixes a defect on all three lifts.** Note what does NOT fix it: shrinking the
  template raises NCC and makes the track worse (ROM 60.5 → 74.1 cm). See
  `analysis/34`.
- **A capture with the session running and 30+ s of wrist-down.** *Rewritten
  2026-08-01.* This used to ask for a **sessionless** capture, as the falsifier
  for C7's deletion of the `HKWorkoutSession`. **It was collected by accident and
  C7 lost** — the captures truncated and a Workout-app session took priority
  while the wrist was down. C16 put the session back, so what is now wanted is
  the same test *with* it: if the rate still drops, the session is not what keeps
  Core Motion alive and the cause is elsewhere. Check gaps in `dt`, never the
  sample counter, which rises either way. Note the standing consequence is
  unchanged in direction: **every capture taken between C7 and C16 is suspect**,
  and any that show wrist-down truncation should be re-taken. See
  `watch/README.md`.
- ~~**Tape the wrist-to-bar offset `d`.**~~ **DONE 2026-08-06, and it was the
  best-value item on this list.** Squat 5 cm toward the crown + 4 cm out of the
  case (|d| = 6.4 cm); bench and deadlift 9 cm toward the crown + 3 cm into the
  case (|d| = 9.5 cm). `correct.WRIST_OFFSET_M`; **step 6 is now ON by default**.
  It took the deadlift horizontal acceleration correlation from 0.12–0.23 to
  0.43–0.64 and put all seven template-refereed benches above the flat-line null.
  B2's reason for asking survives intact: `d` is *not* identifiable from the
  video — fitting it against `vs_truth` is ill-conditioned because P3 is also a
  body-frame constant swept by the same rotating forearm, and the optimiser
  returns 21, 60, 64 and even 129 cm against a real 10–15 cm; C31 re-confirmed it
  by fitting `lever` on top of the tape and getting 108/74/4 degrees away from
  it. **Do not re-open the fit.** See C31 above.
- **Three still holds at different wrist postures, not two.** Five seconds of
  capture and no code. C28 proved that two holds can *never* separate the
  attitude tilt leak from the accelerometer bias: `R_open − R_close =
  R_open(I − Δ)`, and a relative rotation fixes its own axis, so the difference
  of two rotation matrices is rank ≤ 2 exactly. A third posture breaks the
  degeneracy. Where the existing two holds happen to differ by more than ~30°
  the observable part already recovers P4's table value of 0.0245 m/s², which is
  the first on-wrist measurement of the accelerometer bias — so this is a known
  quantity waiting on a known-cheap capture change.
- **Tape the sticker-circle diameter**, on each stickered plate, once. Both
  marker referees' absolute scale rests on `STICKER_RATIO = 0.858`, borrowed
  from the old three-sticker plate; C27 finds the video reading 4.6–9.3% below
  the reconstruction on the 8-sticker deadlifts and C32 showed the ratio cannot
  be recovered from the footage — every gradient-based rim measurement
  reproduces a bias `markers.py` already rejected. It goes into
  `bar_path(sticker_diameter_m=)`. **And say which physical plate carries the
  stickers on each bar**: `truth.STICKER_PLATE_DIAMETER_M` has no 2026-08-06
  entry, so bench falls through to 0.425 m and squat to 0.450 m by accident, and
  if one 425 mm plate moved between the two bars squat is 5.9% out.
- **Film a bench single.** ~~No capture exists.~~ **Filmed 2026-08-01 —
  `data_v2/video_only/bench_110x1_20260801.mov` — and it still cannot answer the
  question, because that session produced no IMU log.** C5's singleton rule
  ranks by concentric displacement and `bench_92.5x2`'s unrack moves the bar
  *further* than its reps, so a bench single is predicted to segment onto the
  unrack; the falsifier needs `segment.py` run against a watch capture, and the
  video alone cannot supply one. Worth noting the video says the prediction is
  plausible: `markers.bar_path` on that clip shows the unrack excursion reaching
  14 cm fore-aft against a press of a few. **Re-film it with the watch on.**
- **Film a plumb line once**, to put a number on lens distortion — the leading
  candidate for the scale error above.
- **Tape the lockout height.** Deadlift bar centre at lockout, once. It would
  turn `VERTICAL_ROM_M`'s deadlift ceiling from a bound into a measurement and
  let the video be calibrated against it rather than flagged by it.

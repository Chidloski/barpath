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

### C7 — the watch workout session, removed on measurement
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
track.** `vs_truth` refuses squat.

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
real mid-set gap above 1.45 and would be split. And the singleton rule claims a
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

### B6 — attack the acceleration error itself  ← splice rejected; blocked on B3
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

Bench and squat need none of this — no impact, and both a per-rep residual and
now a vertical closure at the sensor's noise floor. Their problem, if they have
one, is a different problem, and nothing external measures it yet.

Every attempt is measurable against `metrics.vs_truth`, which is the whole point
of having built it. `analysis/25_b6_bias_models.png`, `python run.py --bias`.


### B2 — step 6 implemented; the term is 3× smaller than we thought
`correct.apply_offset` works and step 6 is no longer a blocked stage. It is
**off by default** because `d` is unmeasured, and B2's main finding is that it
cannot be measured from what we have.

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
- **Re-shoot with a vertical reference in frame** — a metre rule against the
  rack, in shot for the whole clip. **Now the highest-value item here.** The
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
  so this is also what converts squat to truth with no code. Bench sits the
  plate against clutter; it is truth already (C8) but only from a hand-placed
  seed in `truth.SEEDS`, and a clear plate would let auto-seeding work and drop
  the ~4% scale uncertainty the hand-read radius carries. **One camera change
  fixes a defect on all three lifts.** Note what does NOT fix it: shrinking the
  template raises NCC and makes the track worse (ROM 60.5 → 74.1 cm). See
  `analysis/34`.
- **A sessionless capture with 30+ s of wrist-down.** C7 deleted the
  `HKWorkoutSession` after measuring that 100 Hz survives a dimmed frontmost app
  for **20 s**. Nothing tests longer, and a real set plus setup is longer. This
  is the falsifier for that decision and it has never been collected. If the
  rate drops, every capture taken since C7 is suspect. See `watch/README.md`.
- **Tape the wrist-to-bar offset `d`.** Watch centre to bar centre, in watch
  axes, once. B2 showed `d` is *not* identifiable from the video — fitting it
  against `vs_truth` is ill-conditioned because P3 is also a body-frame constant
  swept by the same rotating forearm, and the optimiser returns 21, 60, 64 and
  even 129 cm against a real 10–15 cm. Step 6 is implemented and off by default
  purely for want of this number.
- **Film a bench single.** Newly worth doing: C5's singleton rule ranks by
  displacement, and `bench_92.5x2`'s unrack moves the bar *further* than its
  reps, so a bench single is predicted to segment onto the unrack. No capture
  exists to confirm or refute it. One set of one is the cheapest falsifier in
  this list.
- **Film a plumb line once**, to put a number on lens distortion — the leading
  candidate for the scale error above.
- **Tape the lockout height.** Deadlift bar centre at lockout, once. It would
  turn `VERTICAL_ROM_M`'s deadlift ceiling from a bound into a measurement and
  let the video be calibrated against it rather than flagged by it.

# H1 — why the deadlift's horizontal deviations are large (2026-08-15)

Owner's task: a deep dive on the *reasons* behind the large horizontal
deviations in the reconstructed deadlift path. Measurement only — **no file
under `src/` was written.** Four fixes were built and scored; none is proposed
for shipping as it stands, and the reasons are recorded below rather than the
verdicts alone.

Figures: `analysis/57_deadlift_horizontal_origin.png`,
`analysis/58_deadlift_display_axis.png`,
`analysis/59_deadlift_horizontal_fixes.png`.

Everything here is measured with **step 6 ON** (the shipping default), against
the `vtrack` referee on the cached `data_v2/tracked/` paths, scored through
`metrics.vs_truth` — i.e. the number the ~1 cm spec is about.

## The baseline, re-measured

    capture              h rms   v rms    null   beats_null
    deadlift_150x4_1      2.66    4.14    2.15      0.81
    deadlift_160x4_2      3.98    4.90    1.50      0.38
    deadlift_160x6_1      7.52    3.54    1.54      0.20
    deadlift_160x6_2      4.40    3.69    1.54      0.35
    deadlift_170x4_3      5.54   12.14    1.39      0.25
    deadlift_185x3       10.72    1.69    1.55      0.14

All six lose to a flat vertical line. **The deadlift null is the smallest in
the corpus (1.39–1.55 cm against bench's 3.2–4.1)** — the bar genuinely barely
moves fore-aft, so there is very little to get right and the reconstruction
adds 3–11 cm of fiction on top of it. That asymmetry, not a worse sensor, is
half of why deadlift reads worst.

## The mechanism

**The invented fore-aft is a constant-acceleration parabola per rep whose size
GROWS through the set.** Per-rep world-plane excursion runs 5.2 → 34.9 cm on
`deadlift_160x6_1` while the video's own stays flat at 4.2–5.4 cm. Expressed as
the tilt that would leak that much gravity, it is **0.10° to 0.94°**, and it
rises monotonically with rep index on 4 of 6 captures.

Every stage after acceleration — integration, the per-rep detrend, projection
onto a fixed axis — is **linear** in the acceleration, so a candidate error
field can be pushed through the real pipeline and compared column-wise against
the measured error. Fitted with 2 dof each and scored **leave-one-rep-out**:

    capture            world const   kinematic ramp   const tilt   GROWING tilt
    deadlift_150x4_1      -0.54          -0.65          -1.06         -1.58
    deadlift_160x4_2       0.07           0.44           0.05          0.45
    deadlift_160x6_1       0.62           0.90           0.59          0.88
    deadlift_160x6_2       0.68           0.91           0.68          0.91
    deadlift_170x4_3       0.14           0.38          -1.06         -1.06
    deadlift_185x3         0.95           0.86           0.94          0.84

On the three captures where the error is largest and the sync is sound, a
growing horizontal acceleration explains **84–91% of it out of sample**.

**The falsification test passes, and it is the reason to believe this.** A tilt
error leaks `g·sinθ` into horizontal and only `g·(1−cosθ)` into vertical —
first order against second. So the same fitted parameters must explain the
horizontal and must *fail* on the vertical. Measured: horizontal LOO 0.84–0.91,
vertical LOO **−1.63 to −0.02**. The asymmetry a tilt predicts is exactly the
asymmetry that is there. Panel D of `analysis/57`.

### Two things it is NOT, both measured

**It is not a gyro bias of the watch.** The fitted rate is 0.006–0.034 deg/s
(median ~0.016), which is a striking match to `calibrate.anchor_tilt`'s
independently measured ~0.014 deg/s and sits 10–60× *below* the pre-set pause
estimate's own standard error — so B1's rejection of the pause bias stands and
this is invisible to it. But converted into **watch axes**, where a body-fixed
sensor bias would have to agree, the six fitted directions scatter **27–149°
apart** (random 3-D vectors average ~60°). It is fixed within a capture and
random across them. A single body-fixed gyro bias is ruled out.

**It is not localised at the floor impact.** A staircase stepping at each
impact fits no better than a smooth ramp — and cannot, because at 3–6 evenly
spaced reps the two bases correlate **0.86–0.97**. The distinction this project
has wanted to draw between "drift" and "impact damage" is *not identifiable on
sets this short*. That is a fact about the corpus, not a result.

### What the ZUPT-shaped fix would have assumed, and why it fails

The obvious correction — anchor the tilt where the bar rests on the floor — was
measured before it was built. The world-frame horizontal residual at
`segment.rest_instants` is **0.10–3.59 m/s²**, one to two orders above the
0.03–0.16 m/s² being estimated. A wrist under a loaded bar is not still enough
to level against. Same shape as B1's pause and B7's anchor; do not re-propose
without a genuinely still hold.

## The second mechanism, and it is the bigger lever

**Step 8 picks the display axis by maximum variance. On a deadlift the variance
IS the invented drift, so the pipeline displays the axis along which it is most
wrong.** Swept over every azimuth and scored with `vs_truth`'s own statistic:

    capture            shipping   best   worst   % of axes better   angle to best
    deadlift_150x4_1      2.66     2.29    3.90        22%              60°
    deadlift_160x4_2      3.98     2.28    4.19        72%              78°
    deadlift_160x6_1      7.52     1.19    7.53        97%              89°
    deadlift_160x6_2      4.40     1.03    4.79        74%              72°
    deadlift_170x4_3      5.54     3.92    7.78        53%              35°
    deadlift_185x3       10.72     2.32   11.19        82%              76°

On four of six, step 8 chooses an axis worse than 72–97% of every axis
available, landing 60–89° — near perpendicular — from the best one. **On the
best axis two captures beat the null** (1.19 and 1.03 against 1.54), which no
deadlift has ever done. `analysis/58` draws the sweep; the shipping axis sits
on or beside the *peak* of the error curve on four panels.

This is not a bug in `principal_axis`, which does what it says. It is that the
rule "maximum variance is the display axis" is only sound while the
reconstruction's variance is the bar's, and on deadlift it is not.

## H2 — the axis is not the fore-aft axis, on any lift (owner's question, 2026-08-16)

The owner asked whether max-variance is picking the *bias* rather than fore-aft,
and whether that reaches squat and bench as well. Both yes.
`analysis/60_display_axis_is_the_drift.png`.

**Method.** The video gives a 1-D fore-aft signal. The world azimuth whose
projection best *correlates* with it is the camera's fore-aft expressed in world
axes — correlation rather than rms, so the estimate of DIRECTION is not
confounded by an amplitude error.

    lift        axis error vs the video-identified fore-aft
    deadlift    45  46  52  77  78  84       median 64°
    bench       10  20  66  84               median 43°
    squat       32  46  49                   median 46°

**11 of 13 captures are outside the 20° `project.AXIS_TOLERANCE_DEG` the module
declares for itself**, and six are beyond 60° — nearer perpendicular to fore-aft
than aligned with it. Only the two `bench_92.5x6` captures are inside it, and
they are the two best-scoring captures in the corpus. This is not a deadlift
problem; deadlift is where it is worst.

**The bias owns the axis, measured directly.** Split each rep's horizontal path
into the per-rep constant-acceleration parabola and the residual, and take the
principal axis of each. Step 8's axis sits **4° from the drift-only axis**
(median over 13) and 13° from the residual's. The drift is choosing the display
direction.

**But removing the drift does not fix it, and this is the part that matters.**
The residual's axis is **50°** from the video direction against the drift axis's
**47°** — no better. *The true fore-aft is not the dominant horizontal variance
on any of the thirteen captures*, so no re-weighting of that covariance can
recover it. Step 8's premise — fore-aft is the max-variance horizontal direction
— fails whenever the horizontal error exceeds the horizontal signal, which is
every capture in this corpus.

### Why no confidence gate can catch it

**The drift-owned axis is BETTER conditioned than a bar-owned one, not worse.**
Bootstrapping the axis over reps — the test `min_ratio` already assumes, since
it takes N = n_reps — gives a 68% spread of **1–10° on every capture**, including
`deadlift_160x6_1` at **2° of spread on an axis 84° wrong**. And the eigenvalue
ratio that `confidence` gates on carries no information about the error:
Spearman rho **+0.03**, with the best-conditioned axis in the corpus (ratio 26.9)
also the most wrong.

The mechanism is that the drift is smooth, common-mode and grows monotonically,
so **every rep votes for the same wrong direction**. Precision without accuracy.
Two candidate additional gates were built and both fail: bootstrap spread > 20°
refuses 0 of the 6 captures the pipeline currently calls confident, and a
per-rep growth test refuses one squat while keeping `deadlift_185x3` at 77°.

This generalises C31's `_trial_merit` result rather than repeating it: there the
merit rewarded RIGIDITY and gym furniture was maximally rigid; here every
conditioning test rewards CONSISTENCY and the drift is maximally consistent.
**A conditioning statistic cannot referee a choice the nuisance term satisfies
better than the signal.**

`project.confidence`'s docstring half-anticipated this — "an error at rep
frequency (P3) lands in the covariance as variance and makes the ratio look
BETTER" — but it is stated there as a limit on what confidence *proves*, and the
measurement above says something stronger: the ratio is not weak evidence about
the axis, it is **no evidence at all**. The module docstring's "the failure mode
is self-limiting … the case where the estimator fails is the case where the
answer does not matter" is **falsified**: the estimator fails hardest where the
excursion is largest and the ratio is highest.

### What could be done instead — measured, not proposed

An axis estimated from the *rotation* rather than the position is the only
family that is structurally immune, and it answers the module docstring's stated
objection to attitude-derived heading (that it "needs a per-lift constant … a
lookup table to extend for every new exercise") — neither of these needs one,
because each identifies its own reference direction from the signal.

  * **E1 — the forearm swings in the sagittal plane**, so the body-frame gyro's
    dominant direction is the mediolateral axis; fore-aft is perpendicular to it
    in the horizontal plane. Median axis error 49° → 51°, h 2.97 → 3.43. **No
    better.**
  * **E2 — a barbell stays LEVEL**, so the body-frame direction whose world
    image stays closest to horizontal is the bar's long axis. Median axis error
    49° → 45° and h 2.97 → 2.83 over the corpus; on **deadlift** it is a real
    move, 64° → 36° and 4.97 → 4.25 cm, and it costs bench (2.01 → 2.88).
    Promising and not shippable as it stands.

**Two things bound all of the above and are the honest caveat.** The
video-identified direction is itself uncertain: estimated from odd reps against
even reps it moves by a median **38°**, so no single capture's angle should be
quoted alone. What is robust is the aggregate (11 of 13 outside tolerance), the
4° drift alignment, and the bootstrap/ratio results, none of which depend on the
reference direction being sharp. Against that, **adjacent sets of the same lift
agree far better than split-half does** — `bench_92.5x6_1` vs `_2` to **1°**,
the paused squats to 9–25°, `deadlift_160x6_1` vs `_2` to 17° — so the
full-capture estimate is worth more like 10–20°, and the fore-aft direction is
reproducible between neighbouring sets. That is the evidence for the one route
this measurement genuinely supports: **a per-session, per-lift axis, locked once
and reused**, which `project.py` currently defers as "a later step, not a now
step".

## READ THIS BEFORE H3 AND H4: the rotation axis is WRONG ON BENCH (H5, 2026-08-16)

The owner challenged H3/H4 on geometry and was right. On bench the watch's +x
(crown, toward the hand) sits at **+75° elevation**, so a world-horizontal
direction must lie in the watch's y–z plane — both estimates do — and the 68°
between them is therefore **a pure rotation about the forearm axis: pronation**.

Anatomy decides it. The bar runs across the wrist (±y), so fore-aft must be near
the SCREEN NORMAL (±z). The variance axis is 13–26° off z on three of four
benches; E3 is 31–44° off on the other side. **E3 is the wrong estimator on
bench**, and H3's account — that bench regressed because the variance axis
"already worked" — had the cause backwards. E3 has least to work with there:
14–17°/rep of swept attitude against 21–26° elsewhere, and a bench forearm stays
vertical while the arm extends, so the residual wrist rotation is not a hinge.

**H4's reproducibility result stands and its reading does not.** The rotation
axis really does reproduce to 1–13° across same-session sets — and on bench it
is reproducibly *wrong*, because a fixed pronation offset is exactly that
reproducible. Reproducibility was never accuracy.

**What replaces it.** Fore-aft in WATCH coordinates is a per-lift anatomical
quantity — **stable to a tolerance, not a constant** (H6). Measured by scale:
0.9–5° rep to rep, 4–19° peak-to-peak within a rep, and **13–17° between SETS**
on bench and squat, against `AXIS_TOLERANCE_DEG`'s 20°. **Deadlift scatters by
51°**, which is the drift-owned axis rather than the geometry.

The mechanism is a nearly rigid chain — watch → strap → wrist → hand → bar,
with a loaded grip locking the wrist — so although the watch's absolute attitude
swings 14–26° per rep, the residual wrist articulation relative to the bar is a
few degrees, and that residual is what a body-frame direction sees. That is the video-free drift detector H2 said was
missing. Leave-one-out across a lift's other captures: median 2.97 → 2.74 cm,
8 of 13 improved, bench unchanged, `deadlift_160x6_1` 7.52 → 1.76 and
`185x3` 10.72 → 3.01. The deadlift half rests on a consensus pooled from axes
that scatter 51°, so read bench and squat as the sound part. Full record in
TASKS.md H5.

## H4 note: the referee is also noisy (2026-08-16)

H2 and H3 score every axis against a **video-identified** fore-aft direction.
Asked whether each estimator reproduces across sets of the same lift in the same
session — where the lifter faces one way, so the answer must be the same — the
rotation axis agrees to **1–13°** and the video-identified direction to
**1–57°** (medians 2/10/1/13/2 against 50/33/1/57/17).

**The rotation axis is 3–25× more reproducible than the reference it was
measured against**, so H3's "41° median error" is substantially the referee's
noise and every axis-error number below is pessimistic about rotation by an
unknown amount. This does not make the rotation axis correct — a fixed
pronation offset would be exactly this reproducible — it makes it PRECISE, and
it means this corpus has no referee sharp enough to price its accuracy.

## H3 — how to get the axis from rotation, built and measured (2026-08-16)

**The premise, and it is one fact about all three lifts.** The wrist swings
about a MEDIOLATERAL axis — the elbow/shoulder hinge, which is parallel to the
bar. That axis is horizontal and fixed in the world for as long as the lifter
faces one way, so **fore-aft is perpendicular to it in the horizontal plane**.
Nothing here is a per-lift constant; the axis is identified from the signal on
every capture, which is what `project.py`'s objection to attitude-derived
heading asks for ("a lookup table to extend for every new exercise").

**Why rotation and not position.** Attitude is never double-integrated. Core
Motion's is good to 0.05–0.14° at the anchors and drifts 0.35–1.49° across a
whole set, so an axis read off it **cannot be captured by the position drift**
that owns the variance-based axis. That is the whole point: it does not share
the failure mode.

**The estimator (E3).** Per rep, over the rep window:

    v(t) = rotvec( R(t) · R(t_start)⁻¹ )        world axes, corrected attitude

pooled over every sample and every rep, weighted by |v|; take the principal
eigenvector of that weighted covariance as the bar axis, project it into the
horizontal plane, rotate 90°.

`v(t)` is the net rotation *so far* within the rep, not the instantaneous rate.
That is the one thing that matters and it is why **E1 (raw body-frame gyro)
failed**: the deadlift wrist sweeps 193–311° per rep against a net swing of
~22°, so ~90% of the gyro signal is strap ringing going back and forth. Ringing
cancels in a net-rotation-so-far and the anatomical swing accumulates.

    lift        axis error  ship -> E3      h rms  ship -> E3
    deadlift        64° -> 35°               4.97 -> 3.85 cm
    bench           43° -> 41°               2.01 -> 2.81 cm   WORSE
    squat           46° -> 59°               2.65 -> 2.58 cm
    all 13          49° -> 41°               2.97 -> 2.81 cm   beats-null 6 -> 7

**One capture settles that the idea is sound.** `deadlift_160x6_2` goes from an
axis 78° wrong to **9° wrong**, and its horizontal from 4.40 to **1.30 cm** —
under its own null of 1.54 and within 0.3 cm of the best axis that exists (1.03).
`deadlift_160x6_1` goes 84° → 29° and 7.52 → 4.02.

**And it is not shippable, for a reason worth stating plainly.** On bench the
position axis already works — those captures beat the null 3.05× and 2.55× — so
E3 replaces a good estimate with a mediocre one, taking the two best captures in
the corpus from 20°/10° of error to 50°/52°. It is a deadlift result, not a
corpus result.

**Two premise checks, one reassuring and one a lead.** Reps agree on the swing
axis to **7°** (median), which is real independent evidence rather than the
drift's false consistency. But the swing axis comes out **15° off horizontal**
(median; 26–32° on deadlift), so the hinge premise is approximate.

**The obvious refinement was built and does not pay.** The contaminant should be
PRONATION about the forearm's long axis — on a deadlift the forearm hangs
vertical, so pronation is rotation about the world vertical and lands entirely
in the horizontal projection. Identifying the forearm axis with no lookup table
(the body direction whose world image is most consistently vertical) and
projecting it out gives deadlift h 3.85 → 3.61 cm but axis error 35° → 39°, and
the corpus is unchanged. Recorded so it is not re-proposed on the reasoning.

**Agreement as the confidence signal step 8 lacks — directionally real, not yet
usable.** Rotation and position are independent estimates that do not share a
failure mode, so their disagreement should predict when the shipping axis is
wrong. It does, weakly: Spearman rho **+0.26** against the eigenvalue ratio's
**+0.03**. Captures where the two agree within 30° have a median 46° axis error
against 71° for those that disagree. **But it misfires exactly where it must
not**: the two benches whose shipping axis is *correct* (10° and 20°) are the
ones where the estimators disagree most (63° and 70°). As a gate it would refuse
the two captures that work.

## H4 — the anatomical cone, measured (2026-08-16)

Pronation is bounded by the wrist, so the attitude-derived axis bounds an arc
within which fore-aft must lie. For a 2×2 covariance the variance is sinusoidal
in azimuth with one maximum, so **"max variance inside the cone" is exactly
"clamp the PCA axis to the nearest cone edge"** — and a no-op when the PCA axis
is already admissible, which is the property that would let it ship.

    delta      0    10    20    30    40    50    60    90(ships)
    all       2.81  2.70  2.66  2.66  2.97  2.97  2.97  2.97
    deadlift  3.85  4.46  4.46  4.35  4.13  4.00  4.27  4.97
    bench     2.81  2.56  2.35  2.23  2.23  2.03  2.01  2.01

The interior optimum in the corpus median (2.97 → 2.66 at 20–30°) **should not
be read**, for the reason C19 fixed in advance. It is a trade: deadlift is best
at delta = 0 and bench unclamped, the middle satisfies neither, and per capture
it is mixed — `bench_spoto_95x5_2` 2.41 → 4.34 against `deadlift_160x6_2`
4.40 → 2.06.

**As a refusal instead of a clamp** — on the precedent of `confidence`'s 20 cm
ceiling, which only ever refuses — precision is 0.62–0.67 across delta 20–60°.
**Step 8's existing gate does better**: 6 of 13 called confident of which 1
loses to the null, 7 refused of which 6 do. It adds nothing.

**A qualification H2 needs.** H2's "no confidence gate can catch it" is true of
the eigenvalue RATIO and of *axis error*. It is not true of `confidence` as a
whole — the 20 cm excursion ceiling separates `beats_null` at 0.86 precision on
refusals and 0.83 on those it keeps. The ratio carries no information; the
excursion ceiling is doing real work.

**Why the cone underperforms, and it is not the bound's fault.** The deviation
between the two axes does not track correctness where it matters: the two
benches whose variance axis is RIGHT sit at 62° and 70° of deviation, while
`deadlift_150x4_1`, which loses to the null, sits at 3°. To bite, the bound must
be ~15–20° wide, and at that width it fires on the captures that already work.

**What would make it work**: a **session-level** rotation axis. It reproduces to
1–13° across sets of one lift, so pooling a session gives a heading far tighter
than any single capture's — the same route H2 reached from the other side. Still
missing is a referee sharp enough to price a fixed pronation offset.

## H7 — what all of this buys the pipeline (2026-08-16)

Three candidates, scored through `vs_truth` on the thirteen scoreable captures.
Full detail in TASKS.md H7. **`src/` is still unwritten; these are proposals.**

  1. **A confidence test that can see a drift-owned axis** — a capture's display
     axis in WATCH coordinates against the consensus of its lift's other sets,
     leave-one-out, no video. At 20–25° it refuses 7 and all 7 lose to the null,
     keeps 6 and all 6 beat it; `confidence` today makes two errors on the same
     corpus. **But on this corpus "loses to the null" and "is a deadlift" are
     nearly the same set**, so most of that score is lift identity. Exactly one
     non-trivial case exists (`bench_spoto_95x5_1`, a losing bench, correctly
     refused) and one data point is not a validation.
  2. **The per-lift display axis (`AX`)** — deadlift 4.97 → 3.40 cm
     (`160x6_1` 7.52 → 1.76, `185x3` 10.72 → 3.01), bench 2.01 → 2.06 and squat
     2.65 → 2.63, i.e. **unchanged where the pipeline already works**. This is
     `project.py`'s own deferred "per-exercise axis by averaging over past sets".
  3. **`V2` and `AX` COMPOSE** — deadlift 4.97 → 2.77, corpus 2.97 → 2.22, 10 of
     13. Different stages (path vs step 8), unlike C29's impact correction and
     `d` which both targeted the same instant. The cost is bench 2.01 → 2.15,
     and `bench_92.5x6_1` 1.23 → 2.20, which is `V2`'s doing.

**The negative that keeps `V2` honest:** if it removed drift it should tighten
the body-frame axis consensus. Bench goes 17° → 12°; **deadlift stays 51° → 52°**
— the very lift its h_rms gain comes from. `V2` improves the comparison without
restoring the geometry. `AX` is the better-founded half.

**And the limit on all three:** the referee's own fore-aft error at lockout is a
median 3.0 cm, so only the large deadlift movements clear it. Every bench and
squat number above is inside the referee's resolution.

## The four fixes, measured

    capture              ship     V2     V3     R4    best   null
    deadlift_150x4_1     2.66   2.43   2.60   3.18   2.29   2.15
    deadlift_160x4_2     3.98   2.96   2.34   2.29   2.28   1.50
    deadlift_160x6_1     7.52   3.44   1.63   1.50   1.19   1.54
    deadlift_160x6_2     4.40   2.82   1.52   1.11   1.03   1.54
    deadlift_170x4_3     5.54   4.95   4.88   3.92   3.92   1.39
    deadlift_185x3      10.72  11.09   2.01   2.98   2.38   1.55
    bench+squat (n=7, medians)
                         2.41   2.04   3.52   3.57   1.61   3.67

  * **V2 — remove the GROWTH of the per-rep curvature** (regress the per-rep
    parabola coefficient on rep index, subtract `c_k − c_0`, keep the first
    rep's real curvature). Deadlift median **4.97 → 3.20**, bench+squat
    **2.41 → 2.04**, beats-null 6/13 → 7/13, improving **10 of 13 captures**.
    The only trial that helps both groups, because it is a near no-op wherever
    the curvature does not grow. Weaknesses, stated: it privileges rep 0
    arbitrarily, it leaves rep 0's own invented curvature in, and it **fails on
    the worst capture** (`185x3`, 10.72 → 11.09), whose drift does not grow.
  * **V3 — remove the per-rep curvature entirely** (D1's `parabola_detrend`).
    Best on deadlift, 4.97 → 2.17. Destroys bench and squat, 2.41 → 3.52 and
    beats-null 6/7 → 5/7. Already rejected by D1; this reproduces the rejection
    and adds the reason — on bench and squat the per-rep curvature *is* the real
    J-curve.
  * **R4 — take the display axis perpendicular to the fitted drift.** Deadlift
    median **4.97 → 2.64**, improving 5 of 6, within 0.36 cm of the oracle
    axis, and it takes two deadlifts under the null. Uses no video. **It
    regresses bench and squat** (2.41 → 3.57, beats-null 6/7 → 5/7) for the
    same reason V3 does.
  * **A fitted 2-dof world tilt ramp**, applied to the attitude before
    `to_world`. Deadlift median 4.97 → 3.55, improving 4 of 6 (7.52 → 2.20,
    4.40 → 1.78, 10.72 → 5.00), **and it leaves vertical untouched to 0.06 cm**,
    which is the physics behaving as predicted end to end. It is an **oracle** —
    fitted against the video it is scored on — and the direction is not a watch
    property, so it bounds what this family can buy rather than being shippable.
    Note the 3-dof version is a trap: gravity cannot observe yaw, the fit puts
    up to 1.13 deg/s in the unobservable direction, and the error goes to
    **318 cm**.

**No gate was found for R4 or V3.** The obvious one — the owner's IMPACT vs
SMOOTH growth statistic — does not separate: deadlift runs 1.2–35.0 %/rep and
bench+squat 1.3–22.8 %/rep, overlapping completely, and the *worst* deadlift
(`185x3`, 1.2 %/rep) sits at the bottom of the deadlift range while a squat sits
at 22.8. Gating on the lift itself is available and legitimate — the pipeline is
already lift-conditioned in `WRIST_OFFSET_M`, `VERTICAL_ROM_M` and the sync
route — but that is a decision, not a measurement, and it is left to the owner.

## The floor under all of it

**The shipping referee reports 2.0–7.9 cm of fore-aft while the bar is STILL at
lockout** (median 3.02 cm over ten dwells, 90th percentile 4.98). Held against
the thighs at lockout the bar is not moving, so that motion is the tracker's.

C12 found this on the v1 template tracker and F1 deleted that tracker; this is
the first time `src/vtrack/` has been checked at lockout, and **it has the same
defect**. The consequence is blunt: every fix above lands at 1.1–3.2 cm, at or
inside the referee's own resolution, so *the ranking between them is not
established by this corpus*. It also means `deadlift_150x4_1`'s 2.66 cm is not
measurably wrong at all.

`170x4_3` is separately unscoreable: its clock fits 22.8% drift with a 216 ms
residual, against ~0.4% and ~9 ms everywhere else, and no acceleration model
fits it (LOO ≤ 0.41 on every family). Its "error" is partly a misaligned clock.

## What would move this

1. **A capture with a genuinely still hold under load**, long enough to level
   the attitude against — the missing anchor for every correction in this
   family, and the same thing `calibrate.gyro_bias` has wanted since B1.
2. **Footage that tracks at lockout.** Until the referee resolves better than
   3 cm, deadlift horizontal cannot be validated to the spec it is written to,
   and four of the trials above cannot be ranked.
3. **Step 8's rule is the cheapest real lever** and it is not blocked on either
   of those. The measurement says the information is in the reconstruction and
   the projection throws it away.

"""
Steps 6-7 — wrist-to-bar offset, and the per-rep detrend.

This module was reserved for the owner until 2026-07-28. It is not any more —
every file is collaborative now. What the lockout was protecting survived it:
this is where the physics lives, so a change here explains the mechanism
alongside the diff and names what would falsify it. See CLAUDE.md, "Learning
contract".

Both steps here rest on a claim about the SHAPE of the error, and real captures
have since contradicted both claims. Read the caveats before trusting either.

Step 6 — offset
---------------
    p_bar(t) = p_watch(t) - R(t) . d

The watch is not on the bar. As the forearm rotates through a press, the
watch swings on an arc about the grip point. With the watch about 14 cm from
the bar and roughly 16 degrees of forearm rotation, that arc is around 3.6 cm
— a quarter to a third of a bench J-curve's entire horizontal excursion.

The shape is what makes it dangerous rather than merely large. It is zero at
lockout and maximum at the touch, so the detrend below sees no ramp to
remove. It is nearly identical every rep, so overlaying reps does not reveal
it either. Uncorrected, it renders as a consistent, plausible, entirely
fictitious J-curve.

The correction is nearly free because R(t) is already computed and is the
best-conditioned quantity in the system. d is one vector, roughly 14 cm along
the forearm axis in body coordinates.

**d cannot be recovered from the video we have, and B2 established that by
trying.** Fitting it against `metrics.vs_truth` over all three deadlifts is
ill-conditioned: the joint optimum sits at |d| = 31 cm, and per-capture fits
give 21.2, 63.6 and 60.3 cm. A wrist is 10-15 cm from the bar, so those are not
lever arms — they are the optimiser absorbing P3, which is also a body-frame
constant swept by the same rotating forearm and therefore nearly degenerate
with d. Leave-one-out settles it: one fold returns |d| = 129 cm and makes the
held-out capture worse, 5.1 -> 16.2 cm.

So d wants a tape measure, not an optimiser: watch centre to bar centre, in
watch axes, once. Thirty seconds, and the same class of fix as measuring the
plates for truth.PLATE_DIAMETER_M — which was done on 2026-07-30 and took about
that long.

**The owner did it on 2026-08-06, and `WRIST_OFFSET_M` below is the tape.**
That paragraph used to end "until then it stays None"; the reason it stayed
None is gone. **And the DEFAULT has moved with it: step 6 is ON**
(`pipeline.run(wrist_offset="auto")`, 70b2a63) — pass None for the old
behaviour. *This paragraph said "the DEFAULT has not moved" for about an hour,
between C31b recording the constant and the owner's call to ship it; C33
corrected it on 2026-08-06.* See the constant's comment block and `pipeline.run`
for what it costs as well as what it buys.

Note the first paragraph above is **not** superseded by the tape. `d` still
cannot be recovered from the video; it can only be measured with a ruler. C31
re-confirmed that from the other side by fitting `lever` on top of the tape and
landing 108/74/4 degrees away from it.

**How big is it really? Smaller than this project has been claiming.** B2
measured it. The rotation premise above is right — the watch turns 18-22
degrees through a rep on all three lifts, so the ~16 degrees assumed here is
sound. What was wrong is the arc it produces at the output.

At |d| = 14 cm, the WITHIN-REP horizontal variation of R(t).d that survives
step 7 is, swept over every possible direction of d:

    bench      0.0 - 4.2 cm   (1.2 cm at a typical direction)
    squat      0.0 - 4.4 cm   (1.3 cm)
    deadlift   0.4 - 6.4 cm   (2.4 cm)

TASKS.md and pipeline.py said **8-13 cm on every lift** and called this the
largest unmodelled term in the system. It is not; that figure is roughly 3x
too big and it had been setting priorities. Two reasons the intuition
overshot: only the component of the arc perpendicular to the rotation axis
sweeps at all, and step 7 runs afterwards and removes the linear part of
whatever is left.

**Deadlift is still not exempt**, which is the one part of the old text that
survives — it is the LARGEST of the three, not the one you can skip. The
forearm does not hang still through a pull.

What cannot be modelled from one wrist sensor is wrist extension under load
— the hand laying back relative to the forearm. That is the accuracy floor
on bench and the reason bench paths stay qualitative.


Step 7 — per-rep detrend
------------------------
For each rep, subtract a straight line in position, per axis, from the start
index to the end index.

The original argument: the dominant errors are smooth, slowly varying and
monotonic, while the true motion is periodic and returns to its origin, so
subtracting a line removes almost all of the former and leaves the latter's
SHAPE untouched — and shape is where the anomaly lives.

**The premise is false, and this is P3.** The dominant error is not monotonic.
Accelerometer bias is fixed in the BODY frame and the forearm rotates through
the rep, so projected into the world frame it varies at REP FREQUENCY — the one
shape a per-rep straight line cannot tell apart from real motion. See
calibrate.accel_bias, which says the same thing from the other end. The
measurement: band-passed IMU vertical correlates -0.82 with the video-tracked
bar, with 145 cm of in-band error against a 69 cm signal, and it is already
present at the ACCELERATION stage (-0.16), so it is not something integration
or filtering introduced. The claim that the residual is "the within-rep bow,
around 1 cm, which is the spec" came from synthetic data, which injected a
constant world-frame bias — the assumption in question. Measured against video,
the horizontal error after this stage is 5.1-15.4 cm rms per rep.

The closure constraint is also only true VERTICALLY. Horizontally the owner
confirms the deadlift bar does not land where it was pulled from, and A3 puts a
number on it: the tracked bar misses closing by 1.9-4.3 cm horizontally, so
forcing each rep to close destroys that much real signal.

**And yet it must stay, which B7 established the hard way.** Close vertical only
and the horizontal error goes to 495 / 522 / 337 cm — the false constraint is
carrying metres. B7's floor-impact anchor was built to replace it and lost;
`analysis/22` has the ablation. So this assumption is wrong and load-bearing at
the same time, and B3 is now "find a replacement", not "delete it".

**But do not expect B3 to fix P2.** metrics.vs_truth reports the error with the
closure applied to the video as well, and it moves the number by only 0.2-0.9
cm against a 5-15 cm total. This stage is doing something wrong and worth
fixing; it is not where the horizontal failure lives. Most of the error is
already in the acceleration that reaches the integrator.

**C19 (2026-08-02) put a ceiling on this stage, and it splits by lift.** An
oracle over the basis — the best line and the best line-plus-quadratic per rep,
fitted against the video, so it bounds every estimator rather than being one —
gives a median over the ten scoreable captures of 2.72 cm shipping, 1.04 for
the best line, 0.33 for the best quadratic, against a null of 2.85. So there is
~1.7 cm of headroom in the LINEAR family alone and today's endpoint line is not
the best line. But on bench the best quadratic reaches 0.25-0.55 cm, inside
spec, while on deadlift the best LINE (3.64 / 3.78 / 4.89) loses to the null
(3.55 / 3.23 / 1.96) on all three. **No per-rep polynomial detrend can bring
deadlift near spec, whoever writes the estimator.** A detrend improvement is a
bench result. `python run.py --b3oracle`, `analysis/38`, TASKS.md B3.

Kalman filters, factor graphs, batch smoothers and spline fits were once
rejected here by reference to a non-goals table whose evidence was synthetic;
that table was deleted on 2026-07-28 and the file holding it on 2026-08-23.
Nothing in this file forbids a solver any more — but see TASKS.md B6 before building one: an oracle fitting
constant gyro AND accel bias directly against the measured error recovers only
~30% of it, so constant-bias estimation of any kind is capped well short of
1 cm.

Because every rep closes individually, cumulative drift across the set is
already gone. Do not additionally zero the net horizontal across the set;
it is redundant.


State — what is implemented and what is not
------------------------------------------

apply_offset(position, quat, d) -> (N, 3)
    Implemented (B2). Off by default: `d` is unmeasured, and B2 showed it
    cannot be fitted from the video. Supply a tape-measured `d` to
    `pipeline.run(wrist_offset=...)` to switch it on.

detrend_rep(position, start, stop, t, axes=(0,1,2), edge=1) -> (M, 3)
    Line subtracted so the rep starts and ends at the same point. `edge`
    medians that many samples at each end; it defaults to 1, the original
    behaviour, because larger values measure as worth nothing. See its
    docstring — B3's endpoint-sensitivity fix was tried and did not pay.

detrend_set(position, bounds, t, axes=(0,1,2)) -> list of (M, 3) arrays
    One detrended path per rep, each translated so its start sits at the
    common origin. Alignment is by START POINT ONLY. Do not align whole
    paths — between-rep divergence is the signal, not the error.


How to check it
---------------
Against real captures, via metrics.vs_truth on a deadlift. That is the whole
point of A3: it reports the error both before and after this closure is
applied, so the cost of the constraint is visible rather than assumed.

The check this docstring used to recommend — a synthetic set with injected
bias, expecting each rep to match synth.pos_true to under 1 cm horizontally —
is exactly the gate that certified this stage as working while it failed in the
gym by two orders of magnitude. It passed because synth.py injects a constant
world-frame bias, which is the shape a per-rep line removes perfectly, and the
real one is not that shape. Do not restore it.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


# The tape, measured by the owner on 2026-08-06. Watch face centre to bar
# centre, in WATCH body axes: +x toward the crown, +z out through the display.
#
#   squat            5 cm toward the crown, 4 cm UP OUT of the case    |d| = 6.4
#   bench, deadlift  9 cm toward the crown, 3 cm DOWN INTO the case    |d| = 9.5
#
# **The sign is the thing to get right and the easy thing to get wrong.**
# `apply_offset` computes p_bar = p_watch - R(t).d, so ITS d points BAR -> WATCH
# and is the negative of what a tape measured from the watch reads. Hence the
# leading minus on the crown component: the bar is 9 cm toward the crown from
# the watch, so the watch is 9 cm anti-crown from the bar.
#
# Corroborated rather than assumed, because a sign error here is invisible —
# it produces a plausible curve of the right size pointing the wrong way.
# Sweeping d's direction over the sphere at the measured magnitude and scoring
# by C30's acceleration correlation, the literal tape value lands within
# 0.02-0.03 of the best achievable correlation on all three data_v2 deadlifts
# (C31, 2026-08-06). It was NOT fitted; the sweep only checks it.
#
# Squat's is the odd one and the direction is the reason: the bar is on the
# lifter's back and the wrists are under it palm-forward, so the display faces
# roughly the same way the bar sits rather than away from it.
#
# **THIS IS THE SHIPPING DEFAULT AS OF 70b2a63.** `pipeline.run(wrist_offset=)`
# defaults to "auto", which looks this table up by lift and applies it; pass
# None for the old behaviour. The owner's call, and the reason is geometric
# rather than metric: this project reconstructs the BAR path from a sensor on
# the WRIST, and R(t).d is the only term between them, so omitting a measured
# term does not make the answer more conservative — it makes it an answer to a
# different question.
#
# *This block read "THIS IS NOT THE SHIPPING DEFAULT ... is still None" until
# 2026-08-06 (C33 corrected it). C31b left the default off on the metric alone
# and was overruled on the geometry an hour later; the metric argument it made
# is kept below because it is still the honest account of what `d` costs.*
#
# What it costs, measured rather than argued. On the nine marker-refereed
# captures (C31b, 2026-08-06) applying `d` improves per-rep horizontal rms on
# 5 of the 6 whose DISPLAY AXIS step 8 can find and makes it 39-202% worse on
# the 3 it cannot — and on those three the axis turns 23-50 degrees when `d` is
# applied, so the before and after are not measured along the same line. The
# blocker there is step 8, not step 6, and not more tape.
#
# What it is good for, measured rather than argued:
#   * bench VERTICAL rms improves on 6 of 6, by ~20-25%
#   * `bench_92.5x4_1` — the one capture `FINDINGS.md` records as losing to the
#     flat-line null — crosses it, `beats_null` 0.71 -> 1.78
#   * the ACCELERATION correlation against the video improves on 6 of 6 benches
#     and on 3 of 3 deadlifts, deadlift going 0.12-0.23 to 0.43-0.64
#
# And one thing it is NOT evidence of. Sweeping |d| along this direction, the
# position rms falls monotonically out to 3x the tape on deadlift and on the
# vertical axis of bench — no interior optimum anywhere. So an improvement in
# position rms does not identify a lever arm and never could; that is B2's
# result reproduced from the other side, and it is why this is a constant and
# not a fitted parameter. The acceleration correlation DOES have an interior
# optimum, tightly at 0.5-0.75x the tape on all six benches and nowhere on
# deadlift — consistent with the wrist extension named at the end of
# `apply_offset`, which would shorten the EFFECTIVE lever below the geometric
# one. Unresolved; see analysis/48.
WRIST_OFFSET_M = {
    "bench": np.array([-0.09, 0.0, 0.03]),
    "deadlift": np.array([-0.09, 0.0, 0.03]),
    "squat": np.array([-0.05, 0.0, -0.04]),
}


def apply_offset(position: np.ndarray, quat: np.ndarray,
                 d: np.ndarray) -> np.ndarray:
    """p_bar(t) = p_watch(t) - R(t).d. Step 6.

    `d` is the lever arm from watch to bar in BODY coordinates, so it is a
    constant vector that the wrist's own rotation sweeps around. `quat` must be
    the CORRECTED attitude from orient.correct_attitude, w-x-y-z, matching what
    to_world used — using the reported attitude here would reintroduce exactly
    the error step 2 removed.

    The constant part of this is irrelevant. Reps are aligned by start point
    (detrend_set), so any fixed offset cancels; what survives is how R(t).d
    VARIES through a rep, which at |d| = 14 cm is 1.2-2.4 cm horizontally at a
    typical lever-arm direction and 4-6.4 cm at the worst. See the module
    docstring — the 8-13 cm this project used to quote was ~3x too big.

    Cheap and well-conditioned: R(t) is already computed and is the most
    trustworthy quantity in the system, so this adds no new error source. What
    it cannot capture is wrist extension under load — the hand laying back
    relative to the forearm — which changes the lever arm itself and is not
    observable from one wrist IMU.
    """
    R = Rotation.from_quat(quat, scalar_first=True)
    return position - R.apply(np.asarray(d, dtype=float))


# ----------------------------------------------------------------- step 5b
DRIFT_TILT_MAX_RAD_S = np.deg2rad(0.10)


def fit_drift_tilt(log: dict, bounds: list[tuple[int, int]],
                   wrist_offset: np.ndarray | None,
                   max_rate: float = DRIFT_TILT_MAX_RAD_S) -> tuple[np.ndarray, dict]:
    """A world-horizontal attitude drift rate, fitted from the set alone. H8.

    Returns `(beta, info)`. `beta` is rad/s about the two world-horizontal axes;
    the caller applies it as `R_true(t) = expm(-[beta.(t-t0)]x) . R_reported(t)`,
    a LEFT multiplication, and `t0` is the start of the first rep.

    The mechanism, because this encodes a judgement about the physics
    ----------------------------------------------------------------
    H1 measured what the deadlift's invented fore-aft IS. Each rep's horizontal
    path is a constant-acceleration parabola whose size GROWS through the set —
    5.2 to 34.9 cm on `deadlift_160x6_1` while the video's own bar stays at
    4.2-5.4 — and pushing candidate error fields through the real pipeline (every
    stage after acceleration is linear, so this is exact) a **horizontal
    acceleration growing linearly in time** explains 84-91% of the error OUT OF
    SAMPLE, leave-one-rep-out.

    The reason to believe that rather than any other growing thing is the
    falsification test, which passed: a tilt error leaks `g.sin(theta)` into the
    horizontal and only `g.(1-cos(theta))` into the vertical, first order against
    second. So the same fitted parameters must explain horizontal and must FAIL
    on vertical. Measured: horizontal 0.84-0.91, vertical **-1.63 to -0.02**.

    **What it is NOT.** Not a gyro bias of the watch: converted into watch axes,
    where a body-fixed sensor bias would have to agree, the six fitted directions
    scatter 27-149 degrees apart. Fixed within a capture, random across them. And
    not resolvably impact-localised: a staircase stepping at each floor impact
    and a smooth ramp correlate 0.86-0.97 at 3-6 evenly spaced reps, so this
    corpus cannot separate them and neither should this docstring.

    Why the objective is dispersion, and why anything else is a trap
    ---------------------------------------------------------------
    `beta` cannot be fitted against the video — that is an oracle, and B2 is the
    standing lesson about fitting geometry to footage. It is fitted against the
    set's own **rep-to-rep dispersion**, on this argument: the true bar path
    REPEATS every rep and the drift GROWS, so a set whose reps already agree is
    left alone and one whose reps fan out is pulled together.

    **"Minimise the horizontal excursion" would be the obvious objective and it
    is a cheat.** It collapses to the flat-line null — it scores well by drawing
    no fore-aft at all, which is precisely what `metrics.beats_null` exists to
    catch. Dispersion cannot do that: a set of identical 5 cm J-curves has zero
    dispersion and is untouched.

    **The anchor is not decoration, and it cost an iteration to learn.**
    Dispersion is symmetric — it can equalise the reps by making rep 1 as wrong
    as rep 6 rather than the reverse. Unanchored it did exactly that:
    `deadlift_150x4_1` went 2.66 -> **8.17 cm** while its dispersion fell 4.45 ->
    2.17, the optimiser succeeding while the answer got worse. The drift grows,
    so rep 1 carries least of it; anchoring the ramp to vanish at the first rep
    gives the objective a direction and the regression went with it.

    What it costs, measured rather than argued
    ------------------------------------------
    Deadlift median horizontal 4.97 -> 3.78 cm, and the three fastest-growing
    sets take the three largest gains: `160x6_1` 7.52 -> 1.97, `160x6_2`
    4.40 -> 1.74, `160x4_2` 3.98 -> 2.53. Fitted |beta| is 0.008-0.051 deg/s,
    the same range H1's video-fitted oracle found and an order BELOW what the
    pre-set pause can measure — so this recovers without video what B1 correctly
    refused to estimate from a hold, and B1's rejection is not disturbed.

    **It is self-limiting on the lifts that do not drift**, which is why it is
    not gated on the lift: |beta| comes out 0.001-0.008 deg/s on bench and
    0.004-0.006 on squat, because there is no growth for it to find. Bench median
    2.01 -> 2.21, squat 2.65 -> 1.87.

    **Two captures it makes worse, and neither is smoothed away.**
    `deadlift_150x4_1` 2.66 -> 5.03: it is the capture nearest its own null
    (2.66 against 2.15) with a best-possible axis of 2.24, so there was almost
    nothing to win and a mis-set `beta` costs it. `deadlift_170x4_3` 5.54 -> 5.60
    is unmoved and is the capture whose video clock fits 22.8% drift at a 216 ms
    residual, so its score is untrustworthy either way. A guard that declined to
    correct a set already within a centimetre of the null would protect the
    first, but the null needs the video. Open.

    **`max_rate` is a safety rail, not a tuned constant.** It never binds on this
    corpus: the largest fit is 0.051 deg/s against a 0.10 cap, and
    `calibrate.anchor_tilt` independently bounds a set's real attitude drift at
    ~0.014. It exists so a degenerate set cannot hand the pipeline a large
    rotation, and a capture that wanted more than 0.1 deg/s would be telling you
    the objective had found something other than drift.

    What would falsify this
    -----------------------
    A capture whose reps genuinely diverge — a set where the lifter's bar path
    really does change shape rep to rep — would be pulled together by this and
    lose real signal. The corpus has none, and the video says the deadlift bar's
    per-rep fore-aft stays flat while the reconstruction's grows, which is the
    evidence for the premise rather than a proof of it. A set filmed with a
    deliberately drifting bar path is the experiment that would settle it.
    """
    from scipy.optimize import minimize

    from . import calibrate, integrate, orient

    if len(bounds) < 2:
        return np.zeros(3), {"fitted": False,
                             "reason": "needs >=2 reps to measure dispersion"}

    t0 = float(log["t"][bounds[0][0]])
    tau = np.maximum(log["t"] - t0, 0.0)
    R_reported = Rotation.from_quat(log["quat"], scalar_first=True)

    def paths(beta: np.ndarray) -> list[np.ndarray]:
        quat = (Rotation.from_rotvec(-np.outer(tau, beta)) * R_reported
                ).as_quat(scalar_first=True)
        world = orient.to_world(log["accel"], log["quat"], quat)
        world = world - calibrate.accel_bias(world, log)
        _, position = integrate.integrate(world, log["dt"])
        bar = (position if wrist_offset is None
               else apply_offset(position, quat, wrist_offset))
        return detrend_set(bar, bounds, log["t"])

    def dispersion(beta2: np.ndarray) -> float:
        reps = paths(np.array([beta2[0], beta2[1], 0.0]))
        grid = np.stack([
            np.column_stack([np.interp(np.linspace(0, 1, 60),
                                       np.linspace(0, 1, len(r)), r[:, i])
                             for i in range(2)]) for r in reps])
        return float(np.sqrt(((grid - grid.mean(axis=0)) ** 2).sum(axis=2).mean()))

    before = dispersion(np.zeros(2))
    fit = minimize(dispersion, np.zeros(2), method="Nelder-Mead",
                   options=dict(xatol=1e-5, fatol=1e-7, maxiter=400))
    beta = np.array([fit.x[0], fit.x[1], 0.0])

    # The rail. Scale back rather than refuse: a capped correction is still in
    # the right direction, and refusing outright would silently return the
    # uncorrected path on exactly the sets that need it most.
    rate = float(np.linalg.norm(beta))
    capped = rate > max_rate
    if capped:
        beta = beta * (max_rate / rate)

    return beta, {
        "fitted": True,
        "rate_rad_s": rate,
        "capped": capped,
        "dispersion_before_m": before,
        "dispersion_after_m": dispersion(beta[:2]),
        "anchor_t": t0,
    }


def apply_drift_tilt(quat: np.ndarray, t: np.ndarray, beta: np.ndarray,
                     anchor_t: float) -> np.ndarray:
    """Rotate the attitude back by `beta` per second, from `anchor_t` on. H8.

    LEFT multiplication, because `beta` is a WORLD-frame rate — the quantity
    `fit_drift_tilt` identifies is a drift of the world-horizontal, not a
    body-fixed gyro bias (see that docstring: the fitted directions scatter
    27-149 degrees in watch axes). `orient.correct_attitude` right-multiplies
    for the body-fixed case and the two must not be confused.
    """
    tau = np.maximum(np.asarray(t, dtype=float) - float(anchor_t), 0.0)
    corrected = (Rotation.from_rotvec(-np.outer(tau, np.asarray(beta, float)))
                 * Rotation.from_quat(quat, scalar_first=True))
    return corrected.as_quat(scalar_first=True)


def detrend_rep(position: np.ndarray, start: int, stop: int, t: np.ndarray,
                axes: tuple[int, ...] = (0, 1, 2), edge: int = 1,
                velocity: np.ndarray | None = None, order: int = 1) -> np.ndarray:
    """Subtract the endpoint-to-endpoint line, on `axes` only. Step 7. B3.

    `order=2` adds one quadratic term, pinned by a SECOND closure the rep
    already supplies. **It was built, measured and REJECTED (C19, 2026-08-02);
    it defaults to 1, which is bit-identical to the original behaviour.** The
    mechanism and the rejection are both below, because TASKS.md B6 asks in so
    many words for a detrend that "can absorb a quadratic" and this is the
    obvious way to get one — so the measurement needs to be here, next to the
    idea, or it gets re-proposed on the strength of the reasoning.

    The mechanism, because this encodes a judgement about the physics
    ----------------------------------------------------------------
    Today's line asserts one thing: a rep ends where it began, so
    `p(T) - p(0)` is entirely drift. That is two coefficients constrained by
    one measured quantity, `dp`, and it fixes the line.

    A rep is periodic in VELOCITY as well as position. The bar is at the same
    phase of the same motion at both boundaries — at rest at the floor on a
    deadlift, at rest at lockout on a touch-and-go bench — so the true
    `v(T) - v(0)` is zero and the reconstructed `dv` is likewise entirely
    drift. That is a second measured quantity, from the same rep boundaries
    the position closure already trusts and from no new anchor, no video and
    no threshold. Three constraints, three coefficients:

        c(tau) = (dv / 2T) tau^2 + (dp/T - dv/2) tau

    **When `dv` is zero this IS the current line**, which is the property that
    makes it a generalisation rather than a rival. The quadratic term is
    driven entirely by how badly velocity fails to close, which is exactly what
    `metrics.momentum_closure` measures: ~0 on bench, -0.37 to -1.48 m/s across
    a deadlift landing.

    What it claimed, and how it was falsified
    -----------------------------------------
    It claimed the velocity non-closure across a rep is drift rather than
    signal — the same class of claim the position closure makes, and seemingly
    a safer one, since the position version is known false horizontally while a
    rep genuinely does start and end at the same speed.

    **It is false on deadlift, and expensively so.** `python run.py --b3oracle`:

        capture             shipping h   order=2 h   order=2 v   order=2 ROM
        deadlift_155x6_1        5.05       29.11       48.67         78.2
        deadlift_155x6_2        9.19       25.20       41.75         68.4
        deadlift_180x3         15.44       12.17       73.11        116.4

    against a 61 cm ROM ceiling and a shipped vertical of 5.24 / 6.60 / 5.24.
    **It is the vertical and the ROM that reject it, not the horizontal** —
    `deadlift_180x3` improves fore-aft, 15.44 -> 12.17, so "it loses on
    horizontal" is not something these captures support. Bench, which has no
    landing and whose `dv` is near zero, moves little and in both directions:
    3.67 -> 1.65 and 2.69 -> 0.97 on the spotos, 0.64 -> 1.13 and
    1.88 -> 2.82 on the 90x4s.

    **Do not read the median.** Over the ten scoreable captures it improves,
    2.72 -> 2.23 cm, while deadlift is destroyed. That is this project's
    recurring failure shape — an aggregate that passes while the thing fails
    exactly where it matters — and it is the reason the rule was fixed per-rule
    and in advance rather than as one summary number.

    Why, and it generalises past this attempt
    -----------------------------------------
    `dv` across a deadlift rep is ~1 m/s, and C11 established that deficit is
    real error injected AT THE LANDING and nowhere else. The quadratic removes
    it, correctly in total, by spreading it smoothly across the whole rep —
    injecting `dv.T/8` at mid-rep, ~31 cm at T = 2.5 s, an order above the
    5-15 cm being corrected.

    That is B6's finding one order up. B6 measured that **a constant
    acceleration correction cannot represent an impulse**; this measures that
    **a quadratic cannot either.** The obstacle was never the detrend's order.
    Any basis that is smooth across the whole rep spreads a landing-localised
    error over the whole rep, and raising the order raises what it spreads.
    So "give the detrend a quadratic to absorb the splice's artefact" does not
    work, and rule 3 measured it directly: under an order=2 detrend the splice
    breaks the ROM ceiling harder (78.1 / 70.4 / 116.4 cm) and loses more
    horizontally (16.41 / 19.27 / 24.87) than under the linear one.

    What survives is the ORACLE, and it is the useful half. See TASKS.md B3.

    `axes` used to be all three implicitly. It is a parameter now because the
    closure premise is true vertically and false horizontally: the bar does
    return to the floor, and it does not return to the same spot on it. See
    `detrend_set`, which decides which axes a given capture can close.

    `edge` medians that many samples at each end instead of using the two
    extreme ones. TASKS.md has listed the endpoint sensitivity under B3 since
    the detrend was written, and the reasoning is sound — a line through two
    samples is maximally noise-sensitive at exactly the indices it depends on.

    **It defaults to 1 (the original behaviour) because it measures as worth
    nothing.** At `edge=5` the horizontal error is 10.08 cm mean across the
    three deadlifts against 9.91 at `edge=1` — indistinguishable, marginally
    worse. Kept as a parameter with the measurement recorded, so the idea is
    not re-proposed on the strength of the reasoning alone.

    That measurement took a detour worth recording. `edge=5` first appeared to
    give 5.1/9.2/15.4 -> 5.1/9.2/15.4, better on 3 of 3, and was committed as a
    win. It was not: the drift was measured between the two medians, which sit
    at t[edge/2] rather than at the ends, and then applied across the full
    window — under-correcting by edge/len, about 1.7%. The gain was that
    accidental shrinkage, not the median. Fixing the baseline (drift per unit
    time between the medians' MEAN TIMES) restored the original numbers. See
    TASKS.md B3 for what the shrinkage itself might mean.
    """
    rep = position[start:stop].copy()
    if len(rep) < 2:
        return rep

    e = max(min(edge, len(rep) // 2), 1)
    drift = np.median(rep[-e:], axis=0) - np.median(rep[:e], axis=0)
    span = float(t[-e:].mean() - t[:e].mean())
    if span <= 0:
        return rep

    # Sized to the input, not to 3: metrics._close applies this same closure to
    # the 2-column video path, where "vertical" is column 1 rather than 2.
    keep = np.zeros(rep.shape[1])
    keep[[a for a in axes if a < rep.shape[1]]] = 1.0

    tau = (t - t[0])[:, None]
    if order < 2 or velocity is None:
        return rep - (tau / span) * (drift * keep)

    # The second closure. `dv` is medianed over the same `edge` samples as
    # `drift`, so both endpoints are read the same way — reading one from a
    # median and the other from a single sample would make the quadratic term
    # noisier than the linear one it is being weighed against.
    vel = velocity[start:stop]
    dv = np.median(vel[-e:], axis=0) - np.median(vel[:e], axis=0)

    a = (dv * keep) / (2.0 * span)
    b = (drift * keep) / span - (dv * keep) / 2.0
    return rep - (a * tau ** 2 + b * tau)


def detrend_set(position: np.ndarray, bounds: list[tuple[int, int]],
                t: np.ndarray, axes: tuple[int, ...] = (0, 1, 2),
                velocity: np.ndarray | None = None,
                order: int = 1) -> list[np.ndarray]:
    """One detrended path per rep, each translated so its start is the origin.

    Alignment is by START POINT ONLY. Do not align whole paths — between-rep
    divergence is the signal, not the error.

    All three axes by default, and that includes the horizontal closure B3
    identified as false. It stays because **removing it is far worse**, which
    B7 measured: closing vertical only, without something to control horizontal
    drift, gives 495 / 522 / 337 cm against 5.1 / 9.2 / 15.4. The bar genuinely
    does not land where it was pulled from — A3 puts that at 1.9-4.3 cm — so
    this constraint is knowingly wrong and costs a few centimetres to avoid
    losing several metres. That is a trade, not a justification.

    The floor-impact anchor was the intended replacement and it lost; see
    TASKS.md B7. `axes` is kept so the next attempt can pass `(2,)` and be
    measured against the same numbers rather than re-deriving them.
    """
    reps = []
    for start, end in bounds:
        rep = detrend_rep(position, start, end, t[start:end], axes=axes,
                          velocity=velocity, order=order)
        rep -= rep[0]
        reps.append(rep)
    return reps

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
None is gone. The DEFAULT has not moved, and that is a separate question with
a separate answer — see the constant's docstring and `pipeline.run`.

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

Kalman filters, factor graphs, batch smoothers and spline fits were previously
rejected here by reference to NON_GOALS.md. That table was deleted on
2026-07-28 because its evidence was synthetic. Nothing in this file forbids a
solver any more — but see TASKS.md B6 before building one: an oracle fitting
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
# **THIS IS NOT THE SHIPPING DEFAULT, and read why before turning it on.**
# `pipeline.run(wrist_offset=)` is still None. On the nine marker-refereed
# captures (C31b, 2026-08-06) applying it improves per-rep horizontal rms on
# 5 of the 6 whose DISPLAY AXIS step 8 can find and makes it 39-202% worse on
# the 3 it cannot — and on those three the axis turns 23-50 degrees when `d` is
# applied, so the before and after are not measured along the same line. The
# blocker is step 8, not step 6, and not more tape.
#
# What it is good for, measured rather than argued:
#   * bench VERTICAL rms improves on 6 of 6, by ~20-25%
#   * `bench_92.5x4_1` — the one capture CLAUDE.md records as losing to the
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

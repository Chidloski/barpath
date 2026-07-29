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
the forearm axis in body coordinates, refined per user against video.

**Deadlift is NOT exempt.** This docstring used to say it was — that the
forearm hangs near-vertical throughout, so R(t).d stays near-constant and the
constant part vanishes when reps are aligned by start point. Measured on the
real captures, R(t).d varies by **8-13 cm horizontally on every lift, deadlift
included**. That is the entire error budget several times over, and it makes
this the largest unmodelled term in the system rather than a bench-only
refinement. pipeline.py says the same thing where it records the blocked stage.
The reasoning above was not silly — it is right about the direction of the
effect and wrong about its size, which is what happens when a geometric
argument is never checked against a measurement.

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
the horizontal error after this stage is 4.6-13.4 cm rms per rep.

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
cm against a 5-13 cm total. This stage is doing something wrong and worth
fixing; it is not where the horizontal failure lives. Most of the error is
already in the acceleration that reaches the integrator.

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
    NOT IMPLEMENTED — B2. Needs the video ground truth (A2) to establish d as
    a measurement rather than a guess.

detrend_rep(position, start, stop, t, axes=(0,1,2), edge=5) -> (M, 3)
    Line subtracted so the rep starts and ends at the same point. `edge` is
    half of B3, done: fitting through the two extreme samples made this
    maximally noise-sensitive at exactly the indices it depends on, and a
    5-sample median at each end took horizontal error from 5.1/9.2/15.4 to
    4.6/7.8/13.4 cm, better on 3 of 3 captures.

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


def apply_offset(position: np.ndarray, quat: np.ndarray,
                 d: np.ndarray) -> np.ndarray:
    raise NotImplementedError("step 6 — see TASKS.md B2 and this module's docstring")


def detrend_rep(position: np.ndarray, start: int, stop: int, t: np.ndarray,
                axes: tuple[int, ...] = (0, 1, 2), edge: int = 5) -> np.ndarray:
    """Subtract the endpoint-to-endpoint line, on `axes` only. Step 7. B3.

    `axes` used to be all three implicitly. It is a parameter now because the
    closure premise is true vertically and false horizontally: the bar does
    return to the floor, and it does not return to the same spot on it. See
    `detrend_set`, which decides which axes a given capture can close.

    `edge` medians a few samples at each end instead of using the two extreme
    ones. Fitting a line through exactly two samples makes it maximally
    noise-sensitive at exactly the indices it depends on, which TASKS.md has
    listed under B3 since the detrend was written.
    """
    rep = position[start:stop].copy()
    if len(rep) < 2:
        return rep

    e = max(min(edge, len(rep) // 2), 1)
    drift = np.median(rep[-e:], axis=0) - np.median(rep[:e], axis=0)

    # Sized to the input, not to 3: metrics._close applies this same closure to
    # the 2-column video path, where "vertical" is column 1 rather than 2.
    keep = np.zeros(rep.shape[1])
    keep[[a for a in axes if a < rep.shape[1]]] = 1.0
    span = t[-1] - t[0]
    times = (t - t[0]) / span if span > 0 else np.zeros(len(rep))

    return rep - times[:, None] * (drift * keep)


def detrend_set(position: np.ndarray, bounds: list[tuple[int, int]],
                t: np.ndarray, axes: tuple[int, ...] = (0, 1, 2)) -> list[np.ndarray]:
    """One detrended path per rep, each translated so its start is the origin.

    Alignment is by START POINT ONLY. Do not align whole paths — between-rep
    divergence is the signal, not the error.

    All three axes by default, and that includes the horizontal closure B3
    identified as false. It stays because **removing it is far worse**, which
    B7 measured: closing vertical only, without something to control horizontal
    drift, gives 495 / 522 / 337 cm against 4.6 / 7.8 / 13.4. The bar genuinely
    does not land where it was pulled from — A3 puts that at 1.9-4.3 cm — so
    this constraint is knowingly wrong and costs a few centimetres to avoid
    losing several metres. That is a trade, not a justification.

    The floor-impact anchor was the intended replacement and it lost; see
    TASKS.md B7. `axes` is kept so the next attempt can pass `(2,)` and be
    measured against the same numbers rather than re-deriving them.
    """
    reps = []
    for start, end in bounds:
        rep = detrend_rep(position, start, end, t[start:end], axes=axes)
        rep -= rep[0]
        reps.append(rep)
    return reps

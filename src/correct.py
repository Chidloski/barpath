"""
Steps 6-7 — wrist-to-bar offset, and the per-rep detrend.

=========================================================================
RESERVED MODULE. The owner writes this. Claude Code reviews and explains,
but does not implement. See CLAUDE.md.
=========================================================================

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

Deadlift needs none of this: the forearm hangs near-vertical throughout, so
R(t).d is near-constant, and a constant offset vanishes the moment reps are
aligned by start point. Build and validate there first, then add this when
you move to bench.

What cannot be modelled from one wrist sensor is wrist extension under load
— the hand laying back relative to the forearm. That is the accuracy floor
on bench and the reason bench paths stay qualitative.


Step 7 — per-rep detrend
------------------------
For each rep, subtract a straight line in position, per axis, from the start
index to the end index.

Why it works: the dominant errors are smooth, slowly varying and monotonic,
while the true motion is periodic and returns to its origin. Subtracting a
line removes almost all of the former and leaves the latter's SHAPE
untouched — and shape is where the anomaly lives. The residual is the
within-rep bow, around 1 cm, which is the spec.

Why it is legitimate rather than massaging: it is a physical fact that the
bar starts and ends each rep in the same place. You are imposing a true
constraint.

This replaces every solver approach — Kalman filters, factor graphs, batch
smoothers, spline fits. If it seems insufficient, say so rather than
building a replacement. See NON_GOALS.md.

Because every rep closes individually, cumulative drift across the set is
already gone. Do not additionally zero the net horizontal across the set;
it is redundant.


What to implement
-----------------

apply_offset(position, quat, d) -> (N, 3)

detrend_rep(position, start, stop) -> (M, 3)
    Line subtracted so the rep starts and ends at the same point.

detrend_set(position, bounds) -> list of (M, 3) arrays
    One detrended path per rep, each translated so its start sits at the
    common origin. Alignment is by START POINT ONLY. Do not align whole
    paths — between-rep divergence is the signal, not the error.


Suggested check
---------------
Full synthetic set with realistic bias injected: each recovered rep should
match synth.pos_true over the same index range to under 1 cm horizontally.
That 1 cm is the spec, and it comes from the 4x display stretch.
"""

from __future__ import annotations

import numpy as np


def apply_offset(position: np.ndarray, quat: np.ndarray,
                 d: np.ndarray) -> np.ndarray:
    raise NotImplementedError("Reserved module — see docstring.")


def detrend_rep(position: np.ndarray, start: int, stop: int, t: np.ndarray) -> np.ndarray:
    rep = position[start:stop]
    drift = rep[-1] - rep[0]

    times = (t - t[0]) / (t[-1] - t[0])

    drift_line = times[:, None] * drift

    return rep - drift_line


def detrend_set(position: np.ndarray,
                bounds: list[tuple[int, int]], t: np.ndarray) -> list[np.ndarray]:

    reps = []

    for start, end in bounds:
        rep = detrend_rep(position, start, end, t[start:end])
        rep -= rep[0]
        reps.append(rep)

    return reps

"""
Step 5 — rep segmentation.

Two ideas.

ZUPT (zero-velocity update). Knowing that true velocity is zero at a given
instant is powerful, because any velocity you have accumulated by then is
pure error. Finding those instants is what makes the detrend in step 7 work.

The two-pass structure. You need position to classify stillness, and clean
stillness to get position. The circularity breaks because rough vertical
position — from a first integration pass with only the gyro bias removed —
is good to a few centimetres, and the gap between "at the rest position"
and "at full range of motion" is tens of centimetres. Crude is plenty.

A false ZUPT is worse than a missed one: you assert v = 0 when it is not,
injecting error rather than removing it. Hence requiring BOTH low
acceleration and low angular-rate variance, plus a persistence requirement.
"""

from __future__ import annotations

import numpy as np


def _rolling_var(x: np.ndarray, w: int) -> np.ndarray:
    """Centred rolling variance of a 1-D signal, same length as input."""
    pad = w // 2
    xp = np.pad(x, (pad, w - 1 - pad), mode="edge")
    c1 = np.concatenate([[0.0], np.cumsum(xp)])
    c2 = np.concatenate([[0.0], np.cumsum(xp**2)])
    n = len(x)
    s1 = c1[w:w + n] - c1[:n]
    s2 = c2[w:w + n] - c2[:n]
    return np.maximum(s2 / w - (s1 / w) ** 2, 0.0)


def stationary_mask(log: dict, window_s: float = 0.25,
                    accel_var_max: float = 0.05,
                    gyro_var_max: float = 0.002,
                    min_duration_s: float = 0.20) -> np.ndarray:
    """Boolean mask of samples where the watch is judged stationary."""
    fs = log["fs"]
    w = max(int(round(window_s * fs)), 3)

    av = _rolling_var(np.linalg.norm(log["accel"], axis=1), w)
    gv = _rolling_var(np.linalg.norm(log["gyro"], axis=1), w)
    quiet = (av < accel_var_max) & (gv < gyro_var_max)

    return _drop_short(quiet, int(round(min_duration_s * fs)))


def _drop_short(mask: np.ndarray, min_len: int) -> np.ndarray:
    """Remove runs of True shorter than min_len."""
    out = mask.copy()
    for a, b in runs(mask):
        if b - a < min_len:
            out[a:b] = False
    return out


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous [start, stop) index pairs where mask is True."""
    if not mask.any():
        return []
    d = np.diff(mask.astype(np.int8))
    starts = list(np.flatnonzero(d == 1) + 1)
    stops = list(np.flatnonzero(d == -1) + 1)
    if mask[0]:
        starts.insert(0, 0)
    if mask[-1]:
        stops.append(len(mask))
    return list(zip(starts, stops))


def rep_bounds(log: dict, vertical: np.ndarray,
               lift: str = "deadlift",
               rest_tolerance: float = 0.10) -> list[tuple[int, int]]:
    """Classify stationary windows into rep boundaries.

    `vertical` is rough vertical position from the first integration pass.

    A boundary sits near the lift's rest position; a mid-rep pause (a grind,
    a paused bench, a held lockout) sits near full range of motion. Those are
    tens of centimetres apart, so a few centimetres of drift cannot confuse
    them.

    Where the rest position is depends on the lift:
        deadlift  — bar on the floor, so rest is the MINIMUM of vertical
        squat     — standing, so rest is the MAXIMUM
        bench     — locked out, so rest is the MAXIMUM

    Returns [start, end) index pairs, one per rep.
    """
    mask = stationary_mask(log)
    windows = runs(mask)
    if len(windows) < 2:
        return []

    heights = np.array([vertical[a:b].mean() for a, b in windows])
    rest = heights.min() if lift == "deadlift" else heights.max()
    at_rest = np.abs(heights - rest) < rest_tolerance

    anchors = [w for w, keep in zip(windows, at_rest) if keep]

    # A rep runs from the LAST still sample before motion to the FIRST still
    # sample after it. Not the window centres: the pause between reps can be
    # a second long, and taking its midpoint would put the boundary half a
    # second inside the rest period, which is exactly the sort of small
    # systematic offset that survives every later correction.
    return [(anchors[i][1] - 1, anchors[i + 1][0])
            for i in range(len(anchors) - 1)]


def quality_flags(log: dict, bounds: list[tuple[int, int]]) -> list[dict]:
    """Per-rep data-quality checks.

    Discriminate on PHYSICAL IMPOSSIBILITY, not on unusualness. The rep you
    most want to discard for looking strange is often the rep with the real
    form breakdown. Strap resonance is energy above ~10 Hz, where barbell
    motion has essentially none. Clipping is a hard rail. Both are outside
    what a barbell can do. A grind is ugly but physically plausible: keep it.
    """
    fs = log["fs"]
    out = []
    for a, b in bounds:
        seg = log["accel"][a:b]
        n = len(seg)
        flags = {"rep": (a, b), "clipped": False, "strap_resonance": False}

        if np.abs(seg).max() > 0.95 * 16 * 9.80665:
            flags["clipped"] = True

        if n > 16:
            mag = np.linalg.norm(seg, axis=1)
            spec = np.abs(np.fft.rfft(mag - mag.mean())) ** 2
            freq = np.fft.rfftfreq(n, 1.0 / fs)
            total = spec.sum()
            if total > 0 and spec[freq > 10.0].sum() / total > 0.25:
                flags["strap_resonance"] = True

        flags["ok"] = not (flags["clipped"] or flags["strap_resonance"])
        out.append(flags)
    return out

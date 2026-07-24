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
               grind_band: float = 0.15,
               min_excursion: float = 0.12) -> list[tuple[int, int]]:
    """Rep boundaries from the stationary windows and a rough, drifting vertical.

    A rep is a departure from the rest position and a return to it. The rest
    position is fixed in the room — the bar racks, locks out, or sits on the
    floor at the same height every rep — but the rough vertical from a single
    integration drifts by metres across a set (uncorrected accelerometer bias;
    the leak from gyro bias is already gone by this stage). So ABSOLUTE height
    is useless. What survives is the shape relative to a locally-fitted rest
    line, and that is what this works on.

    Method:
      1. Stationary windows — drift-immune, from accel/gyro variance.
      2. Fit the drift through the REST windows only. Every rest sits at the
         same true height, so a low-order fit through them recovers the drift.
         A window sitting more than `grind_band` on the range-of-motion side of
         that line is a hold at mid-ROM — a sticking point, a paused rep — and
         is dropped from the fit, robustly, by refitting until the rest set
         stops changing. Subtracting the fit flattens the rest line to ~0.
      3. Anchors are the rest windows. Between each consecutive pair, a rep is
         present iff the bar deviates from the rest line by more than
         `min_excursion` in the lift's ROM direction. That single test rejects
         gaps with no real movement AND lets a rep span a mid-rep hold: the
         hold is not a rest window, so the rep simply runs from the rest before
         it to the rest after — a grind cannot split or hide a rep, and it is
         never itself mistaken for a boundary.

    Where "rest" sits depends on the lift:
        deadlift     — bar on the floor, so rest is the MINIMUM of vertical
        squat, bench — standing / locked out, so rest is the MAXIMUM

    Returns [start, end) index pairs, one per rep: from the last still sample
    before the rep to the first still sample after it.
    """
    windows = runs(stationary_mask(log))
    if len(windows) < 2:
        return []

    idx = np.arange(len(vertical))
    heights = np.array([vertical[a:b].mean() for a, b in windows])
    centers = np.array([(a + b) / 2 for a, b in windows])
    top_is_max = lift != "deadlift"

    # Robust drift fit: drop windows on the ROM side of the rest line (grinds /
    # held reps), refit, until the set of rest windows is stable.
    keep = np.ones(len(windows), dtype=bool)
    for _ in range(len(windows)):
        resid = heights - np.polyval(np.polyfit(centers[keep], heights[keep], 2), centers)
        ref = np.median(resid[keep])
        new_keep = (resid > ref - grind_band) if top_is_max else (resid < ref + grind_band)
        if np.array_equal(new_keep, keep) or new_keep.sum() < 3:
            break
        keep = new_keep

    flat = vertical - np.polyval(np.polyfit(centers[keep], heights[keep], 2), idx)
    win_flat = np.array([flat[a:b].mean() for a, b in windows])
    top = np.median(win_flat[keep])

    # A rep runs from the LAST still sample before motion to the FIRST still
    # sample after it — not the window centres, which would place the boundary
    # a systematic half-second inside the rest.
    anchors = [w for w, k in zip(windows, keep) if k]
    bounds = []
    for (_, b0), (a1, _) in zip(anchors, anchors[1:]):
        gap = flat[b0 - 1:a1]
        excursion = (top - gap.min()) if top_is_max else (gap.max() - top)
        if excursion > min_excursion:
            bounds.append((b0 - 1, a1))
    return bounds


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

"""
Step 1 — gyro bias from the pre-set pause.

A stationary gyro should read zero. Whatever it reads is bias. Averaging
over a still window gives it directly, no solver required.

This is the single highest-value operation in the pipeline. Gyro bias
corrupts your sense of which way is down, and a wrong "down" leaks gravity
into the horizontal axes with an error that grows as t^3. Consumer turn-on
bias is 0.5-2 deg/s; measuring it drops you to the in-run instability floor
around 0.005-0.01 deg/s. Over a 2 s rep that is the difference between
roughly 23 cm of phantom horizontal drift and roughly 2 mm.

We do not ask the user to be perfectly still. We ask for three seconds and
then find the stillest part ourselves.
"""

from __future__ import annotations

import numpy as np


def stillest_window(log: dict, search_s: float = 3.0,
                    window_s: float = 1.0) -> tuple[int, int]:
    """Find the quietest sub-window inside the opening `search_s` seconds.

    Scored on gyro magnitude variance. Returns (start, stop) indices.
    """
    t = log["t"]
    end = int(np.searchsorted(t, search_s))
    w = max(int(round(window_s * log["fs"])), 5)
    if end <= w:
        return 0, max(end, w)

    mag = np.linalg.norm(log["gyro"][:end], axis=1)
    # Rolling variance via cumulative sums of x and x^2.
    c1 = np.concatenate([[0.0], np.cumsum(mag)])
    c2 = np.concatenate([[0.0], np.cumsum(mag**2)])
    n = len(mag) - w + 1
    s1 = c1[w:] - c1[:n]
    s2 = c2[w:] - c2[:n]
    var = s2 / w - (s1 / w) ** 2

    i = int(np.argmin(var))
    return i, i + w


def gyro_bias(log: dict, search_s: float = 3.0, window_s: float = 1.0,
              fallback: np.ndarray | None = None,
              max_rate: float = 0.05) -> tuple[np.ndarray, dict]:
    """Estimate gyro bias, rad/s.

    `max_rate` is the quality gate: if the stillest window still averages
    more motion than this, the user never held still. Fall back rather than
    block — never let calibration stop somebody lifting.

    Returns (bias, info) where info carries the quality flags.
    """
    i, j = stillest_window(log, search_s, window_s)
    seg = log["gyro"][i:j]
    bias = seg.mean(axis=0)

    residual = float(np.linalg.norm(seg - bias, axis=1).mean())
    ok = residual < max_rate

    if not ok and fallback is not None:
        bias = np.asarray(fallback, dtype=float)

    return bias, {
        "window": (i, j),
        "residual_rad_s": residual,
        "confident": bool(ok),
        "used_fallback": bool(not ok and fallback is not None),
    }


def initial_tilt(log: dict, window: tuple[int, int]) -> np.ndarray:
    """Mean measured acceleration over the still window, m/s^2.

    Should be ~zero, because Core Motion has already removed gravity. What
    is left is accelerometer bias plus any residual tilt error in Apple's
    filter. Reported for diagnostics; the per-rep detrend removes its effect.
    """
    return log["accel"][window[0]:window[1]].mean(axis=0)

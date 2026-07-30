"""
Step 1 — gyro bias from the pre-set pause.

A stationary gyro should read zero. Whatever it reads is bias. Averaging
over a still window gives it directly, no solver required.

That is the theory, and on real captures it is wrong twice over.

First, we log `dm.rotationRate`, which Core Motion has ALREADY bias-corrected
with its own internal estimator. What is left to measure is the residual after
that estimator, not the raw 0.5-2 deg/s turn-on bias this module was written
for.

Second, the residual is smaller than the noise we measure it in. The "stillest"
second of a real capture carries ~7 deg/s peak-to-peak of 6.5 Hz physiological
tremor while the bias being extracted is 0.1-0.9 deg/s. Block-resampled, the
standard error on the mean is 0.16-0.36 deg/s and the spread of the estimate
across captures is 0.33-0.47 deg/s — the same number. The capture-to-capture
variation IS the tremor.

Subtracting a noise sample as though it were a bias injects the error it was
meant to remove. Applying this estimate was worse than doing nothing on 13 of
the 13 captures held when it was measured, taking the median per-rep horizontal
residual from 4.3 cm to 55.0 cm. (`data/raw/` holds 17 rep-labelled captures
now: the room and warm-up ones were dropped in 7004c32 for having no video, and
the 2026-07-30 session added seven. The gate still holds on all 17.)

A significance gate was tried first — correct an axis only where the estimate
stands clear of the standard error of its own mean — and it failed. It passed
on 4 of 10 captures and made every one of those 4 worse (bench_90x4_1
3.5 -> 66.7 cm, deadlift_180x3 4.1 -> 95.6 cm). The reason is instructive: SNR
asks whether the mean is reproducible within the window, not whether it is
BIAS. A lifter holding a loaded bar for three seconds is genuinely rotating
slowly, that rotation is coherent across the window, and so a significance test
actively selects for it. Tuning the threshold until nothing passed would have
been choosing a number to produce a conclusion.

So the correction is off by default. `gyro_bias` measures and reports; it does
not apply. Core Motion has already removed the part of the bias that is
removable, and nothing we can measure in a 1-3 s hold improves on that.

To turn it back on you need `apply=True` AND a reason. The reason this file
would accept: a capture with a hold long enough and quiet enough that the
estimate is not confounded with real wrist rotation — which is what the
post-set stillness hold in the watch logger is for, since two anchors 40 s
apart measure drift over a baseline where real rotation cancels and bias does
not.

Falsifiable: if `apply=True` ever scores better than the default on a real
capture, this reasoning is wrong and the default should change.

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


def bias_sem(seg: np.ndarray, fs: float, block_s: float = 0.2) -> np.ndarray:
    """Standard error of the mean of `seg`, per axis, accounting for tremor.

    Physiological tremor is ~6.5 Hz and strongly correlated sample to sample,
    so the naive std/sqrt(N) understates the error on the mean by roughly the
    square root of the samples-per-tremor-cycle. Averaging in blocks longer
    than a tremor period first, then taking the SEM of the block means, gives
    an honest number: on real captures it lands at 0.16-0.36 deg/s, which is
    the same size as the bias being estimated.
    """
    n_block = max(int(round(block_s * fs)), 2)
    n_blocks = len(seg) // n_block
    if n_blocks < 2:
        return np.full(seg.shape[1], np.inf)
    means = seg[:n_blocks * n_block].reshape(n_blocks, n_block, -1).mean(axis=1)
    return means.std(axis=0, ddof=1) / np.sqrt(n_blocks)


def gyro_bias(log: dict, search_s: float = 3.0, window_s: float = 1.0,
              fallback: np.ndarray | None = None,
              max_rate: float = 0.05,
              apply: bool = False) -> tuple[np.ndarray, dict]:
    """Measure gyro bias from the pre-set pause, rad/s.

    Returns ZERO by default. The measurement is always made and always
    reported in `info`; `apply=True` opts in to actually using it, and on
    every real capture collected so far that is the wrong choice. See the
    module docstring for the evidence.

    `max_rate` is the stillness gate: if the stillest window still averages
    more motion than this, the user never held still. Fall back rather than
    block — never let calibration stop somebody lifting.

    info carries:
        raw          the estimate, always, whether applied or not
        sem_rad_s    block-resampled standard error of that estimate
        snr          |raw| / sem, per axis
        applied      whether `raw` was actually returned as `bias`
    """
    i, j = stillest_window(log, search_s, window_s)
    seg = log["gyro"][i:j]
    raw = seg.mean(axis=0)

    residual = float(np.linalg.norm(seg - raw, axis=1).mean())
    ok = residual < max_rate

    sem = bias_sem(seg, log["fs"])
    snr = np.abs(raw) / np.where(sem > 0, sem, np.inf)

    used_fallback = bool(not ok and fallback is not None)
    if used_fallback:
        bias = np.asarray(fallback, dtype=float)
    elif apply:
        bias = raw
    else:
        bias = np.zeros(3)

    return bias, {
        "window": (i, j),
        "residual_rad_s": residual,
        "confident": bool(ok),
        "used_fallback": used_fallback,
        "raw": raw,
        "sem_rad_s": sem,
        "snr": snr,
        "applied": bool(apply or used_fallback),
    }


def initial_tilt(log: dict, window: tuple[int, int]) -> np.ndarray:
    """Mean measured (body-frame) acceleration over the still window, m/s^2.

    Should be ~zero, because Core Motion has already removed gravity. What is
    left is accelerometer bias plus the gyro bias's gravity leak, which during
    the pause has not yet been corrected. Because of that leak this is NOT a
    clean accel-bias estimate — use `accel_bias`, which measures on the
    reconstructed world acceleration where the leak is already gone. Reported
    for diagnostics only.
    """
    return log["accel"][window[0]:window[1]].mean(axis=0)


def accel_bias(world_accel: np.ndarray, log: dict,
               search_s: float = 3.0, window_s: float = 1.0) -> np.ndarray:
    """Accelerometer bias in the WORLD frame, m/s^2, from the pre-set pause.

    Call AFTER orient.to_world. The bar is still during the pause, so the mean
    world-frame acceleration there is the accel bias — gravity is gone (Core
    Motion) and the gyro bias's gravity leak is gone (attitude reconstruction).
    That is why it must be measured on the reconstructed world acceleration and
    not on raw userAcceleration, whose pause mean is dominated by the leak.

    Unlike gyro bias, this is NOT cleaned up by the per-rep detrend. The bias
    is fixed in the body frame and the forearm rotates through the rep, so in
    the world frame it varies with the motion rather than appearing as the
    removable ramp a per-rep line can subtract. That is P3, and this docstring
    is what CLAUDE.md cites for it.

    What subtracting this constant buys is far less than was once claimed. The
    previous claim — that it "brings the horizontal within spec", ~1.3 cm of
    residual bow dropping under the 1 cm target — came from synthetic data,
    where the injected bias IS a world-frame constant and so this correction is
    exact by construction. Measured against video by metrics.vs_truth, the
    horizontal error remaining after this stage is 5.1-15.4 cm rms per rep.

    The correction removes the constant PART of a body-frame bias; the part
    that rotates with the forearm survives it, and that part is the problem.
    A3 shows the survivor's shape directly — a single smooth arch across each
    rep rather than a ramp or noise (analysis/19).
    """
    i, j = stillest_window(log, search_s, window_s)
    return world_accel[i:j].mean(axis=0)

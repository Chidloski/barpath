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

THAT MEASUREMENT HAS NOW BEEN MADE, and it settles the question in the
default's favour. `anchor_tilt` below propagates the logged gyro across a whole
set and compares it with Core Motion's own attitude: the disagreement is
0.35-1.49 deg over 39-56 s, median 0.69, which is an effective drift rate of
about 0.014 deg/s. The pause estimate is 0.1-0.9 deg/s. It is 10-60x too large,
measured over a baseline forty times longer than the pause, and applying it
would inject roughly that factor of error. The default stands on evidence now
rather than on an A/B between two bad options.

Falsifiable: if `apply=True` ever scores better than the default on a real
capture, this reasoning is wrong and the default should change.

We do not ask the user to be perfectly still. We ask for three seconds and
then find the stillest part ourselves.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from .io import G


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
    is what `FINDINGS.md` cites for it.

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


def hold_windows(log: dict, span_s: float = 1.5) -> dict:
    """The quietest `span_s` inside each C3 hold. None where there is no hold.

    Returns {"open": slice-index array or None, "close": ... }. Scored on gyro
    magnitude rather than acceleration, because the thing being isolated is
    stillness of the WRIST, and acceleration during a hold is already the
    quantity under test.

    Only the 2026-07-30 captures onward carry `phase`; older ones return None
    for both and the caller must say so rather than falling back to
    `stillest_window`, which searches the opening seconds and cannot find a
    CLOSING hold at all.
    """
    phase = log.get("phase")
    out: dict = {"open": None, "close": None}
    if phase is None:
        return out

    n = int(span_s * log["fs"])
    for name, label in (("open", 0), ("close", 2)):
        idx = np.flatnonzero(phase == label)
        if len(idx) < n + 2:
            continue
        mag = np.linalg.norm(log["gyro"][idx], axis=1)
        c = np.concatenate([[0.0], np.cumsum(mag)])
        k = int(np.argmin((c[n:] - c[:-n]) / n))
        out[name] = idx[k:k + n]
    return out


def anchor_tilt(log: dict, world_accel: np.ndarray, span_s: float = 1.5) -> dict:
    """C6 — Core Motion's attitude error at each end of a set, in degrees.

    THE MEASUREMENT C1 WAS BUILT FOR. During a still hold the world-frame
    acceleration must be zero: Core Motion removed gravity using its own
    attitude, so a tilt error theta leaves g*sin(theta) in the world horizontal
    (orient.py's docstring derives this). The opening and closing holds bracket
    ~40-55 s of loaded lifting, so the difference between them is what a
    working set does to the attitude solution.

    Returns degrees at each anchor, the change, and `gyro_only` — the angle
    between Core Motion's reported attitude at the closing anchor and one
    obtained by integrating the logged gyro from the opening anchor. That last
    number is how much work the fusion did: it is what the attitude WOULD have
    drifted on gyro alone.

    Measured on the seven 2026-07-30 captures: 0.05 deg at the opening anchor,
    0.14 deg at the closing anchor, against 0.69 deg of gyro-only drift over
    the same span. The fusion is correcting, and winning, THROUGH a set with
    20 g impacts in it.

    THREE LIMITS, and they matter more than the result.

    1. `open_deg` and `close_deg` are UPPER BOUNDS on tilt error, not
       measurements of it. The world-frame residual is the tilt leak plus the
       body-frame accel bias rotated into the world, and 0.0025 g of accel bias
       — what a watch on a table shows — is g*sin(0.143 deg), which is the
       closing-anchor median itself. The true tilt could be zero.

    2. `change_deg` is not a result. It is returned because it is the obvious
       thing to look at, and it should not be read as degradation across the
       set: the watch is not in the same posture at the two anchors (measured,
       3.5-161 deg between them), so the accel-bias term projects differently
       at each end and moves this number on its own.

    3. This is TILT only — two of three degrees of freedom. Gravity says
       nothing about yaw, and the logger requests `.xArbitraryZVertical`, so no
       absolute yaw reference exists anywhere in the system. Yaw error is
       unobservable here; it is bounded indirectly at 0.0-1.4 deg per set by
       the yaw part of `gyro_only_deg`, which is 2.4 mm on a 10 cm excursion
       and so below the spec.

    And the standing limit on the design: the anchors sample the attitude at
    the two moments it is most likely to be right — still, with no linear
    acceleration to corrupt the gravity reference. A good number here does NOT
    say the attitude holds during a rep, and P3's error lives during the rep.
    This measures that a set does no LASTING damage, which is a different and
    smaller claim than the one C1 was hoped to settle.
    """
    holds = hold_windows(log, span_s)
    if holds["open"] is None or holds["close"] is None:
        raise ValueError(
            "anchor_tilt needs a capture with both C3 holds — the `phase` "
            "column exists only from 2026-07-30 on. Older captures have no "
            "closing hold to anchor against.")

    def tilt(win):
        h = world_accel[win, :2].mean(axis=0)
        return float(np.degrees(np.arcsin(np.clip(
            np.linalg.norm(h) / G, -1.0, 1.0)))), h

    open_deg, open_h = tilt(holds["open"])
    close_deg, close_h = tilt(holds["close"])

    i0 = int(holds["open"][len(holds["open"]) // 2])
    i1 = int(holds["close"][len(holds["close"]) // 2])
    q = _as_scipy(log["quat"][i0])
    for k in range(i0, i1):
        q = q * Rotation.from_rotvec(log["gyro"][k] * log["dt"][k])
    gyro_only = float(np.atleast_1d(np.degrees(
        (q.inv() * _as_scipy(log["quat"][i1])).magnitude()))[0])

    return {
        "open_deg": open_deg,
        "close_deg": close_deg,
        "change_deg": close_deg - open_deg,
        "gyro_only_deg": gyro_only,
        "span_s": float(log["t"][i1] - log["t"][i0]),
        "open_horizontal": open_h,
        "close_horizontal": close_h,
    }


def _as_scipy(quat) -> Rotation:
    """w,x,y,z (this project) -> x,y,z,w (SciPy). See CLAUDE.md Conventions."""
    q = np.atleast_2d(quat)
    return Rotation.from_quat(np.column_stack([q[:, 1], q[:, 2], q[:, 3], q[:, 0]]))

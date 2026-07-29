"""
Log I/O.

One CSV format shared by the watch logger and the synthetic generator, so
the pipeline never knows or cares which it is reading.

Columns
-------
t                 seconds. Core Motion's timestamp is seconds since boot,
                  so only differences are meaningful. We rebase to zero on
                  load but keep the true spacing.
qw qx qy qz       attitude quaternion, body -> world
ax ay az          userAcceleration, UNITS OF g, Core Motion's SIGN
gx gy gz          rotationRate, rad/s

The file holds exactly what the watch reported. `load_log` converts to the
convention the pipeline works in — units AND sign — and it is the only place
that conversion happens.

The sign matters and it cost a full day. Core Motion's `userAcceleration` is
the NEGATIVE of the device's physical acceleration: move the watch upwards and
the reported z goes negative. Every stage downstream assumes the physics
convention, where acceleration points the way the thing is actually going, so
the negation belongs here at the boundary.

How it was missed for so long: at rest `userAcceleration` is zero, so its sign
is invisible. Every check that had been run — gravity direction during the
calibration pause, `to_world` returning ~0 while still, the synthetic
round-trip — was run somewhere the term vanishes. `synth.py` encoded the same
wrong convention, so the generator and the pipeline agreed with each other and
disagreed with the watch, which is exactly the failure the synthetic gates
cannot see.

Caught by video: integrating world acceleration over 0.2 s windows correlated
-0.76 with the tracked bar, and flipped to +0.76 negated. Confirmed
independently by the floor impact, where the measured velocity step was
negative on all 9 impacts across two captures while the floor decelerating a
falling bar demands positive.

The floor impact, and what B5 found
-----------------------------------
The impact is a 20-30 ms event at 15-21 g, which at 100 Hz is 2-3 samples. That
looks like it must lose the impulse, and it does not: measured against the
video, the integrated velocity step across an impact comes out at a ratio of
0.77-1.19 on both 155 kg captures, median 1.04 over all fifteen. The impulse
survives.

Two traps worth recording, because the first version of this measurement fell
into both. Do NOT predict the arrival velocity as sqrt(2*g*h) — a touch-and-go
deadlift is lowered under control with the hands on the bar and arrives at
about 2 m/s, not the 3.3 a free fall from lockout would give. And do not
measure the step as a net change across a fixed window, which spans the rise
AND the fall into the next descent. Against those two mistakes the impulse
appears 80% missing. The video is the only arrival-velocity truth here.

`deadlift_180x3` is the exception: it over-reads the step by 58-72%, alone
among the three, and it is also the worst capture by horizontal error
(15.4 cm against 5.1 and 9.2). Heaviest bar, hardest landing, most strap ring —
see TASKS.md B5 and #14.

Nothing here clips; see `clipped_runs`.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

COLUMNS = ["t", "qw", "qx", "qy", "qz", "ax", "ay", "az", "gx", "gy", "gz"]

# C2, and OPTIONAL. The watch logger appends these; the ten captures recorded
# before it did not have them, and synth.py does not emit them. Absent means
# `raw_gyro` is None rather than an error.
RAW_GYRO_COLUMNS = ["rgt", "rgx", "rgy", "rgz"]

G = 9.80665


def save_log(path: str | Path, data: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(data["t"])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i in range(n):
            w.writerow([f"{data[c][i]:.9g}" for c in COLUMNS])
    return path


def load_log(path: str | Path) -> dict:
    """Load a log into arrays.

    Returns a dict with:
        t      (N,)   seconds, rebased so t[0] == 0
        dt     (N,)   per-sample interval. NOT assumed constant — the watch
                      does not always honour the requested rate exactly, and
                      assuming a fixed dt is a real source of scale error.
        quat   (N,4)  w, x, y, z
        accel  (N,3)  m/s^2, PHYSICS sign (converted from g and negated on
                      load — see the module docstring)
        gyro   (N,3)  rad/s, as reported — Core Motion has ALREADY removed its
                      own bias estimate from this
        fs     float  median sample rate, for reference only

    And, only when the log carries them (C2, watch logger from 2026-07-29 on):

        raw_gyro      (N,3)  rad/s, NOT bias-corrected
        raw_gyro_lag  (N,)   seconds between the paired raw and device-motion
                             samples. The two streams arrive on separate
                             callbacks, so `gyro - raw_gyro` is only Core
                             Motion's bias estimate to the extent this is small
                             — check it before trusting the difference.

    Both are None on the ten captures recorded before that and on synth output.
    """
    raw = np.genfromtxt(path, delimiter=",", names=True)
    t = np.asarray(raw["t"], dtype=float)
    t0 = t[0]
    t = t - t0

    dt = np.empty_like(t)
    dt[1:] = np.diff(t)
    dt[0] = dt[1] if len(t) > 1 else 0.01

    quat = np.column_stack([raw["qw"], raw["qx"], raw["qy"], raw["qz"]])
    # Negated: Core Motion's userAcceleration is the negative of the device's
    # physical acceleration. See the module docstring for how this was found.
    accel = -np.column_stack([raw["ax"], raw["ay"], raw["az"]]) * G
    gyro = np.column_stack([raw["gx"], raw["gy"], raw["gz"]])

    have_raw = all(c in (raw.dtype.names or ()) for c in RAW_GYRO_COLUMNS)
    raw_gyro = raw_lag = None
    if have_raw:
        raw_gyro = np.column_stack([raw["rgx"], raw["rgy"], raw["rgz"]])
        raw_lag = np.asarray(raw["rgt"], dtype=float) - t0 - t
        if np.isnan(raw_gyro).all():
            raw_gyro = raw_lag = None      # column present, never populated

    return {
        "t": t,
        "dt": dt,
        "quat": quat,
        "accel": accel,
        "gyro": gyro,
        "raw_gyro": raw_gyro,
        "raw_gyro_lag": raw_lag,
        "fs": float(1.0 / np.median(dt[1:])) if len(t) > 1 else 100.0,
    }


def core_motion_gyro_bias(log: dict) -> np.ndarray | None:
    """Core Motion's own gyro bias estimate, by difference. C2, needs raw gyro.

    `dm.rotationRate` is already bias-corrected and `CMGyroData.rotationRate` is
    not, so their difference is the estimate Core Motion applied — the opaque,
    time-varying quantity P5 says we cannot otherwise see. Returns None when the
    log predates C2.

    **The sign convention is unverified.** If Core Motion computes
    `corrected = raw - bias` then bias is `raw - corrected`, which is what this
    returns. Nobody has confirmed that against a capture yet, so check it on the
    first C2 log before building anything on the sign: a stationary watch should
    give a bias of the right ORDER (0.1-0.9 deg/s) and a consistent direction.
    """
    if log.get("raw_gyro") is None:
        return None
    return log["raw_gyro"] - log["gyro"]


def clipped_runs(accel: np.ndarray, min_run: int = 2) -> int:
    """Samples sitting on a per-axis rail, i.e. genuinely clipped. B5.

    A magnitude threshold cannot answer "did the sensor saturate?" — it only
    answers "was the reading large?", and those differ. What clipping actually
    looks like is a RAIL: consecutive samples pinned at one identical extreme
    value while the true signal keeps going, so the waveform flat-tops.

    A real transient visits its peak once and lands on an arbitrary value. On
    `deadlift_180x3`, which peaks at 21.78 g and used to trip a 16 g warning,
    every per-axis extreme is hit by exactly ONE sample and none of them is a
    round number. Nothing in `data/raw/` is clipped.

    Counts samples in runs of `min_run` or more at an axis extreme.
    """
    total = 0
    for k in range(accel.shape[1]):
        x = accel[:, k]
        for extreme in (x.max(), x.min()):
            at = x == extreme
            if at.sum() < min_run:
                continue
            # Longest consecutive run at the rail.
            idx = np.flatnonzero(at)
            breaks = np.flatnonzero(np.diff(idx) != 1)
            runs = np.diff(np.r_[-1, breaks, len(idx) - 1])
            total += int(runs[runs >= min_run].sum())
    return total


def check_log(log: dict) -> list[str]:
    """Cheap sanity checks. Returns a list of warnings, empty if clean."""
    warn = []
    dt = log["dt"][1:]
    if dt.std() / dt.mean() > 0.15:
        warn.append(f"irregular sampling: dt cv = {dt.std()/dt.mean():.2f}")
    if np.abs(np.linalg.norm(log["quat"], axis=1) - 1).max() > 1e-3:
        warn.append("quaternions not unit norm")

    # Was a 0.95 * 16 g magnitude threshold. The 16 g was an assumption about
    # a sensor nobody had checked, and it fired on deadlift_180x3 for reading
    # 21.8 g — which the watch measured perfectly well. See clipped_runs.
    n = clipped_runs(log["accel"])
    if n:
        warn.append(f"accelerometer CLIPPED: {n} samples railed at full scale")

    # C2 pairing quality. `gyro - raw_gyro` is only Core Motion's bias estimate
    # if the two samples are close in time; at 100 Hz a lag over ~15 ms means the
    # difference is dominated by real rotation instead.
    lag = log.get("raw_gyro_lag")
    if lag is not None:
        worst = float(np.nanmax(np.abs(lag)))
        if worst > 0.015:
            warn.append(f"raw gyro pairing lag up to {worst*1000:.0f} ms — "
                        f"gyro minus raw_gyro is not a clean bias estimate")

    # C1. No closing stillness means only one gravity anchor, which is the
    # limitation P4 is about: a single 1-3 s window cannot separate bias from
    # tremor. Cheap to check here rather than discovering it during analysis.
    if len(log["t"]) > 1 and log["t"][-1] > 5.0:
        tail = log["t"] > log["t"][-1] - 2.0
        if np.linalg.norm(log["gyro"][tail], axis=1).mean() > 0.05:
            warn.append("no closing stillness hold — single-anchor capture, so "
                        "gyro bias cannot be measured over a long baseline (C1)")

    n_brief, peak = brief_transients(log["accel"], log["fs"])
    if n_brief:
        warn.append(
            f"{n_brief} high-g transients at the sample rate's limit (peak "
            f"{peak:.1f} g). Their impulse is captured (median 1.04 against "
            f"video) but a hard landing can over-read it by 60%. See B5")
    return warn


def brief_transients(accel: np.ndarray, fs: float,
                     g_threshold: float = 8.0,
                     min_ms: float = 50.0) -> tuple[int, float]:
    """High-g excursions spanning only a few samples. B5.

    Returns (count, peak in g). A statement about the LOG, decidable here with
    no knowledge of what the lifter was doing: an excursion above `g_threshold`
    lasting less than `min_ms` is carried by a handful of samples, which is the
    regime where the sample rate starts to matter.

    It does NOT follow that the impulse is lost. Measured against video, the
    integrated velocity step across a floor impact matches at a ratio of
    0.77-1.19 on both 155 kg captures. What this flags is that the event is at
    the limit of what 100 Hz represents, not that it was mis-measured — with
    `deadlift_180x3` the exception, over-reading by 58-72%.

    Deliberately NOT phrased as "floor impacts". Nothing at this layer knows
    what caused a transient — a squat re-rack trips this too — and brevity is a
    property of the event's duration, not its cause.
    """
    mag = np.linalg.norm(accel, axis=1) / G
    above = mag > g_threshold
    if not above.any():
        return 0, float(mag.max())

    idx = np.flatnonzero(above)
    breaks = np.flatnonzero(np.diff(idx) != 1)
    lengths = np.diff(np.r_[-1, breaks, len(idx) - 1])
    brief = int((lengths < max(min_ms * fs / 1000.0, 2)).sum())
    return brief, float(mag.max())

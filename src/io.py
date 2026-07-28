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
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

COLUMNS = ["t", "qw", "qx", "qy", "qz", "ax", "ay", "az", "gx", "gy", "gz"]

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
        gyro   (N,3)  rad/s
        fs     float  median sample rate, for reference only
    """
    raw = np.genfromtxt(path, delimiter=",", names=True)
    t = np.asarray(raw["t"], dtype=float)
    t = t - t[0]

    dt = np.empty_like(t)
    dt[1:] = np.diff(t)
    dt[0] = dt[1] if len(t) > 1 else 0.01

    quat = np.column_stack([raw["qw"], raw["qx"], raw["qy"], raw["qz"]])
    # Negated: Core Motion's userAcceleration is the negative of the device's
    # physical acceleration. See the module docstring for how this was found.
    accel = -np.column_stack([raw["ax"], raw["ay"], raw["az"]]) * G
    gyro = np.column_stack([raw["gx"], raw["gy"], raw["gz"]])

    return {
        "t": t,
        "dt": dt,
        "quat": quat,
        "accel": accel,
        "gyro": gyro,
        "fs": float(1.0 / np.median(dt[1:])) if len(t) > 1 else 100.0,
    }


def check_log(log: dict) -> list[str]:
    """Cheap sanity checks. Returns a list of warnings, empty if clean."""
    warn = []
    dt = log["dt"][1:]
    if dt.std() / dt.mean() > 0.15:
        warn.append(f"irregular sampling: dt cv = {dt.std()/dt.mean():.2f}")
    if np.abs(np.linalg.norm(log["quat"], axis=1) - 1).max() > 1e-3:
        warn.append("quaternions not unit norm")
    amax = np.abs(log["accel"]).max()
    if amax > 0.95 * 16 * G:
        warn.append(f"accelerometer near saturation ({amax/G:.1f} g)")
    return warn

"""
Synthetic IMU generator.

This is the keystone of the project. It defines a bar path analytically,
differentiates it twice to get true acceleration, rotates that into a
plausible watch frame, and injects *known* sensor errors.

Because the ground truth is known exactly, you can develop and debug the
entire pipeline without a barbell, a watch, or a gym. When a stage is
wrong, this tells you which stage.

Error model
-----------
Real specific force (what an accelerometer measures) is  f = a - g,
where g = (0, 0, -9.80665) in the world frame. At rest f = (0, 0, +9.81).

Core Motion reports `userAcceleration`, which is Apple's filter subtracting
its *estimate* of gravity. We model that as:

    userAccel_body = R_true^T . f_world  +  b_a  +  R_est^T . g_world

with R_est = R_true . Exp(b_g * t): the reported attitude is the true
attitude corrupted by an integrated gyro bias.

When R_est == R_true this collapses to R^T.a_world + b_a, as it should.
When it doesn't, gravity leaks into the horizontal axes — which is the
dominant error in the whole system and the thing the pipeline exists to fix.

We let the attitude error accumulate freely from t=0. In reality Apple's
filter pulls attitude back toward gravity during quiet periods, so this is
deliberately pessimistic. If the pipeline handles this, it handles reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial.transform import Rotation

G = 9.80665  # m/s^2
DEG = np.pi / 180.0


# --------------------------------------------------------------------------
# Smooth basis functions
# --------------------------------------------------------------------------
# "smootherstep": 6u^5 - 15u^4 + 10u^3.
# Value goes 0 -> 1 over u in [0, 1], with BOTH first and second derivatives
# zero at each end. That matters: it means the synthetic bar starts and stops
# without an acceleration discontinuity, so the signal is physically plausible
# and the stationary periods are genuinely stationary.


def _S(u):
    return 6 * u**5 - 15 * u**4 + 10 * u**3


def _dS(u):
    return 30 * u**4 - 60 * u**3 + 30 * u**2


def _ddS(u):
    return 120 * u**3 - 180 * u**2 + 60 * u


def _ramp(tau, T):
    """0 -> 1 over the whole rep. Returns (value, d/dt, d2/dt2)."""
    u = np.clip(tau / T, 0.0, 1.0)
    return _S(u), _dS(u) / T, _ddS(u) / T**2


def _bump(tau, T):
    """0 -> 1 -> 0 over the interval. Returns (value, d/dt, d2/dt2)."""
    u = np.clip(tau / T, 0.0, 1.0)
    up = u <= 0.5
    v = np.where(up, _S(2 * u), _S(2 * (1 - u)))
    d1 = np.where(up, _dS(2 * u) * 2 / T, -_dS(2 * (1 - u)) * 2 / T)
    d2 = np.where(up, _ddS(2 * u) * 4 / T**2, _ddS(2 * (1 - u)) * 4 / T**2)
    return v, d1, d2


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass
class SetConfig:
    """Everything about the movement being simulated."""

    n_reps: int = 5
    rep_duration: float = 2.2  # s, one full down-up cycle
    rest_between: float = 0.8  # s, stationary at the top between reps
    calib_pause: float = 3.0  # s, the pre-set stillness window

    rom: float = 0.55  # m, vertical range of motion
    forward_amp: float = 0.035  # m, fore-aft excursion at full depth
    loop_width: float = 0.020  # m, extra fore-aft offset on the concentric
    lateral_amp: float = 0.004  # m, side-to-side (should be small)

    # Form breakdown: fore-aft excursion grows linearly across the set.
    drift_per_rep: float = 0.008  # m added to forward_amp per rep index

    # Forearm rotation through the rep, about the watch's mediolateral axis.
    forearm_rot: float = 16.0 * DEG

    # Base orientation of the watch at rest (roll, pitch, yaw in radians).
    base_euler: tuple = (0.0, -0.35, 0.9)


@dataclass
class SensorConfig:
    """Everything about how the sensors corrupt it."""

    fs: float = 100.0  # Hz

    # Gyro bias, rad/s. Consumer turn-on bias is 0.5-2 deg/s.
    gyro_bias: tuple = (0.45 * DEG, -0.70 * DEG, 0.30 * DEG)

    # Accelerometer bias, m/s^2, fixed in the body frame.
    accel_bias: tuple = (0.020, -0.015, 0.025)

    # White noise, per-sample standard deviation.
    accel_noise: float = 0.010  # m/s^2
    gyro_noise: float = 0.0012  # rad/s

    seed: int = 0


@dataclass
class SyntheticSet:
    """Ground truth plus the log a watch would have produced."""

    t: np.ndarray  # (N,)   seconds
    pos_true: np.ndarray  # (N,3) world frame, metres. THE ANSWER.
    acc_true: np.ndarray  # (N,3) world frame, m/s^2
    quat_true: np.ndarray  # (N,4) w,x,y,z  body -> world

    quat_log: np.ndarray  # (N,4) w,x,y,z  what Core Motion would report
    accel_log: np.ndarray  # (N,3) userAcceleration, units of g
    gyro_log: np.ndarray  # (N,3) rotationRate, rad/s

    rep_bounds: list = field(default_factory=list)  # (start, end) index pairs
    fs: float = 100.0


# --------------------------------------------------------------------------
# Trajectory
# --------------------------------------------------------------------------


def _trajectory(cfg: SetConfig, fs: float):
    """Build world-frame position and acceleration analytically.

    World frame: x = forward (anterior), y = lateral (left), z = up.
    """
    dt = 1.0 / fs
    total = cfg.calib_pause + cfg.n_reps * (cfg.rep_duration + cfg.rest_between)
    n = int(round(total * fs))
    t = np.arange(n) * dt

    pos = np.zeros((n, 3))
    acc = np.zeros((n, 3))
    depth = np.zeros(n)  # 0 at top, 1 at bottom — drives forearm rotation
    bounds = []

    for r in range(cfg.n_reps):
        t0 = cfg.calib_pause + r * (cfg.rep_duration + cfg.rest_between)
        i0 = int(round(t0 * fs))
        i1 = int(round((t0 + cfg.rep_duration) * fs))
        bounds.append((i0, i1))

        tau = t[i0:i1] - t0
        T = cfg.rep_duration

        # Vertical: down to full depth at mid-rep, back up. A bump.
        d, dd, ddd = _bump(tau, T)
        pos[i0:i1, 2] = -cfg.rom * d
        acc[i0:i1, 2] = -cfg.rom * ddd

        # Fore-aft: tracks depth, so the excursion peaks at the bottom.
        # Amplitude grows across the set to simulate form breaking down.
        amp = cfg.forward_amp + r * cfg.drift_per_rep
        pos[i0:i1, 0] = amp * d
        acc[i0:i1, 0] = amp * ddd

        # The concentric returns on a different line from the eccentric, so
        # the path is a loop rather than a retrace. Bump over the second half
        # only, which keeps position and both derivatives continuous.
        half = i0 + (i1 - i0) // 2
        tau2 = t[half:i1] - t[half]
        T2 = t[i1 - 1] - t[half] + dt
        w, _, ddw = _bump(tau2, T2)
        pos[half:i1, 0] += cfg.loop_width * w
        acc[half:i1, 0] += cfg.loop_width * ddw

        # Lateral: small, and slightly worse as the set goes on.
        lat = cfg.lateral_amp * (1 + 0.4 * r)
        pos[i0:i1, 1] = lat * d
        acc[i0:i1, 1] = lat * ddd

        depth[i0:i1] = d

    return t, pos, acc, depth, bounds


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------


def generate(set_cfg: SetConfig | None = None,
             sensor_cfg: SensorConfig | None = None) -> SyntheticSet:
    """Produce a synthetic set: ground truth plus a corrupted sensor log."""
    set_cfg = set_cfg or SetConfig()
    sensor_cfg = sensor_cfg or SensorConfig()
    rng = np.random.default_rng(sensor_cfg.seed)
    fs = sensor_cfg.fs
    dt = 1.0 / fs

    t, pos, acc, depth, bounds = _trajectory(set_cfg, fs)
    n = len(t)

    # --- true attitude -----------------------------------------------------
    # Watch sits at a fixed base orientation, then the forearm rotates through
    # the rep in proportion to depth, about the watch's own y axis.
    R0 = Rotation.from_euler("xyz", set_cfg.base_euler)
    theta = set_cfg.forearm_rot * depth
    axis = np.zeros((n, 3))
    axis[:, 1] = theta
    R_true = R0 * Rotation.from_rotvec(axis)

    # Body-frame angular velocity is just d(theta)/dt about that same axis.
    omega = np.zeros((n, 3))
    omega[1:, 1] = np.diff(theta) / dt
    omega[0, 1] = omega[1, 1]

    # --- attitude as Core Motion would report it ---------------------------
    b_g = np.asarray(sensor_cfg.gyro_bias)
    drift_rotvec = np.outer(t, b_g)  # integrated bias, body frame
    R_log = R_true * Rotation.from_rotvec(drift_rotvec)

    # --- specific force ----------------------------------------------------
    g_world = np.array([0.0, 0.0, -G])
    f_world = acc - g_world  # at rest this is (0, 0, +G)

    b_a = np.asarray(sensor_cfg.accel_bias)
    f_body = R_true.inv().apply(f_world) + b_a
    g_body_est = R_log.inv().apply(g_world)
    user_accel = f_body + g_body_est  # Apple's gravity subtraction

    user_accel += rng.normal(0.0, sensor_cfg.accel_noise, (n, 3))
    gyro = omega + b_g + rng.normal(0.0, sensor_cfg.gyro_noise, (n, 3))

    def _wxyz(R):
        q = R.as_quat()  # scipy gives x, y, z, w
        return np.column_stack([q[:, 3], q[:, 0], q[:, 1], q[:, 2]])

    return SyntheticSet(
        t=t,
        pos_true=pos,
        acc_true=acc,
        quat_true=_wxyz(R_true),
        quat_log=_wxyz(R_log),
        accel_log=user_accel / G,  # Core Motion reports in units of g
        gyro_log=gyro,
        rep_bounds=bounds,
        fs=fs,
    )


def to_log_dict(s: SyntheticSet) -> dict:
    """Shape a SyntheticSet like a real watch log, for io.save_log."""
    return {
        "t": s.t,
        "qw": s.quat_log[:, 0], "qx": s.quat_log[:, 1],
        "qy": s.quat_log[:, 2], "qz": s.quat_log[:, 3],
        "ax": s.accel_log[:, 0], "ay": s.accel_log[:, 1],
        "az": s.accel_log[:, 2],
        "gx": s.gyro_log[:, 0], "gy": s.gyro_log[:, 1],
        "gz": s.gyro_log[:, 2],
    }


if __name__ == "__main__":
    s = generate()
    print(f"{len(s.t)} samples, {s.t[-1]:.1f} s, {len(s.rep_bounds)} reps")
    print(f"vertical ROM      {-s.pos_true[:, 2].min() * 100:.1f} cm")
    print(f"fore-aft excursion {s.pos_true[:, 0].max() * 100:.1f} cm")

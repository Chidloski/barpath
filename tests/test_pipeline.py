"""
Milestone gates.

Tests 1-2 pass now. Tests 3-6 fail with NotImplementedError until the
reserved modules are written, and they are ordered so that each one becomes
passable as you work through the pipeline. That is the intended loop: pick
the first failing test, make it pass, commit.

Run:  pytest tests/ -v
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import calibrate, correct, integrate, io, orient, project, segment, synth  # noqa: E402
from src.synth import DEG, G, SensorConfig, SetConfig  # noqa: E402

CLEAN = SensorConfig(gyro_bias=(0, 0, 0), accel_bias=(0, 0, 0),
                     accel_noise=0.0, gyro_noise=0.0)


def as_log(s):
    """Turn a SyntheticSet into the dict shape the pipeline consumes."""
    d = synth.to_log_dict(s)
    dt = np.empty_like(s.t)
    dt[1:] = np.diff(s.t)
    dt[0] = dt[1]
    return {
        "t": s.t, "dt": dt,
        "quat": s.quat_log,
        "accel": s.accel_log * G,
        "gyro": s.gyro_log,
        "fs": s.fs,
    }


# ---------------------------------------------------------------- gate 1 --
def test_synth_is_self_consistent():
    """Zero error injected: the log must encode the true trajectory exactly."""
    from scipy.spatial.transform import Rotation

    s = synth.generate(sensor_cfg=CLEAN)
    q = s.quat_log
    R = Rotation.from_quat(np.column_stack([q[:, 1], q[:, 2], q[:, 3], q[:, 0]]))
    a_world = R.apply(s.accel_log * G)
    assert np.abs(a_world - s.acc_true).max() < 1e-9


def test_log_roundtrip(tmp_path):
    s = synth.generate()
    p = io.save_log(tmp_path / "x.csv", synth.to_log_dict(s))
    log = io.load_log(p)
    assert len(log["t"]) == len(s.t)
    assert np.abs(log["accel"] / G - s.accel_log).max() < 1e-6
    assert io.check_log(log) == []


# ---------------------------------------------------------------- gate 2 --
def test_gyro_bias_recovered():
    """The pause must recover injected bias to well under the in-run floor."""
    true_bias = np.array([0.45, -0.70, 0.30]) * DEG
    s = synth.generate(sensor_cfg=SensorConfig(gyro_bias=tuple(true_bias)))
    b, info = calibrate.gyro_bias(as_log(s))
    assert info["confident"]
    assert np.abs(b - true_bias).max() < 0.01 * DEG


def test_calibration_falls_back_rather_than_blocking():
    s = synth.generate(sensor_cfg=SensorConfig(gyro_noise=0.5))
    fb = np.array([0.01, 0.0, 0.0])
    b, info = calibrate.gyro_bias(as_log(s), fallback=fb)
    assert info["used_fallback"] and np.allclose(b, fb)


# ---------------------------------------------------------------- gate 3 --
def test_attitude_correction_recovers_truth():
    """orient.correct_attitude must undo the integrated gyro bias."""
    s = synth.generate(sensor_cfg=SensorConfig(accel_noise=0, gyro_noise=0))
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log)
    q = orient.correct_attitude(log, b)
    dot = np.abs(np.sum(q * s.quat_true, axis=1))
    assert np.degrees(2 * np.arccos(np.clip(dot, 0, 1))).max() < 0.5


def test_world_frame_acceleration_exact():
    s = synth.generate(sensor_cfg=CLEAN)
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"])
    assert np.abs(a - s.acc_true).max() < 1e-9


# ---------------------------------------------------------------- gate 4 --
def test_integration_recovers_clean_path():
    """Trapezoidal, no error injected: sub-millimetre."""
    s = synth.generate(sensor_cfg=CLEAN)
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"])
    _, p = integrate.integrate(a, log["dt"])
    assert np.abs(p - s.pos_true).max() < 1e-3


def test_uncorrected_gyro_bias_blows_up():
    """Deliberately observe the failure. 1 deg/s must wreck the horizontal."""
    s = synth.generate(sensor_cfg=SensorConfig(
        gyro_bias=(1.0 * DEG, 0, 0), accel_noise=0, gyro_noise=0))
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"])  # NO bias correction
    _, p = integrate.integrate(a, log["dt"])
    assert np.abs(p[:, :2] - s.pos_true[:, :2]).max() > 0.15


# ---------------------------------------------------------------- gate 5 --
def test_segmentation_finds_every_rep():
    s = synth.generate()
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], q)
    _, p = integrate.integrate(a, log["dt"])
    bounds = segment.rep_bounds(log, p[:, 2], lift="squat")
    assert len(bounds) == len(s.rep_bounds)
    for (a0, _), (b0, _) in zip(bounds, s.rep_bounds):
        assert abs(a0 - b0) < 0.15 * s.fs


def test_mid_rep_pause_is_not_a_boundary():
    """The synthetic bar is momentarily stationary at full depth every rep —
    velocity AND acceleration both go to zero at the turnaround, exactly like
    a grind or a paused bench. The detector should see it as stationary; the
    classifier must not mistake it for a rep boundary."""
    s = synth.generate()
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], q)
    _, p = integrate.integrate(a, log["dt"])

    windows = segment.runs(segment.stationary_mask(log))
    assert len(windows) > len(s.rep_bounds), "turnaround pauses not detected"

    bounds = segment.rep_bounds(log, p[:, 2], lift="squat")
    depths = [p[i0:i1, 2].min() for i0, i1 in s.rep_bounds]
    for start, _ in bounds:
        assert p[start, 2] > 0.5 * max(depths), "boundary placed at full depth"


# ---------------------------------------------------------------- gate 6 --
def test_full_pipeline_meets_spec():
    """THE GATE. Realistic bias and noise, recovered to under 1 cm."""
    s = synth.generate()
    log = as_log(s)

    b, _ = calibrate.gyro_bias(log)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], q)
    _, p = integrate.integrate(a, log["dt"])
    bounds = segment.rep_bounds(log, p[:, 2], lift="squat")
    reps = correct.detrend_set(p, bounds)

    for (a0, b0), rep in zip(bounds, reps):
        truth = s.pos_true[a0:b0] - s.pos_true[a0]
        n = min(len(truth), len(rep))
        assert np.abs(rep[:n, :2] - truth[:n, :2]).max() < 0.01


def test_principal_axis_finds_the_sagittal_plane():
    """Synthetic fore-aft excursion is ~10x the lateral, so PCA must find it."""
    s = synth.generate()
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], q)
    _, p = integrate.integrate(a, log["dt"])
    bounds = segment.rep_bounds(log, p[:, 2], lift="squat")
    reps = correct.detrend_set(p, bounds)

    axis, ratio, excursion = project.principal_axis(reps)
    assert ratio > 3.0
    assert abs(abs(float(axis[0])) - 1.0) < 0.2  # world x is fore-aft

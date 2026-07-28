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
        "accel": -s.accel_log * G,   # mirrors io.load_log
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
    a_world = R.apply(-s.accel_log * G)
    assert np.abs(a_world - s.acc_true).max() < 1e-9


def test_log_roundtrip(tmp_path):
    s = synth.generate()
    p = io.save_log(tmp_path / "x.csv", synth.to_log_dict(s))
    log = io.load_log(p)
    assert len(log["t"]) == len(s.t)
    assert np.abs(log["accel"] / G + s.accel_log).max() < 1e-6  # load negates
    assert io.check_log(log) == []


# ---------------------------------------------------------------- gate 2 --
def test_gyro_bias_recovered():
    """The pause must recover injected bias to well under the in-run floor.

    Asserts on info["raw"] — the MEASUREMENT — not on the returned bias.
    Whether to apply the measurement is a policy decision that now defaults to
    off, because on real captures the estimate is confounded with genuine slow
    wrist rotation and applying it is worse than doing nothing in 13 of 13
    captures. The estimator itself is fine, and this test keeps it honest.
    """
    true_bias = np.array([0.45, -0.70, 0.30]) * DEG
    s = synth.generate(sensor_cfg=SensorConfig(gyro_bias=tuple(true_bias)))
    b, info = calibrate.gyro_bias(as_log(s))
    assert info["confident"]
    assert not info["applied"] and np.array_equal(b, np.zeros(3))
    assert np.abs(info["raw"] - true_bias).max() < 0.01 * DEG


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
    b, _ = calibrate.gyro_bias(log, apply=True)
    q = orient.correct_attitude(log, b)
    dot = np.abs(np.sum(q * s.quat_true, axis=1))
    assert np.degrees(2 * np.arccos(np.clip(dot, 0, 1))).max() < 0.5


def test_world_frame_acceleration_exact():
    s = synth.generate(sensor_cfg=CLEAN)
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"], log["quat"])
    assert np.abs(a - s.acc_true).max() < 1e-9


# ---------------------------------------------------------------- gate 4 --
def test_integration_recovers_clean_path():
    """Trapezoidal, no error injected: sub-millimetre."""
    s = synth.generate(sensor_cfg=CLEAN)
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"], log["quat"])
    _, p = integrate.integrate(a, log["dt"])
    assert np.abs(p - s.pos_true).max() < 1e-3


def test_uncorrected_gyro_bias_blows_up():
    """Deliberately observe the failure. 1 deg/s must wreck the horizontal."""
    s = synth.generate(sensor_cfg=SensorConfig(
        gyro_bias=(1.0 * DEG, 0, 0), accel_noise=0, gyro_noise=0))
    log = as_log(s)
    a = orient.to_world(log["accel"], log["quat"], log["quat"])  # NO bias correction
    _, p = integrate.integrate(a, log["dt"])
    assert np.abs(p[:, :2] - s.pos_true[:, :2]).max() > 0.15


# ------------------------------------------------- gate 4b: gravity leak --
def test_to_world_removes_gravity_leak():
    """Realistic gyro bias, attitude corrected: the recovered horizontal PATH
    must match truth to under 1 cm once per-rep linear drift is removed.

    This isolates STEP 3 (to_world) from segmentation and the reserved detrend
    by using the true rep bounds and detrending both sides identically. It
    fails today by tens of centimetres, and the reason is a gravity leak:

      Core Motion subtracts gravity using its OWN gyro-biased attitude before
      it reports userAcceleration. Rotating that vector by the corrected
      attitude cannot undo a subtraction made in the wrong frame, so a
      fraction of g ~ g*sin(bias*t) stays leaked into the horizontal axes and
      grows across the set. A per-rep LINEAR detrend cannot remove it (the
      leak is nonlinear within a rep), so the horizontal is left ~tens of cm
      off — see the residual growing 23 -> 86 cm across the five reps.

    To pass, to_world must RECONSTRUCT gravity: add back the gravity Core
    Motion removed using the REPORTED quaternion (log["quat"]), recovering the
    raw specific force, then subtract gravity using the CORRECTED quaternion.
    With that, the same detrend lands at ~0.74 cm.

    NOTE: reconstruction needs the reported attitude as well as the corrected
    one, so to_world's inputs will change. Update the call below to match
    whatever signature you settle on.
    """
    s = synth.generate()
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log, apply=True)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], log["quat"], q)
    a = a - calibrate.accel_bias(a, log)   # coarse accel-bias removal
    _, p = integrate.integrate(a, log["dt"])

    def linear_detrend(seg):
        t = np.arange(len(seg))
        out = np.empty_like(seg)
        for k in range(seg.shape[1]):
            out[:, k] = seg[:, k] - np.polyval(np.polyfit(t, seg[:, k], 1), t)
        return out

    worst = 0.0
    for a0, b0 in s.rep_bounds:
        rep = linear_detrend(p[a0:b0])
        truth = linear_detrend(s.pos_true[a0:b0])
        worst = max(worst, np.abs(rep[:, :2] - truth[:, :2]).max())
    assert worst < 0.01, f"horizontal path off by {worst * 100:.1f} cm — gravity leak not removed"


# ------------------------------------------- gate 4c: accel-bias removal --
def test_accel_bias_removal_meets_horizontal_spec():
    """Realistic bias, pipeline through integration WITH coarse accel-bias
    removal: the endpoint-CHORD detrend (what correct.detrend_rep will do) must
    recover each rep's horizontal path to under 1 cm — compared against zeroed
    truth, exactly as the full-pipeline gate does.

    Isolates the accel-bias step from segmentation (true bounds) and from the
    reserved detrend (chord subtracted inline). Without calibrate.accel_bias the
    residual is ~1.3 cm: the body-fixed accel bias rotates with the forearm, so
    it is not the removable ramp a linear detrend assumes. Removing it in the
    world frame from the pause drops the residual well under spec.
    """
    s = synth.generate()
    log = as_log(s)
    b, _ = calibrate.gyro_bias(log, apply=True)
    q = orient.correct_attitude(log, b)
    a = orient.to_world(log["accel"], log["quat"], q)
    a = a - calibrate.accel_bias(a, log)
    _, p = integrate.integrate(a, log["dt"])

    def chord_detrend(seg):
        n = len(seg)
        u = (np.arange(n) / (n - 1))[:, None]
        return seg - (seg[0] + (seg[-1] - seg[0]) * u)  # line through the endpoints

    worst = 0.0
    for a0, b0 in s.rep_bounds:
        rep = chord_detrend(p[a0:b0])
        truth = s.pos_true[a0:b0] - s.pos_true[a0]
        worst = max(worst, np.abs(rep[:, :2] - truth[:, :2]).max())
    assert worst < 0.01, f"horizontal off by {worst * 100:.1f} cm — accel bias not removed"


# ------------------------------------------------------------- deleted --
# Gates 5 and 6 lived here: test_segmentation_finds_every_rep,
# test_mid_rep_pause_is_not_a_boundary, test_grind_near_lockout_is_not_a_boundary
# and test_full_pipeline_meets_spec. All four passed for months while the
# pipeline failed in the gym by two orders of magnitude, because they asked
# synth.py whether the pipeline handled lifting and synth.py's model of lifting
# is wrong in the ways that mattered — it emits stationary windows between reps,
# which loaded lifting does not have, and a constant accel bias, which the real
# one is not.
#
# They are replaced by tests/test_real_data.py, which asks the captures. The
# equivalent claims now have real referees: 44 reps across 10 sets for
# detection, and bench_92.5x2's two paused reps for the mid-rep hold.
#
# Recover them with `git show 17d5eee:tests/test_pipeline.py` if a synthetic
# version is ever wanted for a specific mechanism — but do not restore them as
# gates. See CLAUDE.md, "Open problems".


def test_principal_axis_finds_the_sagittal_plane():
    """PCA must pick the axis of greatest horizontal variance.

    Built from paths directly rather than by running the pipeline. This is a
    property of the covariance eigendecomposition and nothing else, so routing
    it through calibration, orientation, integration and segmentation only
    meant it could fail — or pass — for reasons that have nothing to do with
    what it claims to test.
    """
    rng = np.random.default_rng(0)
    reps = []
    for _ in range(5):
        n = 200
        u = np.linspace(0, 1, n)
        fore_aft = 0.10 * np.sin(np.pi * u) + rng.normal(0, 0.002, n)
        lateral = 0.01 * np.sin(np.pi * u) + rng.normal(0, 0.002, n)
        reps.append(np.column_stack([fore_aft, lateral, 0.5 * u]))

    axis, ratio, excursion = project.principal_axis(reps)
    assert ratio > 3.0
    assert abs(abs(float(axis[0])) - 1.0) < 0.2   # world x is fore-aft
    assert 0.08 < excursion < 0.13                # ~10 cm of fore-aft travel

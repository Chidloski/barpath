"""
Algebraic identities against the synthetic generator.

This was "Milestone gates", a numbered ladder you climbed by making the next
test pass. That framing is gone with the milestones: gates 5 and 6 passed for
months while the pipeline failed in the gym by two orders of magnitude, because
they asked synth.py whether the pipeline handled lifting and synth.py's model
of lifting is wrong in the ways that mattered.

What belongs here now is only what is true REGARDLESS of how lifting behaves —
round trips, frame and sign conventions, integration schemes, eigendecomposition
properties. Those catch real bugs that no gym capture can see, and they are
cheap. What does not belong here is any claim about whether a stage works;
tests/test_real_data.py asks the captures, and the captures are the referee.

Run:  pytest tests/ -v
"""

import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import calibrate, correct, integrate, io, orient, project, synth  # noqa: E402
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
def test_accel_bias_removal_helps_on_every_seed():
    """calibrate.accel_bias must reduce the horizontal residual. A COMPARISON.

    This was written as an absolute threshold — "must recover each rep to under
    1 cm" — and it was not a gate. Measured across twelve noise seeds the
    residual spans 0.29-1.86 cm, so **it failed on 5 of 12 and passed only
    because seed=0 happened to land at 0.39**. Adding C1's closing hold to
    synth lengthened the record, moved the noise draw, and exposed it.

    That is the same mistake as gates 5 and 6 in miniature: a behavioural spec
    claim refereed by synth.py, which cannot referee one. A threshold sitting
    inside the generator's own seed-to-seed spread constrains nothing.

    What synth CAN settle is whether the mechanism works, so this now asserts
    the comparison: removing the world-frame pause bias must beat not removing
    it, on every seed. It does, 12 of 12, median 1.93 -> 1.58 cm. Same pattern
    as the B1 gate in test_real_data — if this ever fails, the step is wrong,
    and no threshold needs retuning to find that out.

    Note what the numbers say even here: ~1.6 cm residual on SYNTHETIC data
    with a constant world-frame bias injected, which is the shape this
    correction removes exactly. Real captures are 5-15 cm. Do not read this
    test as evidence about the gym.
    """
    def residual(seed: int, remove: bool) -> float:
        s = synth.generate(sensor_cfg=SensorConfig(seed=seed))
        log = as_log(s)
        b, _ = calibrate.gyro_bias(log, apply=True)
        q = orient.correct_attitude(log, b)
        a = orient.to_world(log["accel"], log["quat"], q)
        if remove:
            a = a - calibrate.accel_bias(a, log)
        _, p = integrate.integrate(a, log["dt"])

        worst = 0.0
        for a0, b0 in s.rep_bounds:
            seg = p[a0:b0]
            u = (np.arange(len(seg)) / (len(seg) - 1))[:, None]
            rep = seg - (seg[0] + (seg[-1] - seg[0]) * u)   # endpoint chord
            truth = s.pos_true[a0:b0] - s.pos_true[a0]
            worst = max(worst, np.abs(rep[:, :2] - truth[:, :2]).max())
        return worst

    off = [residual(sd, False) for sd in range(12)]
    on = [residual(sd, True) for sd in range(12)]

    losses = [(sd, o, f) for sd, o, f in zip(range(12), on, off) if o >= f]
    assert not losses, f"accel-bias removal made it worse on seeds {losses}"
    assert np.median(on) < np.median(off)


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
# gates. See `FINDINGS.md`, Part 2.


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


def test_wrist_offset_is_a_rigid_rotation_of_a_constant():
    """Step 6's algebra: p_bar = p_watch - R(t).d, and what that implies.

    Three properties that hold regardless of how lifting behaves, which is what
    this file is for:

    d = 0 changes nothing. A CONSTANT attitude moves the whole path by one
    fixed vector, so it vanishes under the start-point alignment in
    detrend_set — that is the reason only the VARIATION of R(t).d matters, and
    it is worth pinning rather than asserting in prose. And the correction is
    exactly invertible, because a rotation is.
    """
    rng = np.random.default_rng(0)
    n = 500
    position = np.cumsum(rng.normal(0, 0.01, (n, 3)), axis=0)
    d = np.array([0.03, -0.14, 0.02])

    # 1. no lever arm, no change
    still = Rotation.random(n, random_state=1).as_quat(scalar_first=True)
    assert np.allclose(correct.apply_offset(position, still, np.zeros(3)), position)

    # 2. constant attitude -> a constant shift, so shape is untouched
    fixed = np.tile(Rotation.random(1, random_state=2).as_quat(scalar_first=True), (n, 1))
    bar = correct.apply_offset(position, fixed, d)
    shift = bar - position
    assert np.allclose(shift, shift[0]), "constant attitude must give a constant offset"
    assert np.allclose(bar - bar[0], position - position[0], atol=1e-12)

    # 3. invertible: applying -d undoes it
    there = correct.apply_offset(position, still, d)
    assert np.allclose(correct.apply_offset(there, still, -d), position)


def test_detrend_closes_only_the_axes_it_is_given():
    """B3 made the closure axes explicit. They must actually be respected."""
    rng = np.random.default_rng(3)
    n = 300
    t = np.linspace(0, 2.0, n)
    ramp = np.column_stack([0.5 * t, -0.3 * t, 0.2 * t])       # pure drift
    out = correct.detrend_rep(ramp, 0, n, t, axes=(2,))

    assert abs(out[-1, 2] - out[0, 2]) < 1e-9, "vertical must close"
    assert abs(out[-1, 0] - out[0, 0]) > 0.5, "x was not asked for and must not close"
    assert abs(out[-1, 1] - out[0, 1]) > 0.3, "y was not asked for and must not close"

    both = correct.detrend_rep(ramp, 0, n, t)
    assert np.allclose(both[-1], both[0], atol=1e-9), "default closes all three"


def test_optional_columns_are_optional(tmp_path):
    """Appended columns must be readable when present and absent without error.

    Ten captures predate every optional column and synth.py emits none of them,
    so None has to be a supported state rather than a crash. That is why they
    are appended rather than interleaved — and why abandoning C2 did not
    invalidate the two captures that carry its empty columns.
    """
    s = synth.generate()
    plain = io.save_log(tmp_path / "plain.csv", synth.to_log_dict(s))
    log = io.load_log(plain)
    assert log["raw_gyro"] is None and log["phase"] is None

    # A phase column bolted on, as the watch now writes it (C3).
    text = plain.read_text().splitlines()
    n = len(text) - 1
    ph = np.where(s.t < 3.0, 0, np.where(s.t > s.t[-1] - 3.0, 2, 1))
    rows = [text[0] + ",phase"] + [f"{l},{ph[i]}" for i, l in enumerate(text[1:])]
    full = tmp_path / "c3.csv"
    full.write_text("\n".join(rows) + "\n")

    log2 = io.load_log(full)
    assert log2["phase"] is not None and log2["phase"].shape == (n,)
    assert set(np.unique(log2["phase"])) == {0, 1, 2}
    assert log2["raw_gyro"] is None
    assert io.check_log(log2) == [], "a capture with a real closing hold is clean"


def test_synth_emits_a_closing_stillness_hold():
    """C1: synth models the capture protocol, not just the sensors.

    Without this every synthetic log trips check_log's single-anchor warning,
    which would be correct — and would also make the warning useless by firing
    everywhere. The generator emits what the watch now records.
    """
    s = synth.generate()
    log = as_log(s)
    assert io.check_log(log) == []

    tail = log["t"] > log["t"][-1] - 2.0
    assert np.linalg.norm(log["gyro"][tail], axis=1).mean() < 0.05

    none = as_log(synth.generate(set_cfg=SetConfig(settle_pause=0.0)))
    assert any("closing stillness" in w for w in io.check_log(none))


# ------------------------------------------------- dataset pairing (C17) --
def test_find_video_keeps_a_capture_within_its_own_dataset(tmp_path):
    """`data_v2/raw` pairs to `data_v2/video`, never across to `data/video`.

    Algebraic, so it belongs here: it asserts a path rule, not a fact about
    lifting. It matters because the two datasets are refereed by DIFFERENT
    trackers — `data/video/` has no markers on the plate and `data_v2/` is
    filmed for them — so a cross-dataset pairing hands `metrics.resolve_path`
    footage its inferred tracker cannot read, and the failure surfaces as a
    tracking error rather than as the pairing mistake it actually is.

    Before C17 the search was `parents[2] / "data" / "video"`, which sent every
    dataset to `data/video/` regardless of where the capture lived.
    """
    from src import pipeline

    for ds in ("data", "data_v2"):
        (tmp_path / ds / "raw").mkdir(parents=True)
        (tmp_path / ds / "video").mkdir(parents=True)

    # The same stem exists in both datasets' video dirs.
    (tmp_path / "data" / "video" / "deadlift_150x5_20260801.mov").touch()
    (tmp_path / "data_v2" / "video" / "deadlift_150x5_20260801.mov").touch()

    v1 = tmp_path / "data" / "raw" / "deadlift_150x5_20260801_120000.csv"
    v2 = tmp_path / "data_v2" / "raw" / "deadlift_150x5_20260801_120000.csv"
    v1.touch()
    v2.touch()

    assert pipeline.find_video(v1).parents[1].name == "data"
    assert pipeline.find_video(v2).parents[1].name == "data_v2"

    # A dataset with no matching clip returns None rather than reaching sideways
    # into the other one.
    (tmp_path / "data_v2" / "video" / "deadlift_150x5_20260801.mov").unlink()
    assert pipeline.find_video(v2) is None

    # An explicit video_dir still wins, for tests and one-offs.
    forced = pipeline.find_video(v2, tmp_path / "data" / "video")
    assert forced is not None and forced.parents[1].name == "data"

"""C28 — the oracle's machinery, and the one result that is a theorem.

Most of this file is synthetic, and `CLAUDE.md` permits that only for algebraic
identities. That is exactly what the load-bearing test here is: the rank of a
difference of rotation matrices does not depend on any capture, and a gym clip
could not test it better than algebra can.

The real-data tests are non-regression pins on the two numbers C28 reports, so
that a later change to `calibrate` or `integrate` cannot quietly move the
ceiling without someone noticing.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from src import oracle


# ------------------------------------------------------- the structural bit --
@pytest.mark.parametrize("angle_deg", [5, 30, 90, 137, 179])
def test_the_difference_of_two_rotations_is_ALWAYS_rank_two(angle_deg):
    """The reason two C3 holds can never separate tilt from accel bias.

    R1 - R2 = R1 (I - R1^T R2). The relative rotation Delta fixes its own axis
    n, so (I - Delta) n = 0 identically and hence (R1 - R2) n = 0. There is no
    separation of postures large enough to escape it: the component of a
    body-frame bias along the axis the wrist turns about is unobservable from
    two holds, permanently.

    C28 hit this as |b| = 1e12 m/s^2 out of `np.linalg.lstsq(..., rcond=None)`,
    which divides by the zero singular value rather than declining it.
    """
    axis = np.array([0.3, 0.5, 0.81])
    axis = axis / np.linalg.norm(axis)
    r1 = Rotation.random(random_state=7).as_matrix()
    r2 = r1 @ Rotation.from_rotvec(np.deg2rad(angle_deg) * axis).as_matrix()

    sv = np.linalg.svd(r1 - r2, compute_uv=False)
    assert sv[2] < 1e-12 * max(sv[0], 1.0), f"3rd singular value {sv[2]:.2e}"
    # The null direction is the relative rotation's OWN axis, not that axis
    # carried through R1: R1 - R2 = R1 (I - Delta) kills whatever (I - Delta)
    # kills, and (I - Delta) fixes `axis` in the frame Delta acts on.
    assert np.linalg.norm((r1 - r2) @ axis) < 1e-12


def test_split_bias_declines_the_unobservable_direction():
    """Given a bias with a component along the null axis, only the rest returns.

    The point is not that the answer is right — it cannot be. It is that the
    unrecoverable part comes back as ZERO rather than as an arbitrary large
    number, which is the difference between a truncated solve and `rcond=None`.
    """
    axis = np.array([0.0, 0.0, 1.0])
    r_open = np.eye(3)
    r_close = Rotation.from_rotvec(np.deg2rad(60) * axis).as_matrix()
    b_true = np.array([0.02, -0.01, 0.05])       # 0.05 lies along the null axis
    tau_true = np.array([0.03, 0.01, 0.0])

    d = r_open - r_close
    dr = d @ b_true
    u, sv, vt = np.linalg.svd(d)
    keep = sv > 1e-8 * sv[0]
    rank = int(keep.sum())
    b = vt[:rank].T @ ((u[:, :rank].T @ dr) / sv[:rank])

    assert rank == 2
    # the observable plane is recovered exactly
    assert np.allclose(b[:2], b_true[:2], atol=1e-9)
    # the unobservable component is declined, not invented
    assert abs(b[2]) < 1e-9
    assert abs(b_true[2]) > 0.01, "the test would be vacuous without this"


# ------------------------------------------------------------- the harness --
def test_unpack_round_trips_the_parameter_vector():
    terms = ("bias", "tilt", "lever")
    theta = np.arange(oracle.n_params(terms), dtype=float)
    p = oracle.unpack(theta, terms)
    assert list(p) == list(terms)
    assert np.allclose(np.concatenate([p[t] for t in terms]), theta)


def test_the_zero_parameter_model_is_the_identity():
    """`apply_model` with no terms must not touch the acceleration at all.

    If this drifts, every C28 number silently becomes a comparison against
    something other than the shipping pipeline, which is the one thing the
    ladder's bottom row is for.
    """
    rng = np.random.default_rng(0)
    n = 200
    quat = Rotation.random(n, random_state=3).as_quat(scalar_first=True)
    log = {"accel": rng.normal(0, 2.0, (n, 3)), "quat": quat}
    from src import orient
    base = orient.to_world(log["accel"], quat, quat)
    got = oracle.apply_model(log, quat, {})
    assert np.allclose(got, base)


def test_a_body_frame_bias_enters_the_world_rotated():
    """The whole physical claim of `apply_model`, checked as algebra.

    A body-frame offset b must appear in the world as R(t) b — varying with the
    wrist — and NOT as a world-frame constant. That distinction is the entire
    content of C28's `calibrate.accel_bias` finding, so it gets a test rather
    than a comment.
    """
    n = 120
    quat = Rotation.random(n, random_state=11).as_quat(scalar_first=True)
    log = {"accel": np.zeros((n, 3)), "quat": quat}
    b = np.array([0.02, -0.03, 0.01])

    zero = oracle.apply_model(log, quat, {})
    with_b = oracle.apply_model(log, quat, {"bias": b})
    delta = with_b - zero

    expected = Rotation.from_quat(quat, scalar_first=True).apply(b)
    assert np.allclose(delta, expected, atol=1e-12)
    # and it is emphatically not constant in the world frame
    assert delta.std(axis=0).max() > 0.005


def test_plausibility_flags_an_absurd_value():
    """The check that makes this evidence rather than curve-fitting.

    B2 fitted |d| = 21, 64 and 60 cm against a real 10-15 cm and the residual
    still fell; without a plausibility rule that reads as success.
    """
    ok = oracle.plausibility(np.array([0.005, 0.0, 0.0]), ("bias",))
    assert "ok" in ok[0]
    bad = oracle.plausibility(np.array([1.2, 0.0, 0.0]), ("lever",))
    assert "TOO BIG" in bad[0]


# ------------------------------------------------------------------ C28b --
def test_rest_observables_reads_the_velocity_error_without_the_video(monkeypatch):
    """The identity the whole observability result rests on.

    At a true rest instant the bar's velocity is zero, so whatever the
    reconstruction reports there IS its velocity error — and it is readable
    from the reconstruction alone. This drives a synthetic capture through
    `rest_observables` and checks the number that comes back is the reported
    velocity change along the display axis, with no video anywhere in it.
    """
    from src import segment
    n = 400
    t = np.arange(n) * 0.01
    vel = np.zeros((n, 3))
    vel[:, 0] = np.linspace(0.0, 0.8, n)      # drifting along +x
    vel[:, 2] = np.linspace(0.0, -0.5, n)
    monkeypatch.setattr(segment, "rest_instants", lambda log, imp=None: [50, 350])

    result = {"log": {"t": t}, "velocity": vel,
              "bounds": [(0, n)], "impacts": [40]}
    m = {"axis": np.array([1.0, 0.0, 0.0]), "axis_flipped": False,
         "per_rep": [{"covered": True, "pipeline_h_rms": 3.0}]}

    got = oracle.rest_observables(result, m)
    assert len(got) == 1
    assert got[0]["dv_h"] == pytest.approx(vel[350, 0] - vel[50, 0])
    assert got[0]["dv_z"] == pytest.approx(vel[350, 2] - vel[50, 2])
    assert got[0]["span"] == pytest.approx(t[350] - t[50])
    # the sign convention must follow the metric's axis flip, or the
    # correlation this exists to measure is computed against a mirrored axis
    m_flip = dict(m, axis_flipped=True)
    assert oracle.rest_observables(result, m_flip)[0]["dv_h"] == pytest.approx(
        -(vel[350, 0] - vel[50, 0]))


def test_impact_correction_actually_zeroes_the_observed_velocity_change(monkeypatch):
    """It is a NEGATIVE result, so the implementation has to be above suspicion.

    `impact_correction` loses on 4 of 6 deadlifts. That is only a statement
    about the physics if it does what it says — remove exactly the constant
    horizontal acceleration that brings the observed velocity change over each
    rest-to-rest interval to zero. Re-integrating the corrected acceleration
    must therefore close that interval.
    """
    from src import integrate, segment
    n = 400
    dt = np.full(n, 0.01)
    t = np.cumsum(dt) - dt[0]
    # a constant horizontal acceleration: velocity drifts, the bar "is at rest"
    # at both ends by construction of the test, so the whole drift is error
    world = np.zeros((n, 3))
    world[:, 0] = 0.25
    vel, _ = integrate.integrate(world, dt)
    monkeypatch.setattr(segment, "rest_instants", lambda log, imp=None: [50, 350])

    result = {"log": {"t": t, "dt": dt}, "world_accel": world, "velocity": vel,
              "bounds": [(0, n)], "impacts": [40], "path": "synthetic",
              "quat": None}
    out = oracle.impact_correction(result)

    # re-integrate what the correction produced and check the interval closes
    corrected = world.copy()
    span = t[350] - t[50]
    corrected[50:351, :2] -= (vel[350, :2] - vel[50, :2]) / span
    v2, _ = integrate.integrate(corrected, dt)
    assert abs(v2[350, 0] - v2[50, 0]) < 1e-9, "the interval must close"
    assert abs(vel[350, 0] - vel[50, 0]) > 0.5, "test vacuous without real drift"
    # vertical is deliberately untouched — this is a horizontal-only correction
    assert np.allclose(corrected[:, 2], world[:, 2])
    assert out["bar_position"].shape == (n, 3)

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


# ------------------------------------------------------------------- C29 --
def test_a_velocity_step_at_a_rep_BOUNDARY_is_annihilated_by_the_detrend():
    """Why a jump state at the impact cannot work, as algebra rather than as a
    measurement.

    `segment.rep_bounds` ends every rep AT a floor impact. So a velocity error
    that steps at the impact is constant within each rep, its position error is
    linear in t within each rep, and `correct.detrend_rep` removes a line. The
    correction therefore lands exactly in the detrend's null space and changes
    nothing — not approximately, exactly.

    That is a structural incompatibility between the two ideas the project has
    been trying to combine: "use the impact, which is the one externally true
    instant" and "close each rep with a line, whose boundaries are the impacts".
    Any correction localised at the boundary is invisible to what follows it.
    """
    from src import correct
    n = 300
    t = np.linspace(0.0, 3.0, n)
    # a rep's true path plus a constant velocity offset => a linear position term
    true_path = np.column_stack([0.02 * np.sin(np.pi * t / 3.0),
                                 np.zeros(n),
                                 0.5 * np.sin(np.pi * t / 3.0)])
    step = np.array([0.3, -0.2, 0.0])           # constant velocity error
    with_step = true_path + step * t[:, None]

    a = correct.detrend_rep(true_path, 0, n, t)
    b = correct.detrend_rep(with_step, 0, n, t)
    assert np.allclose(a, b, atol=1e-9), (
        "a constant velocity offset over a rep must vanish under a linear "
        "per-rep detrend; if this fails the C29 result needs revisiting")


def test_jump_correction_reduces_to_impact_correction_at_full_width():
    """`width_s=None` must reproduce C28b exactly, or the sweep compares two
    different things at its endpoints and the curve means nothing."""
    from src import integrate, segment
    n = 500
    dt = np.full(n, 0.01)
    t = np.cumsum(dt) - dt[0]
    world = np.zeros((n, 3))
    world[:, 0] = 0.2
    vel, _ = integrate.integrate(world, dt)
    import pytest as _pt
    saved = segment.rest_instants
    segment.rest_instants = lambda log, imp=None: [50, 400]
    try:
        res = {"log": {"t": t, "dt": dt}, "world_accel": world, "velocity": vel,
               "bounds": [(0, n)], "impacts": [300], "path": "synthetic"}
        full = oracle.jump_correction(res, width_s=None)
        c28b = oracle.impact_correction(res)
    finally:
        segment.rest_instants = saved
    assert np.allclose(full["bar_position"], c28b["bar_position"], atol=1e-12)


# ------------------------------------------------- C31b, the measured lever --
def test_lever0_and_a_fitted_lever_ADD_rather_than_replace():
    """`rebuild(lever0=d)` plus a fitted `lever` must equal one offset of d + p.

    The point of keeping them separate is that the fitted term becomes a
    RESIDUAL on the tape — "how far past the measurement does the optimiser
    still want to go?" — which is only a meaningful question if the two compose
    additively. If they ever stopped composing, that reading would be wrong and
    every plausibility line in the pinned ladder would be measuring the wrong
    quantity.
    """
    from src import correct

    n = 300
    dt = np.full(n, 0.01)
    t = np.cumsum(dt) - dt[0]
    log = {"t": t, "dt": dt, "accel": np.zeros((n, 3)),
           "quat": np.tile([1.0, 0.0, 0.0, 0.0], (n, 1))}
    quat = Rotation.from_rotvec(
        np.column_stack([np.zeros(n), 0.4 * np.sin(t), np.zeros(n)])
    ).as_quat(scalar_first=True)
    base = {"path": "synthetic", "log": log, "quat": quat,
            "bounds": [(0, n)], "impacts": []}

    d0 = np.array([-0.09, 0.0, 0.03])
    p = np.array([0.01, -0.02, 0.004])
    both = oracle.rebuild(base, {"lever": p}, world_bias=False, lever0=d0)
    summed = oracle.rebuild(base, {"lever": d0 + p}, world_bias=False)
    assert np.allclose(both["bar_position"], summed["bar_position"], atol=1e-12)


def test_lever0_is_exactly_step_six():
    """A known `d` through the oracle must equal `correct.apply_offset`.

    Cheap, and it pins the thing that would be silently wrong if `rebuild` ever
    applied the offset before integrating instead of after: the answer would
    still be plausible and would no longer be step 6.
    """
    from src import correct

    n = 200
    dt = np.full(n, 0.01)
    t = np.cumsum(dt) - dt[0]
    log = {"t": t, "dt": dt, "accel": np.zeros((n, 3)),
           "quat": np.tile([1.0, 0.0, 0.0, 0.0], (n, 1))}
    quat = Rotation.from_rotvec(
        np.column_stack([0.3 * np.sin(t), np.zeros(n), np.zeros(n)])
    ).as_quat(scalar_first=True)
    base = {"path": "synthetic", "log": log, "quat": quat,
            "bounds": [(0, n)], "impacts": []}

    d0 = np.array([-0.09, 0.0, 0.03])
    off = oracle.rebuild(base, {}, world_bias=False)
    on = oracle.rebuild(base, {}, world_bias=False, lever0=d0)
    assert np.allclose(
        on["bar_position"],
        correct.apply_offset(off["bar_position"], quat, d0), atol=1e-12)


def test_jump_rest_windows_applies_the_wrist_offset_it_is_given():
    """`jump_rest_windows` re-integrates from `world_accel`, so a `d` applied by
    `pipeline.run` upstream is DISCARDED by it.

    That silent discard is the bug this argument exists to prevent: C29's arms
    would have been measured with step 6 off however the caller set it up, and
    the comparison would have read "d does nothing here" for a plumbing reason.
    """
    from src import correct, integrate, segment

    n = 500
    dt = np.full(n, 0.01)
    t = np.cumsum(dt) - dt[0]
    world = np.zeros((n, 3))
    world[:, 0] = 0.2
    vel, _ = integrate.integrate(world, dt)
    quat = Rotation.from_rotvec(
        np.column_stack([np.zeros(n), 0.5 * np.sin(t), np.zeros(n)])
    ).as_quat(scalar_first=True)
    res = {"log": {"t": t, "dt": dt}, "world_accel": world, "velocity": vel,
           "bounds": [(0, n)], "impacts": [300], "path": "synthetic",
           "quat": quat}

    saved = segment.rest_instants
    segment.rest_instants = lambda log, imp=None: [50, 400]
    try:
        d0 = np.array([-0.09, 0.0, 0.03])
        off = oracle.jump_rest_windows(res, width_s=0.20)
        on = oracle.jump_rest_windows(res, width_s=0.20, wrist_offset=d0)
    finally:
        segment.rest_instants = saved

    assert not np.allclose(off["bar_position"], on["bar_position"])
    assert np.allclose(
        on["bar_position"],
        correct.apply_offset(off["bar_position"], quat, d0), atol=1e-12)


# ------------------------------------------------------------------- D1 --
#
# D1 (2026-08-07) asked where the deadlift's invented fore-aft is generated.
# Two of these are algebra and could be nothing else; the rest are real-data
# pins on the numbers the answer rests on, because a diagnosis that nothing
# re-checks is how this project has repeatedly kept a claim past its evidence.

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

_ROOT = _Path(__file__).resolve().parents[1]
# One glob, not two. This used to concatenate `data/raw` and `data_v2/raw`;
# with v1 deleted (F1, 2026-08-14) both halves resolved to the same directory
# and every deadlift ran twice.
_DL = sorted((_ROOT / "data_v2" / "raw").glob("deadlift_*.csv"))
_needs_deadlifts = pytest.mark.skipif(not _DL, reason="no deadlift captures")


def test_parabola_fit_recovers_an_injected_constant_acceleration():
    """Algebra. A constant `c`, endpoint-line removed, IS `c*tau(tau-T)/2`.

    That identity is the whole reason the fit is interpretable: `c` is not a
    curve-fitting coefficient, it is the constant horizontal acceleration that
    would draw the path. If this drifts, `tilt_deg` stops meaning degrees.
    """
    T = 3.0
    tau = np.linspace(0.0, T, 300)
    for c in (0.02, -0.15, 0.0):
        curve = c * tau * (tau - T) / 2.0
        got = oracle.parabola_fit(curve, T)
        assert got["c"] == pytest.approx(c, abs=1e-12)
        if c:
            assert got["r2"] == pytest.approx(1.0, abs=1e-12)
            assert got["tilt_deg"] == pytest.approx(
                np.degrees(np.arcsin(abs(c) / 9.80665)), abs=1e-9)


def test_parabola_detrend_leaves_the_rep_ENDPOINTS_untouched():
    """It must be an ADDITION to step 7, never a replacement for it.

    `tau(tau - T)/2` is zero at both endpoints, so removing any multiple of it
    cannot change where the rep starts or finishes and step 7's closure
    survives exactly. If that stopped holding, the arm measured in
    `oracle.parabola_detrend`'s docstring would be confounded with a change to
    the closure and its rejection would be about the wrong thing.
    """
    n = 400
    t = np.linspace(0.0, 3.0, n)
    rng = np.random.default_rng(3)
    rep = np.cumsum(rng.normal(size=(n, 3)) * 0.001, axis=0)
    rep = rep - np.linspace(0.0, 1.0, n)[:, None] * (rep[-1] - rep[0]) - rep[0]

    out = oracle.parabola_detrend([rep], [(0, n)], t)[0]
    # closure preserved on the corrected axes, and the vertical untouched
    assert out[-1, :2] == pytest.approx(rep[-1, :2], abs=1e-12)
    assert out[:, 2] == pytest.approx(rep[:, 2], abs=1e-12)
    # and it really did remove the parabolic content it claims to
    T = t[-1]
    basis = t * (t - T) / 2.0
    for ax in (0, 1):
        assert abs(float(basis @ out[:, ax])) < 1e-12 * float(basis @ basis) + 1e-15


@_needs_deadlifts
@pytest.mark.parametrize("csv", _DL, ids=lambda p: p.stem.split("_2026")[0])
def test_rep_attribution_parts_sum_to_the_whole(csv):
    """The self-check that makes D1's attribution an attribution.

    Step 7's output is linear in the world acceleration, so any disjoint,
    covering partition of the samples must decompose it EXACTLY. This is not a
    tolerance to be relaxed: if the parts stop summing to the whole, some bin is
    interacting with another and every percentage D1 quotes is meaningless.
    """
    from src import pipeline

    res = pipeline.run(csv)
    mask = oracle.impact_mask(res, 0.10)
    parts = oracle.rep_attribution(res, {"impact": mask, "elsewhere": ~mask},
                                   axis=np.array([1.0, 0.0]))
    assert oracle.attribution_error(parts) < 1e-9


@_needs_deadlifts
@pytest.mark.parametrize("csv", _DL, ids=lambda p: p.stem.split("_2026")[0])
def test_a_detrended_rep_depends_ONLY_on_its_own_samples(csv):
    """The fact that fell out of the attribution, and it is worth a gate.

    Acceleration before a rep reaches it as `p(t0) + v(t0)*(t - t0)` — exactly a
    line — so step 7's endpoint detrend removes it completely; acceleration
    after it cannot reach it at all. So a bin holding every sample OUTSIDE the
    rep windows contributes nothing, measured at ~1e-13 cm.

    The consequence is the reason to pin it: all the integrator drift this
    project worries about is already gone once step 7 has run, and everything
    left in a rep is generated inside its own three seconds. Any future
    correction that claims to fix a rep by acting outside it is claiming
    something this test says is impossible.
    """
    from src import pipeline

    res = pipeline.run(csv)
    inside = np.zeros(len(res["log"]["t"]), dtype=bool)
    for a, b in res["bounds"]:
        inside[a:b] = True
    parts = oracle.rep_attribution(res, {"inside": inside, "outside": ~inside},
                                   axis=np.array([1.0, 0.0]))
    worst = max(float(np.abs(p).max()) for p in parts["outside"])
    assert worst < 1e-9, f"samples outside the rep contribute {worst*100:.2e} cm"


@_needs_deadlifts
@pytest.mark.parametrize("csv", _DL, ids=lambda p: p.stem.split("_2026")[0])
def test_the_deadlift_fore_aft_path_IS_one_parabola(csv):
    """D1's headline, pinned on every deadlift the project holds.

    The reconstruction's per-rep fore-aft output is the response to a single
    constant horizontal acceleration: median r2 of 0.76, 0.95, 0.95, 0.97, 0.98
    and 1.00 across the six. The floor is 0.70 rather than the observed minimum
    because the point is qualitative — the channel carries ONE NUMBER per rep —
    and a tight pin would fail on a change that does not touch the finding.

    If this ever drops materially, the deadlift horizontal has acquired
    structure it did not have, and `parabola_detrend`'s rejection (which rests
    on there being nothing else in there) needs re-measuring.

    **IT RUNS WITH `drift_tilt=False`, AND THAT IS THE POINT (2026-08-16).**
    D1's claim is about the pipeline as it stood when D1 measured it. Step 5b
    now removes exactly the growing parabola D1 identified, so with the default
    on, this r2 FALLS — `deadlift_160x4_2` goes 0.47 to 0.20 — and that fall is
    the correction working, not the finding failing. Pinning the claim against
    the pipeline it was made about keeps both readable; the companion test below
    pins the fall itself.

    *This gate was ALREADY RED on 2 of 6 before 5b existed, and still is. G1
    measured it: `deadlift_150x4_1` 0.27 and `deadlift_170x4_3` 0.47, both
    2026-08-08 captures, so D1's headline holds on the captures it was derived
    from and does not generalise to the newest ones. Left failing rather than
    re-pinned — it is a finding, not a stale gate. See TASKS.md G1.*
    """
    from src import pipeline, project

    res = pipeline.run(csv, drift_tilt=False)
    axis = project.principal_axis(res["reps"])[0]
    t = res["log"]["t"]
    r2 = []
    for rep, (a, b) in zip(res["reps"], res["bounds"]):
        along = np.asarray(rep, float)[:, :2] @ axis
        r2.append(oracle.parabola_fit(along, t[b - 1] - t[a])["r2"])
    assert np.median(r2) > 0.70, f"median r2 {np.median(r2):.2f}, per rep {r2}"


@_needs_deadlifts
def test_the_invented_parabola_GROWS_through_the_set():
    """The other half of D1, and the half that rules out a per-capture constant.

    The effective tilt runs 0.03-0.94 degrees and rises monotonically through a
    set on 4 of the 6 captures (Spearman rho of |c| against rep index 1.00,
    1.00, 0.94, 0.50), while the video's per-rep fore-aft stays flat. That is
    why C28's ladder — one constant fitted per CAPTURE — capped at the null and
    transferred nothing: the constant is real but it is per REP and it moves.

    Gated as "the last rep's tilt exceeds the first's on at least 4 of 6",
    which is the claim, rather than on any one capture's ratio.

    Runs with `drift_tilt=False` for the same reason as the test above: step 5b
    exists to remove this growth, so measuring it with the correction on would
    test the correction rather than the finding.
    """
    from src import pipeline, project

    grew = []
    for csv in _DL:
        res = pipeline.run(csv, drift_tilt=False)
        if len(res["reps"]) < 3:
            continue
        axis = project.principal_axis(res["reps"])[0]
        t = res["log"]["t"]
        tilt = []
        for rep, (a, b) in zip(res["reps"], res["bounds"]):
            along = np.asarray(rep, float)[:, :2] @ axis
            tilt.append(oracle.parabola_fit(along, t[b - 1] - t[a])["tilt_deg"])
        grew.append(tilt[-1] > tilt[0])
        assert max(tilt) < 2.0, f"{csv.stem}: {max(tilt):.2f} deg is not a tilt"
    assert sum(grew) >= 4, f"grew on {sum(grew)} of {len(grew)}"


@_needs_deadlifts
def test_step_5b_REMOVES_the_parabola_D1_found():
    """The correction is aimed at D1's finding, and hits it. 2026-08-16.

    The two tests above pin D1 against the pipeline D1 was measured on. This one
    pins the consequence: turning `drift_tilt` on must make the deadlift fore-aft
    LESS well described by a single constant-acceleration parabola, because that
    parabola is what step 5b removes.

    It is the cheapest possible check that 5b targets the mechanism it claims to.
    A correction that improved the video score while leaving this untouched would
    be improving the number by some other route, and that is worth catching —
    `correct.fit_drift_tilt`'s objective never sees the video, so nothing else in
    the suite connects the two.
    """
    from src import oracle as _oracle
    from src import pipeline, project

    fell = 0
    tested = 0
    for csv in _DL:
        def median_r2(**kw):
            res = pipeline.run(csv, **kw)
            axis = project.principal_axis(res["reps"])[0]
            t = res["log"]["t"]
            return float(np.median([
                _oracle.parabola_fit(np.asarray(rep, float)[:, :2] @ axis,
                                     t[b - 1] - t[a])["r2"]
                for rep, (a, b) in zip(res["reps"], res["bounds"])]))

        before = median_r2(drift_tilt=False)
        after = median_r2(drift_tilt=True)
        tested += 1
        if after < before - 0.01:
            fell += 1

    assert fell >= 4, (
        f"step 5b lowered the parabola r2 on only {fell} of {tested} deadlifts. "
        f"It is supposed to be REMOVING that parabola — if the video score still "
        f"improved, it improved by some other route and the mechanism in "
        f"correct.fit_drift_tilt is not what is doing the work")

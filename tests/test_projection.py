"""Step 8 — the display axis, and whether it is determined enough to stretch.

Split from `test_real_data.py` so three agents could work in parallel; the
convention there applies here — each docstring carries the measurement and the
reasoning, and gates about lifting run on real captures.

The load-bearing test in this file is
`test_axis_stability_is_no_worse_than_min_ratio_predicts`. `project.min_ratio`
derives its threshold from Anderson's asymptotic result for the angular error
of a sample covariance's principal eigenvector, and the one judgement in that
derivation — that the effective sample size is the REP COUNT, not the sample
count — is not derivable. It is checked here against the captures instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import project  # noqa: E402
from tests.test_real_data import CAPTURES, needs_data  # noqa: E402


def _axis_angle(paths) -> float:
    """Heading of the principal horizontal axis, in degrees, mod 180.

    Mod 180 because the eigenvector's sign is arbitrary — that is B4, and a
    stability measure that counted a sign flip as a 180 degree error would be
    measuring B4 rather than the axis.
    """
    v = np.real(project.principal_axis(paths)[0])[:2]
    return float(np.degrees(np.arctan2(v[1], v[0])) % 180.0)


# ------------------------------------------------------- algebraic identities --
# True regardless of how lifting behaves, so they belong here rather than in a
# gym capture. These are the sign and frame-convention bugs synth.py is still
# good for catching (CLAUDE.md).

def test_projection_preserves_distance_along_the_axis():
    """Projecting onto a unit axis is an isometry along that axis."""
    rng = np.random.default_rng(0)
    axis = np.array([0.6, 0.8])
    path = np.column_stack([np.linspace(0, 1, 50), np.zeros(50), rng.normal(size=50)])
    path[:, :2] = np.outer(np.linspace(0, 1, 50), axis)

    out = project.project_to_plane([path], axis)[0]
    assert np.allclose(out[:, 0], np.linspace(0, 1, 50))
    assert np.allclose(out[:, 1], path[:, 2])


def test_projection_normalises_the_axis():
    """A non-unit axis must not silently rescale the horizontal channel.

    That would be a scale error on exactly the axis the 1 cm spec is about,
    which is the class of defect this project keeps rediscovering.
    """
    path = np.column_stack([np.linspace(0, 1, 20), np.zeros(20), np.zeros(20)])
    a = project.project_to_plane([path], np.array([1.0, 0.0]))[0]
    b = project.project_to_plane([path], np.array([7.0, 0.0]))[0]
    assert np.allclose(a, b)


def test_zero_axis_raises_rather_than_returning_nonsense():
    path = np.zeros((10, 3))
    with pytest.raises(ValueError, match="zero vector"):
        project.project_to_plane([path], np.array([0.0, 0.0]))


def test_principal_axis_is_real():
    """`np.linalg.eigh`, not `eig`. The covariance is symmetric.

    Using `eig` returned complex dtype, which is why callers all wrapped the
    result in `np.real` — a workaround that hid the fact that the wrong
    routine was being called.
    """
    rng = np.random.default_rng(1)
    paths = [np.column_stack([rng.normal(size=40) * 3, rng.normal(size=40),
                              np.linspace(0, 1, 40)]) for _ in range(4)]
    axis, ratio, excursion = project.principal_axis(paths)
    assert not np.iscomplexobj(axis)
    assert not np.iscomplexobj(np.asarray(ratio))
    assert ratio >= 1.0
    assert excursion > 0.0


def test_min_ratio_falls_with_rep_count_and_is_finite():
    """More reps pin the axis better, so the bar to clear drops."""
    r = [project.min_ratio(n) for n in range(1, 7)]
    assert all(np.isfinite(r))
    assert all(a > b for a, b in zip(r, r[1:])), r
    assert r[0] > r[-1] > 1.0


# ------------------------------------------------------------- the real check --
@needs_data
def test_axis_stability_is_no_worse_than_min_ratio_predicts():
    """The falsifier `min_ratio`'s docstring names. A DISTRIBUTION statement.

    `min_ratio` sets its threshold from Anderson's asymptotic angular error for
    a principal eigenvector, taking the effective sample size to be the rep
    count rather than the sample count — on the argument that the samples
    within one rep are a single smooth excursion traced at 100 Hz, not
    independent draws. That argument is a judgement and cannot be derived, so
    it is checked here.

    Bootstrap the axis by resampling REPS, and compare the observed angular
    spread against what the formula predicts for that capture's ratio and rep
    count. Predicted larger than observed means the threshold is conservative,
    which is the right direction for a gate authorising a 4x magnification.

    Asserted as a distribution, not per capture, and the reason is honest: it
    does NOT hold everywhere. Captures with a genuinely undetermined axis have
    a bootstrap spread that saturates near the mod-180 wrap, so the comparison
    degenerates exactly where the axis is worst. Requiring a clear majority
    conservative is the strongest claim the data supports.
    """
    rng = np.random.default_rng(0)
    from src import pipeline

    conservative, total, offenders = 0, 0, []
    for path in CAPTURES:
        result = pipeline.run(path)
        reps = result.get("reps") or []
        if len(reps) < 3:
            continue                      # nothing to resample
        n = len(reps)
        ratio = result["axis_ratio"]

        angles = []
        for _ in range(60):
            pick = [reps[i] for i in rng.integers(0, n, n)]
            try:
                angles.append(_axis_angle(pick))
            except Exception:
                pass
        if len(angles) < 30:
            continue

        # Circular spread on a mod-180 quantity.
        z = np.exp(2j * np.deg2rad(np.array(angles)))
        R = float(np.abs(z.mean()))
        observed = float(np.degrees(np.sqrt(max(-2.0 * np.log(max(R, 1e-12)), 0.0))) / 2.0)
        predicted = float(np.degrees(np.sqrt(ratio) / ((ratio - 1.0) * np.sqrt(n)))) \
            if ratio > 1.0 else np.inf

        total += 1
        if observed <= predicted:
            conservative += 1
        else:
            offenders.append(f"{path.stem} obs {observed:.1f} > pred {predicted:.1f} deg")

    assert total >= 10, f"only {total} captures had enough reps to bootstrap"
    assert conservative >= total - 3, (
        f"min_ratio is optimistic on {total - conservative} of {total} captures, "
        f"more than the 2-of-16 its docstring records. N = n_reps may be too "
        f"generous and the gate may be licensing a 4x stretch it should not. "
        f"Offenders: {offenders}")


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_every_capture_gets_a_projected_path_and_a_verdict(path):
    """Step 8 must produce both, on every capture, without raising.

    `confident` being False is a legitimate outcome and is the answer on 8 of
    17 captures — including both with a known segmentation defect. The gate is
    that the stage RAN and committed to a verdict, not that the verdict is yes.
    """
    from src import pipeline

    result = pipeline.run(path)
    planar = result.get("planar")
    assert planar is not None and len(planar) == len(result["bounds"])
    for rep, flat in zip(result["reps"], planar):
        assert flat.shape == (len(rep), 2)
        assert np.isfinite(flat).all()
    assert isinstance(result["confident"], (bool, np.bool_))

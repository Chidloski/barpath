"""
Gates that run on real captures.

Separate from test_pipeline.py on purpose. That file tests algebraic identities
against the synthetic generator — round trips, sign conventions, integration
schemes — things that are true regardless of how lifting behaves. This file
tests claims about the gym, and only real data can settle those.

`data/raw/` is gitignored, so everything here skips cleanly when the captures
are absent. A skipped gate is honest; a gate that passes without data is not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import calibrate, integrate, io, orient, segment  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
CAPTURES = sorted(RAW.glob("*.csv")) if RAW.is_dir() else []

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data/raw/")

REP_COUNT = re.compile(r"^(bench|squat|deadlift)_[\d.]+x(\d+)")


def truth_reps(path: Path) -> int:
    """Rep count from the filename, e.g. deadlift_155x6_2 -> 6."""
    m = REP_COUNT.match(path.name)
    assert m, f"{path.name} is not rep-labelled — it cannot gate anything"
    return int(m.group(2))


def world(log: dict):
    """Velocity and position in the world frame, current best settings."""
    bias, _ = calibrate.gyro_bias(log)
    quat = orient.correct_attitude(log, bias)
    accel = orient.to_world(log["accel"], log["quat"], quat)
    accel = accel - calibrate.accel_bias(accel, log)
    return integrate.integrate(accel, log["dt"])


def horizontal_residual(log: dict, bias: np.ndarray) -> float:
    """Median per-rep-scale horizontal residual, cm. A PROXY, not the metric.

    Tiles 2 s windows across the set and linearly detrends each, standing in
    for real reps until segmentation works (A1) and metrics.dispersion exists
    (A3). It conflates genuine bar movement with error, so the absolute number
    means little — but real motion is common to both arms of a comparison, so
    it ranks two pipelines against each other reliably, which is all it is
    used for here.
    """
    t = log["t"]
    q = orient.correct_attitude(log, bias)
    world = orient.to_world(log["accel"], log["quat"], q)
    world = world - calibrate.accel_bias(world, log)
    pos = integrate.integrate(world, log["dt"])[1]

    out = []
    for t0 in np.arange(5.0, t[-1] - 2.0, 2.0):
        i, j = np.searchsorted(t, [t0, t0 + 2.0])
        seg, tt = pos[i:j, :2], t[i:j] - t[i]
        basis = np.vstack([tt, np.ones_like(tt)]).T
        fit = basis @ np.linalg.lstsq(basis, seg, rcond=None)[0]
        out.append(np.abs(seg - fit).max())
    return float(np.median(out) * 100)


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_gyro_bias_default_beats_applying_it(path):
    """Not applying the pause-derived gyro bias must never be worse.

    This is the B1 gate. Applying the estimate was worse on 13 of 13 captures
    when measured — median 71.5 cm against 4.2 cm — because a 1-3 s hold cannot
    separate residual gyro bias from the lifter's own slow wrist rotation, and
    Core Motion has already removed the part that is removable.

    If this test ever fails, the default in calibrate.gyro_bias should change.
    That is the point of writing it as a comparison rather than a threshold.
    """
    log = io.load_log(path)
    applied, _ = calibrate.gyro_bias(log, apply=True)
    default, info = calibrate.gyro_bias(log)

    assert not info["applied"]
    assert np.array_equal(default, np.zeros(3))
    assert horizontal_residual(log, default) <= horizontal_residual(log, applied)


@needs_data
def test_pause_estimate_is_not_significant_against_its_own_noise():
    """The pause estimate must be reported with an honest uncertainty.

    Every capture should show a standard error on the mean of the same order
    as the estimate itself — that is the measurement proving the estimate
    carries no usable information, and it is why the default is off.
    """
    ratios = []
    for path in CAPTURES:
        info = calibrate.gyro_bias(io.load_log(path))[1]
        assert np.all(np.isfinite(info["sem_rad_s"]))
        ratios.append(np.median(info["snr"]))

    assert np.median(ratios) < 5.0, (
        f"pause estimates now stand well clear of their own noise "
        f"(median SNR {np.median(ratios):.1f}) — revisit whether apply=False "
        f"is still right"
    )


# ------------------------------------------------------------------- A1 --
@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_every_rep_is_found_and_nothing_else(path):
    """Exact rep count on every capture — no misses, no false positives.

    The false positives are the hard half. Walking to the bar, bending to grip
    it, unracking and re-racking are all genuine velocity oscillations, and
    they are LARGER than the reps: setup peaks reach 1.5-2.0 m/s against
    0.3-0.6 m/s for a bench rep.
    """
    log = io.load_log(path)
    velocity, _ = world(log)
    bounds = segment.rep_bounds(log, velocity[:, 2])
    assert len(bounds) == truth_reps(path)


@needs_data
def test_reps_do_not_overlap_and_are_ordered(path=None):
    """Rep windows must be disjoint and in time order on every capture."""
    for p in CAPTURES:
        log = io.load_log(p)
        bounds = segment.rep_bounds(log, world(log)[0][:, 2])
        for (_, stop), (start, _) in zip(bounds, bounds[1:]):
            assert stop <= start, f"{p.name}: overlapping rep windows"


@needs_data
def test_paused_bench_reps_are_where_the_analysis_says():
    """bench_92.5x2 is the designated trap, and counting cannot catch it.

    Its unrack and its two paused reps each form a clean, internally consistent
    pair, so a detector seeded on the wrong one returns exactly the right rep
    COUNT with entirely the wrong reps — which is what happened before the
    lateness tie-break in segment._similar_cluster.

    analysis/README.md records the two paused reps at ~27 s and ~32 s from an
    independent off-pipeline reconstruction. Anchoring on that is the only
    reason this test can tell a right answer from a plausible one.

    Asserts on the CONCENTRIC PEAK, not the window edges. The peak is where the
    press happens and is what "the rep is at ~27 s" means. Window edges depend
    on how far back the eccentric is traced, which is unvalidated until A2 —
    asserting on them here would be claiming an accuracy this file cannot
    justify, and would fail for reasons unrelated to finding the right reps.
    """
    path = next((p for p in CAPTURES if p.name.startswith("bench_92.5x2")), None)
    if path is None:
        pytest.skip("bench_92.5x2 not present")

    log = io.load_log(path)
    velocity = world(log)[0][:, 2]
    filtered = segment.bandpass(velocity, log["fs"])
    bounds = segment.rep_bounds(log, velocity)
    peaks = [log["t"][a + int(np.argmax(filtered[a:b]))] for a, b in bounds]

    assert len(peaks) == 2
    assert 25.0 < peaks[0] < 29.0, f"first rep at {peaks[0]:.1f}s, expected ~27s"
    assert 30.0 < peaks[1] < 34.0, f"second rep at {peaks[1]:.1f}s, expected ~32s"


@needs_data
@pytest.mark.parametrize(
    "stem,expected",
    [("deadlift_155x6_1", 6), ("deadlift_155x6_2", 6), ("deadlift_180x3", 3)],
)
def test_floor_impacts_are_one_per_deadlift_rep(stem, expected):
    """The deadlift landing is a 15-21 g spike and nothing else in a gym is.

    This is an independent check on segmentation: the impacts are found from
    raw acceleration alone, with no integration, no attitude and no velocity,
    so agreeing with the rep count means two unrelated routes to the same
    answer.
    """
    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")
    assert len(segment.impact_anchors(io.load_log(path))) == expected


@needs_data
def test_impacts_do_not_fire_on_lifts_that_never_touch_down():
    """Bench and squat must not produce enough impacts to trigger anchoring.

    This is what lets rep_bounds apply impact_anchors unconditionally instead
    of being told which lift it is looking at.
    """
    for p in CAPTURES:
        if p.name.startswith("deadlift"):
            continue
        n = len(segment.impact_anchors(io.load_log(p)))
        assert n < 3, f"{p.name}: {n} impacts would wrongly trigger anchoring"


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_every_rep_contains_both_phases(path):
    """A rep starts and ends in about the same place, so it must contain both
    an up phase and a down phase of comparable size.

    This is a physical fact about lifting rather than a tuned threshold, and it
    is the strongest check available without video. It catches a failure that
    rep COUNTS cannot see: before segment._absorb existed, 9 of 15 deadlift
    reps contained zero downward travel — the window held only the pull — while
    the count was a perfect 44/44. A heavy pull often breaks into two positive
    lobes at the knee, so the lobe adjacent to the chosen concentric is itself
    positive and no eccentric was ever absorbed.

    Pauses inside a rep are fine and are deliberately included: the bar is
    barely moving, so a pause adds little to either total and keeping it makes
    the window closed at both ends.
    """
    log = io.load_log(path)
    velocity = world(log)[0][:, 2]
    filtered = segment.bandpass(velocity, log["fs"])

    for n, (a, b) in enumerate(segment.rep_bounds(log, velocity), 1):
        seg, tt = filtered[a:b], log["t"][a:b]
        up = np.trapezoid(np.clip(seg, 0, None), tt)
        down = abs(np.trapezoid(np.clip(seg, None, 0), tt))
        assert min(up, down) > 0.3 * max(up, down), (
            f"{path.stem} rep {n}: up {up*100:.0f} cm vs down {down*100:.0f} cm "
            f"— the window is missing a phase, so the rep does not close"
        )

"""Gates on step 5, on real captures. C5.

Separate from `test_real_data.py`, which owns the broad per-capture sweeps.
This file holds the two segmentation defects C5 fixed and — more importantly —
the MARGINS around the constants the fixes rest on.

Why the margins get their own tests. Both defects were found by the ROM bound
rather than by a rep count, and the fix for one of them moved a threshold. This
project has already been burned once by a threshold that passed at a single
setting: `test_accel_bias_removal_meets_horizontal_spec` asserted 1 cm on
synthetic data and was passing only because seed=0 landed at 0.39 cm, inside a
0.29-1.86 cm spread. A constant that works at one value and fails either side
is fitted, not measured, and the only way to tell the difference is to sweep it
and assert on the plateau. That is what
`test_cadence_tolerance_is_a_plateau_not_a_point` does.

`data/raw/` is gitignored, so everything here skips cleanly without captures.
"""

from __future__ import annotations

import functools
import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import calibrate, correct, integrate, io, orient, segment, truth  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
REP_COUNT = re.compile(r"^(bench|squat|deadlift)(?:_[a-z]+)*_[\d.]+x(\d+)")
CAPTURES = ([p for p in sorted(RAW.glob("*.csv")) if REP_COUNT.match(p.name)]
            if RAW.is_dir() else [])

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data/raw/")

_CACHE: dict[str, tuple] = {}


def prepared(path: Path):
    """(log, world velocity, world position), computed once per capture."""
    if path.stem not in _CACHE:
        log = io.load_log(path)
        bias, _ = calibrate.gyro_bias(log)
        quat = orient.correct_attitude(log, bias)
        accel = orient.to_world(log["accel"], log["quat"], quat)
        accel = accel - calibrate.accel_bias(accel, log)
        vel, pos = integrate.integrate(accel, log["dt"])
        _CACHE[path.stem] = (log, vel, pos)
    return _CACHE[path.stem]


def find(stem: str) -> Path:
    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")
    return path


def windows(path: Path):
    log, vel, _ = prepared(path)
    return log, segment.rep_bounds(log, vel[:, 2])


def roms_cm(path: Path, bounds) -> list[float]:
    log, _, pos = prepared(path)
    return [float(r[:, 2].max() - r[:, 2].min()) * 100
            for r in correct.detrend_set(pos, bounds, log["t"])]


# --------------------------------------------------- the two C5 defects --
@needs_data
def test_bench_spoto_does_not_count_the_re_rack():
    """bench_spoto_90x5_1 is five reps, not six.

    The defect: `_longest_cadence`'s tolerance was 1.6, and admitting the
    4.50 s gap between the last rep and the first post-set movement needs
    4.50/2.86 = 1.573. That grew a run of six which beat the true run of five
    on length alone, and the two extra windows came out at 45.7 and 88.7 cm of
    vertical against a 35 cm bench bound.

    Note what could NOT have caught this. The rep COUNT gate did not, because
    `REP_COUNT` failed to match the `spoto` variant token so the capture was
    skipped entirely. Window DURATION could not have: the spurious windows ran
    2.1 and 2.6 s against real reps of 2.5-2.9 s. Only the vertical extent
    separates them, which is why the ROM bound found it and why this test
    asserts on extent rather than on the count alone.
    """
    path = find("bench_spoto_90x5_1")
    log, bounds = windows(path)
    assert len(bounds) == 5

    lo, hi = truth.VERTICAL_ROM_M["bench"]
    for n, rom in enumerate(roms_cm(path, bounds), 1):
        assert lo * 100 <= rom <= hi * 100, (
            f"rep {n} spans {rom:.1f} cm, outside the "
            f"{lo*100:.0f}-{hi*100:.0f} cm bench bound")

    # The re-rack is at ~44-48 s. Every window must end before it.
    assert log["t"][bounds[-1][1] - 1] < 42.0, (
        "a window still reaches into the post-set movement")


@needs_data
def test_squat_single_lands_on_the_rep_not_the_re_rack():
    """squat_160x1's one window must be the squat, not the movement after it.

    The count was already right — 1 of 1 — and that is the point. This is the
    right-count-wrong-window failure, and only the ROM bound could see it: the
    window sat on the re-rack at 37.7 s and spanned 18.0 cm of a ~65 cm squat,
    while the real rep at 33.6 s yields 67.0 cm.

    The mechanism was the cluster tie-break. A single leaves every candidate a
    cluster of one, so `_similar_cluster`'s size key is degenerate and lateness
    decides alone — and the latest movement in any capture is the re-rack,
    because nothing follows a set except putting the bar down.

    Asserts on three independent properties of the window, because any one of
    them alone can be satisfied by an accident: it spans a plausible squat ROM,
    it lasts as long as this lifter's other squat reps (2.4-3.1 s), and it
    contains the concentric peak the diagnosis identified.
    """
    path = find("squat_160x1")
    log, bounds = windows(path)
    assert len(bounds) == 1

    (a, b), = bounds
    rom = roms_cm(path, bounds)[0]
    lo, hi = truth.VERTICAL_ROM_M["squat"]
    assert lo * 100 <= rom <= hi * 100, (
        f"window spans {rom:.1f} cm, outside the {lo*100:.0f}-{hi*100:.0f} cm "
        f"squat bound — 18.0 cm was the re-rack")

    duration = float(log["t"][b - 1] - log["t"][a])
    assert 2.0 < duration < 4.0, (
        f"window lasts {duration:.2f} s; this lifter's squat reps run 2.4-3.1 s "
        f"and the re-rack window ran 1.26 s")

    assert log["t"][a] < 33.6 < log["t"][b - 1], (
        "the window does not contain the concentric peak at 33.6 s that the "
        "C5 diagnosis identified as the real rep")


# ------------------------------------------------------- the margins ------
@needs_data
def test_cadence_tolerance_is_a_plateau_not_a_point():
    """`_longest_cadence`'s tolerance must pass over a RANGE, not at a value.

    This is the anti-fitted-constant gate, and it is the reason C5's bench fix
    is a measurement rather than a tune. The tolerance decides whether a gap
    belongs to the set's rhythm, and it is bounded by real data on both sides:

    * Below 1.35, `squat_140x4_3` splits. Its four reps are genuinely 5.00,
      5.60 and 6.55 s apart — a ratio of 1.310 — so a real set does vary its
      cadence by nearly a third.
    * At 1.60 and above, `bench_spoto_90x5_1` admits the 4.50 s post-set gap
      (4.50/2.86 = 1.573) and counts six.

    Every value in 1.35-1.55 gives 17/17. The shipping 1.45 sits in the middle
    of that plateau — 11% clear of the worst real set, 8% clear of the failure.

    If this test ever fails at an interior value, the constant has become
    load-bearing at a point and the fix is a better discriminator, not a
    re-tune. If it fails at the edges, a new capture has moved the plateau and
    the docstring numbers in `segment._longest_cadence` need re-measuring.
    """
    original = segment._longest_cadence
    counts: dict[float, int] = {}
    try:
        for tol in (1.30, 1.35, 1.45, 1.55, 1.60):
            segment._longest_cadence = functools.partial(original, tol=tol)
            counts[tol] = sum(
                len(segment.rep_bounds(log, vel[:, 2])) == int(
                    REP_COUNT.match(p.name).group(2))
                for p in CAPTURES
                for log, vel, _ in [prepared(p)])
    finally:
        segment._longest_cadence = original

    n = len(CAPTURES)
    for tol in (1.35, 1.45, 1.55):
        assert counts[tol] == n, (
            f"tol={tol} gives {counts[tol]}/{n} — the plateau has shrunk, so "
            f"1.45 is no longer comfortably inside it")
    for tol in (1.30, 1.60):
        assert counts[tol] < n, (
            f"tol={tol} now also gives {counts[tol]}/{n}. The plateau has "
            f"widened, which is good news, but segment._longest_cadence's "
            f"docstring quotes these edges and is now wrong")


@needs_data
def test_only_a_single_has_a_degenerate_cluster():
    """The singleton tie-break can only ever fire on squat_160x1.

    `_similar_cluster` ranks clusters by size and falls back to displacement
    only when the best cluster has one member — the case where the size key
    carries no information at all. That fallback is a judgement about lifting
    (a rep moves the bar further than the movements bracketing it) which is
    measurably FALSE on bench, where `bench_92.5x2`'s unrack carries 0.433 m
    against 0.295 for a real rep.

    So the containment matters as much as the rule: of the 17 captures, only
    `squat_160x1` has a winning cluster of size 1. Every other has four or
    more, and reaches the fallback never. This test pins that, so a future
    capture that lands in the degenerate branch announces itself instead of
    being silently judged by a rule known not to hold on bench.
    """
    degenerate = []
    for p in CAPTURES:
        log, vel, _ = prepared(p)
        if len(segment.impact_anchors(log)) >= 3:
            continue                      # deadlift: impact-anchored
        t = log["t"]
        v = segment.bandpass(vel[:, 2], log["fs"])
        lobes = segment._concentric_lobes(v, t)
        shapes = np.array([segment._shape(v, t, i) for i, _, _, _ in lobes])
        peaks = np.array([np.abs(v[a:b]).max() for _, a, b, _ in lobes])
        biggest = max(int(segment._grow(shapes, peaks, s, 0.7, 2.5).sum())
                      for s in range(len(lobes)))
        if biggest <= 1:
            degenerate.append(p.stem)

    assert len(degenerate) == 1 and degenerate[0].startswith("squat_160x1"), (
        f"captures reaching the displacement fallback: {degenerate}. That rule "
        f"does not hold on bench (bench_92.5x2's unrack carries 0.433 m against "
        f"0.295 for a rep), so a new capture landing here needs checking by "
        f"hand rather than trusting the fallback")


# ------------------------------------------------------ the whole set -----
@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_every_window_spans_a_physically_possible_rep(path):
    """Count AND extent, on every capture. C5's closing state: 72/72.

    Counting was 71/72 and one capture counted right with the wrong window, so
    both halves are asserted together. They fail independently — a count can be
    right while an extent is wrong (`squat_160x1`) and an extent can be right
    while a count is wrong (`bench_spoto_90x5_1`'s first four windows were all
    ~30 cm) — and neither implies the other.

    What this still cannot see is PHASE. A window half a rep out of step has
    the right count and the right amplitude, and only the video catches it —
    which exists for deadlift alone. Bench and squat segment on integrated
    velocity carrying 145 cm of in-band error against a 69 cm signal (P3), so
    passing here leaves their phase unverified. See
    `test_real_data.test_rep_windows_are_in_phase_with_the_video`.
    """
    log, bounds = windows(path)
    expected = int(REP_COUNT.match(path.name).group(2))
    assert len(bounds) == expected

    lo, hi = truth.VERTICAL_ROM_M[truth.lift_of(path)]
    slack = 0.02                    # bounds are anatomical, quoted to the cm
    for n, rom in enumerate(roms_cm(path, bounds), 1):
        assert (lo - slack) * 100 <= rom <= (hi + slack) * 100, (
            f"{path.stem} rep {n}: {rom:.1f} cm outside "
            f"{lo*100:.0f}-{hi*100:.0f} cm")

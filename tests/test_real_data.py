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

REP_COUNT = re.compile(r"^(bench|squat|deadlift)_[\d.]+x(\d+)")

# Every log, including non-lifts. Use for format-level checks — clipping,
# sampling, quaternion norms — which are about the FILE, not about lifting.
ALL_LOGS = sorted(RAW.glob("*.csv")) if RAW.is_dir() else []

# Rep-labelled lifts only. Nearly every gate here means "a set of reps", and
# data/raw/ now also holds diagnostic captures — a stationary watch on a table,
# for instance — where asking how many reps were found is meaningless.
CAPTURES = [p for p in ALL_LOGS if REP_COUNT.match(p.name)]

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data/raw/")


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

    SUPERSEDED by src/metrics.py for measuring error — A3 exists and reports
    real centimetres against video. This survives for one job only: the B1
    gates below, which compare the SAME pipeline with and without the gyro-bias
    correction applied. Real bar movement is common to both arms there, so it
    cancels out of the ranking even though it pollutes the absolute number.

    Do not use it for anything else, and do not read its output as error. It
    tiles 2 s windows across the set and linearly detrends each, so it
    conflates genuine bar movement with error and its windows are not reps.
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

    Asserts on where each rep STARTS, which is what analysis/README.md's "~27 s
    and ~32 s" refers to — the descent beginning.

    This test previously asserted on the concentric peak instead, and the
    expected values have legitimately moved since. Under the old inverted
    acceleration sign what the pipeline called the concentric was really the
    descent, so the "peak" landed at 27.2 and 31.8. With the sign fixed in
    io.load_log the press peaks sit at 30.0 and 34.5 — about three seconds
    later, which is right for a two-count paused bench — and the rep starts
    are what now line up with the recorded times.
    """
    path = next((p for p in CAPTURES if p.name.startswith("bench_92.5x2")), None)
    if path is None:
        pytest.skip("bench_92.5x2 not present")

    log = io.load_log(path)
    bounds = segment.rep_bounds(log, world(log)[0][:, 2])
    starts = [log["t"][a] for a, _ in bounds]

    assert len(starts) == 2
    assert 25.0 < starts[0] < 29.0, f"first rep starts {starts[0]:.1f}s, expected ~27s"
    assert 30.0 < starts[1] < 34.0, f"second rep starts {starts[1]:.1f}s, expected ~32s"


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


# ------------------------------------------------------------------- A2 --
VIDEO = Path(__file__).resolve().parents[1] / "data" / "video"

DEADLIFTS = [
    ("deadlift_155x6_1_20260728", "deadlift_155x6_1_20260728_122828", 6),
    ("deadlift_155x6_2_20260728", "deadlift_155x6_2_20260728_123603", 6),
    ("deadlift_180x3_20260728", "deadlift_180x3_20260728_121739", 3),
]


def _has(video: str, csv: str) -> bool:
    return (VIDEO / f"{video}.mov").exists() and (RAW / f"{csv}.csv").exists()


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_video_and_imu_agree_on_when_the_bar_lands(video, csv, reps):
    """Two unrelated sensors must agree on the same moments.

    The video sees the plate reach the floor; the IMU sees a 15-21 g spike.
    Nothing links them but the event itself, so agreement is real evidence
    rather than a self-consistency check — and it is what makes the video
    usable as ground truth for everything else.

    Rep timing is specified at +/-50 ms, so the fit residual must beat that.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import truth

    path = truth.bar_path(VIDEO / f"{video}.mov")
    seen = truth.landings(path)
    log = io.load_log(RAW / f"{csv}.csv")
    impacts = np.array([float(log["t"][i]) for i in segment.impact_anchors(log)])

    assert len(seen) == reps, f"video found {len(seen)} landings, expected {reps}"
    assert len(impacts) == reps

    fit = truth.sync(seen, impacts)
    assert fit["rms_ms"] < 50.0, f"sync residual {fit['rms_ms']:.0f} ms exceeds the spec"
    assert abs(fit["drift_pct"]) < 1.0, f"clock drift {fit['drift_pct']:.2f}% is implausible"


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_video_deadlift_rom_is_physical(video, csv, reps):
    """Per-rep lockout height must be a plausible deadlift ROM.

    Measured from the bar resting on the floor, so it excludes the 22.5 cm
    plate radius: true bar height at lockout is this plus that. A wrong
    PLATE_DIAMETER_M would scale every measurement proportionally, and this is
    what would catch it.

    Deliberately a band, not a number. The tape-measured lockout height has not
    been recorded yet, and asserting a precise value without it would invent
    the ground truth this module exists to supply.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import truth

    path = truth.bar_path(VIDEO / f"{video}.mov")
    edges = np.r_[0.0, truth.landings(path), path["t"][-1]]
    peaks = []
    for a, b in zip(edges, edges[1:]):
        window = path["height"][(path["t"] >= a) & (path["t"] < b)]
        if len(window):
            peaks.append(float(np.nanmax(window)))
    peaks = [p for p in peaks if p > 0.2]

    assert len(peaks) >= reps - 1, f"only {len(peaks)} lockouts resolved"
    for p in peaks:
        assert 0.40 < p < 0.85, f"lockout {p*100:.0f} cm above the floor is not a deadlift"


@pytest.mark.parametrize("video", ["bench_90x4_1_20260727", "bench_92.5x2_20260727"])
def test_bench_tracking_fails_loudly_rather_than_silently(video):
    """Bench must raise, not return a confident wrong answer.

    The plate there is small, sits against a dark ceiling and abuts the
    lifter-and-bench silhouette, which is a larger dark blob — so find_plate
    prefers the clutter. It tracked a motionless background patch for a whole
    clip at 0.907 median NCC and reported 0.0 cm of bar travel, which would
    have gone downstream as ground truth.

    This test pins the CURRENT state: automatic seeding does not work on bench.
    When it does, or when a seed_yx is wired in, this test should be replaced
    by a real one — not deleted.
    """
    path = VIDEO / f"{video}.mov"
    if not path.exists():
        pytest.skip(f"{video} not present")
    from src import truth

    with pytest.raises(ValueError, match="locked onto something static"):
        truth.bar_path(path)


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_deadlift_tracking_is_clean_enough_to_trust(video, csv, reps):
    """Deadlifts must track well, unattended, with no warning."""
    if not _has(video, csv):
        pytest.skip(f"{video} not present")
    import warnings as w
    from src import truth

    with w.catch_warnings():
        w.simplefilter("error")          # any quality warning fails the test
        path = truth.bar_path(VIDEO / f"{video}.mov")

    assert path["travel_m"] > 0.40
    assert np.nanmedian(path["score"]) > truth.GOOD_SCORE


# ------------------------------------------------------------------- A4 --
@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_pipeline_runs_end_to_end_without_raising(path):
    """The driver must survive stages that are not implemented.

    Three functions still raise NotImplementedError, so the pipeline genuinely
    cannot complete. It must record that and return the eight stages that did
    work — throwing would lose all of them, and a partial result you can see is
    worth more than an exception.
    """
    from src import pipeline

    result = pipeline.run(path)
    assert result["blocked"], "unimplemented stages must be reported, not hidden"
    assert len(result["bounds"]) == truth_reps(path)
    assert result["position"].shape == (len(result["log"]["t"]), 3)
    assert isinstance(pipeline.summary(result), str)


@needs_data
def test_pipeline_surfaces_log_warnings():
    """io.check_log was dead code. The driver must actually report it.

    deadlift_180x3 peaks at 21.8 g and trips the brief-transient check. (It
    used to trip a saturation check; B5 established that nothing clips, and
    replaced the magnitude threshold with a real rail test.) Before the driver
    existed that warning was computed by nothing and seen by nobody.
    """
    from src import pipeline

    path = next((p for p in CAPTURES if p.stem.startswith("deadlift_180x3")), None)
    if path is None:
        pytest.skip("deadlift_180x3 not present")

    result = pipeline.run(path)
    assert result["warnings"], "expected a high-g transient warning on deadlift_180x3"
    assert "WARNING" in pipeline.summary(result)


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_rep_windows_are_in_phase_with_the_video(video, csv, reps):
    """Each rep window must hold exactly one lockout. This is the phase gate.

    Rep COUNT cannot see phase. The previous segmenter scored a perfect 44/44
    while every window ran lockout-to-lockout — holding the descent of one rep
    followed by the ascent of the next, half a rep out of step — because it
    keyed off band-passed vertical velocity, which correlates -0.82 with the
    real bar height. The in-band error is 145 cm against a 69 cm signal, and it
    is present at the acceleration stage already, so no filter removes it.

    Only the video can catch that, which is the whole argument for A2.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} not present")
    from src import truth

    log = io.load_log(RAW / f"{csv}.csv")
    path = truth.bar_path(VIDEO / f"{video}.mov")
    impacts = np.array([float(log["t"][i]) for i in segment.impact_anchors(log)])
    fit = truth.sync(truth.landings(path), impacts)
    t_video = truth.to_imu_time(path, fit)

    edges = np.r_[0.0, truth.landings(path), path["t"][-1]]
    lockouts = []
    for a, b in zip(edges, edges[1:]):
        m = (path["t"] >= a) & (path["t"] < b)
        if m.any() and np.nanmax(path["height"][m]) > 0.2:
            lockouts.append(float(t_video[m][np.nanargmax(path["height"][m])]))

    bounds = segment.rep_bounds(log, world(log)[0][:, 2])
    assert len(bounds) == reps

    for n, (a, b) in enumerate(bounds, 1):
        t0, t1 = log["t"][a], log["t"][b - 1]
        inside = [q for q in lockouts if t0 <= q <= t1]
        assert len(inside) == 1, (
            f"{csv} rep {n} [{t0:.1f},{t1:.1f}] contains {len(inside)} lockouts, "
            f"expected 1 — the window is out of phase with the bar"
        )


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_acceleration_sign_agrees_with_the_video(video, csv, reps):
    """World vertical acceleration must point the way the bar actually moves.

    Core Motion's userAcceleration is the NEGATIVE of physical acceleration, and
    io.load_log negates it on the way in. This test is the reason that is known.

    Integrating world acceleration over 0.3 s windows and comparing to the video
    velocity change is deliberate: over that span an accel bias contributes only
    ~0.1 m/s against true steps of 0.5-1.5 m/s, so the comparison tests SIGN and
    not accumulated drift. Every check that had been run before was at the
    calibration pause or averaged over a whole pull, where userAcceleration is
    zero or nets to zero and its sign simply cannot be seen.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} not present")
    from scipy.signal import savgol_filter
    from src import orient, truth

    log = io.load_log(RAW / f"{csv}.csv")
    accel = orient.to_world(log["accel"], log["quat"],
                            orient.correct_attitude(log, np.zeros(3)))
    accel = accel - calibrate.accel_bias(accel, log)

    path = truth.bar_path(VIDEO / f"{video}.mov")
    impacts = segment.impact_anchors(log)
    fit = truth.sync(truth.landings(path),
                     np.array([float(log["t"][k]) for k in impacts]))
    t_video = truth.to_imu_time(path, fit)

    grid = np.arange(log["t"][impacts[0]] - 3, log["t"][impacts[-1]] + 1, 0.01)
    height = savgol_filter(np.interp(grid, t_video, path["height"]), 41, 3)
    v_video = np.gradient(height, grid)
    a_imu = np.interp(grid, log["t"], accel[:, 2])

    n = 30
    dv_imu = np.array([np.trapezoid(a_imu[i:i + n], grid[i:i + n])
                       for i in range(0, len(grid) - n, 10)])
    dv_vid = np.array([v_video[i + n] - v_video[i]
                       for i in range(0, len(grid) - n, 10)])
    x, y = dv_imu - dv_imu.mean(), dv_vid - dv_vid.mean()
    corr = float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y)))
    assert corr > 0.5, f"vertical acceleration correlates {corr:+.2f} with the video"


@needs_data
@pytest.mark.parametrize(
    "stem", ["deadlift_155x6_1", "deadlift_155x6_2", "deadlift_180x3"])
def test_floor_impact_decelerates_the_bar(stem):
    """The floor pushes UP on a falling bar, so the velocity step must be positive.

    A second, independent check on the acceleration sign that needs no video at
    all — only the knowledge that floors do not accelerate barbells downwards.
    It was negative on all 9 impacts before io.load_log negated userAcceleration.
    """
    from src import integrate, orient

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    log = io.load_log(path)
    accel = orient.to_world(log["accel"], log["quat"],
                            orient.correct_attitude(log, np.zeros(3)))
    velocity = integrate.integrate(accel, log["dt"])[0]

    steps = []
    for k in segment.impact_anchors(log):
        a = int(np.searchsorted(log["t"], log["t"][k] - 0.15))
        b = int(np.searchsorted(log["t"], log["t"][k] + 0.35))
        steps.append(float(velocity[b, 2] - velocity[a, 2]))

    # Asserted in aggregate rather than per-impact. An inverted sign flips
    # EVERY impact, which this catches comprehensively; a single one can go the
    # other way for an honest reason — the 0.35 s window occasionally runs past
    # the bar settling and picks up the wrist following it down. 14 of 15 are
    # positive across the three captures.
    assert np.mean(steps) > 0, f"{path.stem}: mean impact step {np.mean(steps):+.2f}"
    assert sum(s > 0 for s in steps) >= len(steps) - 1, (
        f"{path.stem}: {sum(s <= 0 for s in steps)} of {len(steps)} impacts give a "
        f"downward velocity step — the acceleration sign is inverted")


# ------------------------------------------------------------------- A3 --
# Measured 2026-07-29, first run of metrics.vs_truth. Ceilings, not targets:
# the spec is 1 cm horizontal and 2-3 cm vertical, and the pipeline meets
# neither. These pin what it does TODAY so B2/B3/B6 can only improve it, and
# they should be tightened whenever one of those lands. The xfail below carries
# the actual spec.
AS_SHIPPED_H_CM = {                 # median per-rep horizontal rms vs video
    "deadlift_155x6_1": 5.1,
    "deadlift_155x6_2": 9.2,
    "deadlift_180x3": 15.4,
}
CEILING = 1.25                      # 25% headroom, so noise does not flap it


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_error_against_video_does_not_regress(video, csv, reps):
    """Horizontal error against the video must not get worse than measured.

    This is the gate whose absence let milestones 1-6 pass while the pipeline
    failed by two orders of magnitude. Nothing here asserts the pipeline is
    good — it is not, by 5-15x — only that a change cannot quietly make it
    worse, which is the guarantee B2, B3 and B6 need in order to be evaluated
    at all.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline

    stem = next(k for k in AS_SHIPPED_H_CM if csv.startswith(k))
    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")

    assert m["n_compared"] == reps
    assert m["pipeline_h_rms"] < AS_SHIPPED_H_CM[stem] * CEILING, (
        f"{stem}: horizontal error {m['pipeline_h_rms']:.1f} cm against "
        f"{AS_SHIPPED_H_CM[stem]:.1f} cm when A3 was written")


@pytest.mark.xfail(reason="P2/P3 — the whole point of the project, 5-15x out",
                   strict=False)
@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_horizontal_meets_the_spec(video, csv, reps):
    """~1 cm horizontal. The spec, in the suite, failing honestly.

    Written as xfail rather than left out so that the number the project exists
    to hit is executable and visible on every run. When B2, B3 or B6 makes it
    pass, pytest reports XPASS and the ceilings above should be tightened.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline

    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")
    assert m["pipeline_h_rms"] < 1.0
    assert m["pipeline_v_rms"] < 3.0


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_dispersion_is_finite_and_reported(path):
    """dispersion must run on every capture and produce usable numbers."""
    from src import metrics, pipeline

    result = pipeline.run(path)
    d = result["dispersion"]
    assert d["n_reps"] == truth_reps(path)
    for key in ("horizontal_rms", "horizontal_p95", "vertical_rms"):
        assert np.isfinite(d[key]) and d[key] >= 0
    assert d["horizontal_p95"] >= d["horizontal_rms"] * 0.5
    assert np.isfinite(d["per_axis_rms"]).all()


@needs_data
@pytest.mark.parametrize("stem", ["bench_90x4_1", "squat_130x5"])
def test_dispersion_flatters_a_broken_pipeline(stem):
    """The caveat in dispersion's docstring, asserted rather than promised.

    On bench and squat dispersion reports well under 2 cm of rep-to-rep spread
    — comfortably inside the 1 cm-ish spec band — on lifts where NOTHING has
    ever been verified, and where `vs_truth` refuses to produce a number at all
    because the video is not trustworthy there. Both halves are asserted here,
    because together they are the whole point: a good dispersion number and no
    truth is exactly the state in which this project has twice convinced itself
    a broken pipeline worked.

    The reason is structural. Error that repeats every rep lands in the mean
    rep and cancels out of every deviation from it, so a pipeline dominated by
    P3 scores well here by construction.

    This used to assert `dispersion <= vs_truth` on a deadlift, on the reasoning
    that dispersion must be the optimistic one. That was stronger than the
    argument supports — the two measure different things and their ordering is
    not guaranteed — and B3's endpoint median duly broke it by pulling the
    truth error to 4.6 cm against 5.2 cm of spread.
    """
    from src import metrics, pipeline

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    assert result["dispersion"]["horizontal_rms"] < 2.0
    with pytest.raises(ValueError, match="deadlift-only"):
        metrics.vs_truth(result, VIDEO / "deadlift_155x6_1_20260728.mov")


@needs_data
@pytest.mark.parametrize("stem", ["bench_90x4_1", "squat_130x5"])
def test_vs_truth_refuses_lifts_without_usable_video(stem):
    """Squat and bench are not truth, so vs_truth must raise rather than guess.

    Squat tracks at median NCC ~0.40 with the plate leaving frame at lockout;
    bench does not seed automatically at all. Returning a number from either
    would invent the ground truth this module exists to supply — the exact
    move that let a broken pipeline look validated for months.
    """
    from src import metrics, pipeline

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    with pytest.raises(ValueError, match="deadlift-only"):
        metrics.vs_truth(result, VIDEO / "deadlift_155x6_1_20260728.mov")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_video_truth_is_physically_sane(video, csv, reps):
    """Guard the metric itself: if these drift, distrust the number, not the pipeline.

    A metric is only as good as the truth behind it, and this one leans on the
    video scale (PLATE_DIAMETER_M, still assumed) and on the IMU-video sync.
    These are the quantities that would make vs_truth confidently wrong, so
    they are asserted alongside it rather than taken on faith.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline

    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")

    assert m["sync_rms_ms"] < 50.0, "rep timing is specified at +/-50 ms"
    assert abs(m["sync_drift_pct"]) < 1.0
    assert 40.0 < m["video_rom_cm"] < 85.0, "not a deadlift ROM"
    assert 2.0 < m["video_fore_aft_cm"] < 25.0, (
        "real fore-aft travel is 10-20 cm; outside that the tracker or the "
        "plate scale is wrong")


# ------------------------------------------------------------------- B7 --
@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_rest_instants_land_where_the_bar_is_actually_still(video, csv, reps):
    """`segment.rest_instants` must find rest, not just the impact.

    This is the one piece of B7 that survived the experiment. The anchor
    correction built on it lost and was reverted (see TASKS.md B7), but the
    detector itself is validated and B6 will want it, so it is gated rather
    than deleted.

    The distinction it exists for: `impact_anchors` marks the ONSET of the
    spike, and video says the bar is still moving at 0.4-1.0 m/s there. True
    rest follows 400-850 ms later. Scoring on acceleration alone lands at
    0.50 m/s; adding gyro variance and widening the search gets 13 of 15
    impacts under 0.05 m/s.

    The two it cannot do are the final impact of a set, where the lifter
    releases the bar and walks away — those are rejected by the `max_accel`
    gate rather than returned wrong, which is why this asserts on every
    instant returned rather than on a mean.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from scipy.signal import savgol_filter
    from src import truth

    log = io.load_log(RAW / f"{csv}.csv")
    impacts = segment.impact_anchors(log)
    rest = segment.rest_instants(log, impacts)

    path = truth.bar_path(VIDEO / f"{video}.mov")
    fit = truth.sync(truth.landings(path),
                     np.array([float(log["t"][k]) for k in impacts]))
    t_video = truth.to_imu_time(path, fit)
    v_video = np.gradient(savgol_filter(path["height"], 9, 3), t_video)

    assert rest, "no rest instants accepted on a deadlift"
    assert len(rest) <= len(impacts)
    for k in rest:
        v = abs(float(np.interp(float(log["t"][k]), t_video, v_video)))
        assert v < 0.10, (
            f"{csv}: rest instant at {log['t'][k]:.2f}s has the bar moving at "
            f"{v:.2f} m/s — that is not rest, and anchoring to it would inject "
            f"error rather than remove it")


# ------------------------------------------------------------------- B5 --
@needs_data
@pytest.mark.parametrize("path", ALL_LOGS, ids=lambda p: p.stem)
def test_no_capture_is_actually_clipped(path):
    """Nothing in data/raw/ saturates, including the 21.8 g one.

    `check_log` used to warn on `deadlift_180x3` for exceeding a 16 g threshold
    that was an assumption about a sensor nobody had checked. It is not
    clipped: every per-axis extreme is reached by exactly one sample and none
    is a round number, which is what a genuine transient looks like. A railed
    sensor repeats one value for consecutive samples.
    """
    log = io.load_log(path)
    assert io.clipped_runs(log["accel"]) == 0


@needs_data
def test_the_high_g_capture_is_a_real_measurement():
    """deadlift_180x3 peaks at 21.8 g and that is a reading, not a rail."""
    path = next((p for p in CAPTURES if p.stem.startswith("deadlift_180x3")), None)
    if path is None:
        pytest.skip("deadlift_180x3 not present")

    log = io.load_log(path)
    accel = log["accel"] / io.G
    assert 20.0 < np.linalg.norm(accel, axis=1).max() < 32.0
    for k in range(3):
        col = accel[:, k]
        assert (col == col.max()).sum() == 1, "a rail repeats; a transient does not"
        assert (col == col.min()).sum() == 1


IMPACT_STEP_RATIO = {               # IMU velocity step / video's, per capture
    "deadlift_155x6_1": (0.90, 1.30),
    "deadlift_155x6_2": (0.70, 1.25),
    "deadlift_180x3": (1.40, 1.90),          # over-reads; see the docstring
}


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_impact_velocity_step_matches_the_video(video, csv, reps):
    """The impulse IS captured at 100 Hz — except on the heaviest capture.

    Measured as min-to-max velocity within +/-0.3 s of the impact, identically
    on both sources. The 155 kg captures land at 0.77-1.19, median 1.04 overall.

    Two ways to get this wrong, both of which the first version of this test
    did, and both of which made the impulse look 80% missing:

    Do not predict arrival velocity as sqrt(2*g*h). A touch-and-go deadlift is
    lowered under control with the hands on the bar; it arrives at about 2 m/s,
    not the 3.3 a free fall from lockout gives. Only the video knows.

    Do not measure the step as a net change across a fixed window. The window
    spans the rise and then the fall into the next descent, so the net is small
    while the step is not.

    deadlift_180x3 genuinely over-reads by 58-72%, alone among the three, and
    is also the worst capture by horizontal error. That is pinned separately
    rather than averaged away, because it is the anomaly worth explaining.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from scipy.signal import savgol_filter
    from src import truth

    log = io.load_log(RAW / f"{csv}.csv")
    accel = orient.to_world(log["accel"], log["quat"],
                            orient.correct_attitude(log, np.zeros(3)))
    accel = accel - calibrate.accel_bias(accel, log)
    vel = integrate.integrate(accel, log["dt"])[0]

    path = truth.bar_path(VIDEO / f"{video}.mov")
    impacts = segment.impact_anchors(log)
    fit = truth.sync(truth.landings(path),
                     np.array([float(log["t"][k]) for k in impacts]))
    t_video = truth.to_imu_time(path, fit)
    v_video = np.gradient(savgol_filter(path["height"], 9, 3), t_video)

    ratios = []
    for k in impacts:
        tk = float(log["t"][k])
        a = int(np.searchsorted(log["t"], tk - 0.30))
        b = int(np.searchsorted(log["t"], tk + 0.30))
        m = (t_video > tk - 0.30) & (t_video < tk + 0.30)
        if not m.any():
            continue
        vid = float(np.nanmax(v_video[m]) - np.nanmin(v_video[m]))
        ratios.append(float(vel[a:b, 2].max() - vel[a:b, 2].min()) / vid)

    stem = next(k for k in IMPACT_STEP_RATIO if csv.startswith(k))
    lo, hi = IMPACT_STEP_RATIO[stem]
    mean = float(np.mean(ratios))
    assert lo < mean < hi, (
        f"{stem}: impact velocity step is {mean:.2f}x the video's, outside the "
        f"{lo}-{hi} measured for this capture at B5")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_fore_aft_direction_is_not_self_consistent(video, csv, reps):
    """B4, measured: reps within one set disagree about which way is forward.

    vs_truth picks ONE axis sign per set, because that is what step 8 can do,
    and then counts how many reps would individually have preferred the other.
    The answer is 4 of 6, 2 of 6 and 1 of 3 — near a coin flip on the first.
    The horizontal reconstruction is not merely noisy in magnitude, it is
    inconsistent in DIRECTION from rep to rep, so no per-set sign convention
    can be right for all of a set.

    Pinned as a characterisation, not a target: this asserts the disagreement
    is real and bounded, so that a fix to B2/B4/B6 shows up here as the count
    falling. If it reaches zero, delete this test and say so.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline

    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")
    assert 0 <= m["reps_disagreeing_on_sign"] <= m["n_compared"] // 2 + 1


# ------------------------------------------------------------------- B2 --
def test_wrist_lever_arm_is_centimetres_not_decimetres():
    """The size of R(t).d, pinned — because the old figure was 3x too big.

    TASKS.md and pipeline.py both claimed the wrist offset varies by 8-13 cm
    horizontally on every lift and called it the largest unmodelled term in the
    system. Measured within a rep, after step 7, at |d| = 14 cm and swept over
    every direction of d, the worst case is 4-6.4 cm and a typical direction is
    1.2-2.4 cm. That mis-statement had been setting priorities, so it is worth
    a gate rather than a note.

    Uses a coarse direction sweep and asserts on the WORST case, so it cannot
    pass by picking a flattering d.
    """
    from scipy.spatial.transform import Rotation
    from src import correct, pipeline

    i = np.arange(60) + 0.5
    phi = np.arccos(1 - 2 * i / 60)
    theta = np.pi * (1 + 5 ** 0.5) * i
    dirs = np.column_stack([np.cos(theta) * np.sin(phi),
                            np.sin(theta) * np.sin(phi), np.cos(phi)])

    for stem in ("bench_90x4_1", "squat_130x5", "deadlift_155x6_1"):
        path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
        if path is None:
            pytest.skip(f"{stem} not present")

        r = pipeline.run(path)
        t = r["log"]["t"]
        R = Rotation.from_quat(r["quat"], scalar_first=True)

        worst = 0.0
        for u in dirs:
            lever = R.apply(u * 0.14)
            pp = [np.ptp(np.linalg.norm(
                      correct.detrend_rep(lever, a, b, t[a:b])[:, :2], axis=1))
                  for a, b in r["bounds"]]
            worst = max(worst, float(np.median(pp)))

        assert worst < 0.08, (
            f"{stem}: lever arm sweeps {worst*100:.1f} cm at |d|=14 cm, which "
            f"is back in the range the 8-13 cm claim asserted")


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_step_six_runs_and_is_off_by_default(path):
    """apply_offset must work when given d, and must not be applied without it.

    Off by default is a decision, not an oversight: d is unmeasured, B2 showed
    it cannot be fitted from the video, and a guessed d costs up to 0.8 cm.
    """
    from src import pipeline

    plain = pipeline.run(path)
    assert not any("apply_offset" in b for b in plain["blocked"])
    assert any("step 6 off" in n for n in plain["notes"])

    offset = pipeline.run(path, wrist_offset=np.array([0.0, -0.14, 0.0]))
    assert not offset["blocked"] or all("step 6" not in b for b in offset["blocked"])
    assert not np.allclose(offset["bar_position"], plain["bar_position"])


# --------------------------------------------------- the noise-floor log --
# Diagnostic captures of a watch lying still — no wrist, so no tremor and no
# lifting. Any log whose name is not a rep-labelled lift and which is quiet
# throughout qualifies; there are two so far and they agree, which is what
# makes the noise-floor numbers below worth trusting.
STATIONARY = [p for p in ALL_LOGS
              if not REP_COUNT.match(p.name)
              and p.stem.startswith(("stationary", "stable"))]


def _quietest(log: dict, span: float = 8.0) -> np.ndarray:
    """Indices of the quietest `span` seconds. Both button presses excluded.

    Not a fixed window: pressing Calibrate and pressing Finish bracket every
    capture with a few tenths of a second of real motion, and where they land
    depends on how long the recording is.
    """
    t = log["t"]
    mag = np.linalg.norm(log["gyro"], axis=1)
    best, at = None, 0.0
    for lo in np.arange(0.0, max(t[-1] - span, 0.1), 0.5):
        m = (t >= lo) & (t < lo + span)
        if m.sum() < 10:
            continue
        v = float(mag[m].std())
        if best is None or v < best:
            best, at = v, lo
    return np.flatnonzero((t >= at) & (t < at + span))


@pytest.mark.skipif(not STATIONARY, reason="no stationary capture")
@pytest.mark.parametrize("path", STATIONARY, ids=lambda p: p.stem)
def test_core_motion_residual_gyro_bias_is_negligible(path):
    """A watch on a table, and the number that reframes P4, P5, B1 and C1.

    Every one of those is built on "residual gyro bias is 0.1-0.9 deg/s", taken
    from the calibration pause of on-wrist captures. On a table — same sensor,
    same Core Motion, no wrist — the residual is **0.002 deg/s**, and it is not
    resolvable above its own noise (|mean|/SEM of 0.28-1.33 per axis).

    So Core Motion's gyro correction is essentially perfect at rest, and the
    0.93-1.05 deg/s measured on-wrist is the lifter's own slow rotation, not
    bias. There is almost nothing there to remove, which is a stronger reason
    for `calibrate.gyro_bias` defaulting to off than the one B1 recorded.

    What this does NOT show: that the residual stays this small THROUGH a set,
    with 20 g impacts and fast rotation perturbing Core Motion's estimator.
    That is the open question, and the two-anchor protocol (C1) is what would
    answer it. Do not read this test as closing P5.
    """
    log = io.load_log(path)
    g = log["gyro"][_quietest(log)]

    deg = 180.0 / np.pi
    assert np.linalg.norm(g.mean(axis=0)) * deg < 0.02, "expected ~0.002 deg/s at rest"

    sem = calibrate.bias_sem(g, log["fs"])
    snr = np.abs(g.mean(axis=0)) / sem
    assert snr.max() < 3.0, (
        f"the at-rest bias is now resolvable (SNR {snr.max():.1f}) — if that is "
        f"real, there IS a bias to remove and B1's default should be revisited")


@pytest.mark.skipif(not STATIONARY, reason="no stationary capture")
@pytest.mark.parametrize("path", STATIONARY, ids=lambda p: p.stem)
def test_body_frame_accel_bias_at_rest_is_small(path):
    """0.0025 g on a table, against ~0.035 g seen on-wrist in the press posture.

    The gap matters: 0.035 g is g*sin(2.0 deg), so the on-wrist figure is the
    size an attitude error of about two degrees would leak, not the size of the
    accelerometer's own bias. That points P3 at ATTITUDE rather than at sensor
    bias — and attitude error is exactly what a constant-bias estimator cannot
    fix, which is consistent with B6's oracle recovering only ~30%.
    """
    log = io.load_log(path)
    bias_g = np.linalg.norm(log["accel"][_quietest(log)].mean(axis=0)) / io.G
    assert bias_g < 0.01, f"body-frame accel bias at rest is {bias_g:.4f} g"


@pytest.mark.skipif(not STATIONARY, reason="no stationary capture")
@pytest.mark.parametrize("path", STATIONARY, ids=lambda p: p.stem)
def test_core_motion_attitude_is_stable_at_rest(path):
    """0.018 deg over 10 s — about 6.6 deg/hour. Core Motion's attitude is good.

    Worth pinning because the whole pipeline hangs off this quantity: a 1 deg
    attitude error injects 0.17 m/s^2 and integrates to ~34 cm over a 2 s rep.
    At rest there is no such error. Whatever goes wrong in the gym is not Core
    Motion failing to hold attitude when nothing is happening.
    """
    from scipy.spatial.transform import Rotation

    log = io.load_log(path)
    R = Rotation.from_quat(log["quat"][_quietest(log)], scalar_first=True)
    drift = np.degrees((R[-1] * R[0].inv()).magnitude())
    assert drift < 0.2, f"attitude drifted {drift:.3f} deg over 8 s at rest"

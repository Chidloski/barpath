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

# Must stay identical to pipeline.REP_LABEL. The optional middle token is a
# lift variant (bench_spoto_90x5); without it the three 2026-07-30 benches
# matched nothing, dropped out of CAPTURES, and every gate below skipped them
# silently — which is how a 6-window segmentation of a 5-rep set survived.
REP_COUNT = re.compile(r"^(bench|squat|deadlift)(?:_[a-z]+)*_[\d.]+x(\d+)")

# Every log, including non-lifts. Use for format-level checks — clipping,
# sampling, quaternion norms — which are about the FILE, not about lifting.
ALL_LOGS = sorted(RAW.glob("*.csv")) if RAW.is_dir() else []

# Rep-labelled lifts only. Nearly every gate here means "a set of reps", and
# data/raw/ now also holds diagnostic captures — a stationary watch on a table,
# for instance — where asking how many reps were found is meaningless.
CAPTURES = [p for p in ALL_LOGS if REP_COUNT.match(p.name)]

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data/raw/")

# Captures whose rep COUNT is wrong. P1 recorded counting as closed at 44/44,
# and it was, on the ten captures that existed on 2026-07-29. The 2026-07-30
# session added seven more and took it to 71/72 — `bench_spoto_90x5_1` counted
# the re-rack as a sixth rep, hidden by a REP_COUNT regex that did not match
# the 'spoto' variant token.
#
# EMPTY as of 2026-07-31 (C5): counting is 72/72. The cause was
# `segment._longest_cadence`'s tolerance of 1.6, which admitted the 4.50 s gap
# between the last rep and the re-rack (4.50/2.86 = 1.573) and grew a run of
# six that beat the true run of five on length. It is 1.45 now, the middle of a
# plateau that gives 17/17.
#
# Kept rather than deleted, with `xfail_if_miscounted`, because the next
# miscount wants recording the same way. But NOTE this mechanism is NOT strict:
# `pytest.xfail()` raises immediately, so an entry here masks a test whether it
# would pass or fail, and a fix does not announce itself the way
# KNOWN_ROM_FAILURES' does. Verify by hand before adding or removing one.
#
# Separate from KNOWN_ROM_FAILURES, which is about how far each window SPANS.
# A window can be miscounted with the right extent or counted right with the
# wrong extent, and squat_160x1 was exactly the second case.
WRONG_REP_COUNT: dict[str, str] = {}


def xfail_if_miscounted(path: Path) -> None:
    """xfail the captures whose rep count is a known defect."""
    for stem, reason in WRONG_REP_COUNT.items():
        if path.stem.startswith(stem):
            pytest.xfail(f"{path.stem}: {reason}")


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
    xfail_if_miscounted(path)
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


# ----------------------------------------------------- vertical ROM bounds --
# The only external check bench and squat have. Everything else in this file
# that compares against something outside the IMU needs either deadlift floor
# impacts or trackable video, and bench and squat have neither: bench video
# RAISES, squat video tracks at ~0.40 median NCC. So until this, a bench or
# squat reconstruction could be wrong by any factor at all and no gate here
# would notice.
#
# It is a weak check — a bound is not a measurement, and it constrains only the
# amplitude of one axis. But it is external, and it catches both ways a rep
# window can be wrong that a correct COUNT cannot see: spanning more than a rep,
# and spanning less. P1 closed counting at 44/44 while every window sat half a
# rep out of phase; this is a different question asked of the same windows.
SLACK_M = 0.02      # the bounds are anatomical, quoted to the nearest cm
# EMPTY as of 2026-07-31 (C5). It held the two defects this bound was written
# to catch, and both are fixed in `segment.py`:
#
#   bench_spoto_90x5_1 — segmented a 5-rep set into 6 windows; reps 5 and 6
#   came out 45.7 and 88.7 cm against a 35 cm bench bound. Cause: the cadence
#   tolerance was 1.6 where admitting the post-set gap needs 1.573. Now 5
#   windows at 27.6-30.0 cm.
#
#   squat_160x1 — reconstructed 18.0 cm for a single at 160 kg at a correct
#   count of 1 of 1, the first right-count-wrong-window failure any gate here
#   caught. Cause: a single leaves every cluster size 1, so the lateness
#   tie-break decided alone and picked the re-rack. Now 67.0 cm.
#
# What remains marginal, and was NOT introduced by C5: deadlift_180x3 rep 2
# reconstructs 61.1 cm against a 61 cm bound, inside SLACK_M and nothing else.
# It is the worst capture by measured horizontal error (P2) and the one that
# over-reads its impact step (P6); treat a drift past ~63 cm as that capture
# getting worse rather than as the bound being tight.
KNOWN_ROM_FAILURES: dict[str, str] = {}


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_reconstructed_rom_is_physically_possible(path):
    """Every rep's vertical ROM must be a range this lifter can move a bar through.

    Bounds are measured per lift (`truth.VERTICAL_ROM_M`); the floors are
    inferred, so read a floor violation as "that window is not a whole rep".

    Where this is measured matters. Run on `result["position"]` instead of
    `result["reps"]` — that is, before step 7 — the same numbers are absurd:
    deadlift_155x6_1 climbs from 100 cm on rep 1 to 1939 cm on rep 6. Passing
    here is therefore a statement about the detrended output only, and says
    nothing about the acceleration reaching the integrator, which is P3.

    The bounds are anatomical and quoted to the nearest centimetre, so this
    gate allows `SLACK_M` on each end where `truth.rom_flags` allows none. The
    flag is a thing to look at; a build failure is a claim that something is
    wrong. `deadlift_180x3` rep 2 lands at 61.1 cm against the 61 cm bound —
    worth surfacing in `pipeline.summary`, not worth failing over.
    """
    from src import pipeline, truth

    result = pipeline.run(path)
    reason = next((r for k, r in KNOWN_ROM_FAILURES.items()
                   if path.stem.startswith(k)), None)
    lo, hi = truth.VERTICAL_ROM_M[truth.lift_of(path)]
    flags = [f"rep {i}: {r*100:.1f} cm outside {lo*100:.0f}-{hi*100:.0f} cm"
             for i, r in enumerate(result["rep_rom_m"], 1)
             if not (lo - SLACK_M) <= r <= (hi + SLACK_M)]

    if reason is not None:
        if flags:
            pytest.xfail(f"{path.stem}: {reason}")
        pytest.fail(f"{path.stem} now passes the ROM bound. It used to fail: "
                    f"{reason}. Remove it from KNOWN_ROM_FAILURES.")

    assert not flags, f"{path.stem}: " + "; ".join(flags)


# ------------------------------------------------------------------- A2 --
VIDEO = Path(__file__).resolve().parents[1] / "data" / "video"

DEADLIFTS = [
    ("deadlift_155x6_1_20260728", "deadlift_155x6_1_20260728_122828", 6),
    ("deadlift_155x6_2_20260728", "deadlift_155x6_2_20260728_123603", 6),
    ("deadlift_180x3_20260728", "deadlift_180x3_20260728_121739", 3),
]

# Every bench capture. All seven sync as of C10 — under C8's peak-height
# threshold only the three spoto ones did, and that threshold turned out to be
# measuring clip composition. See metrics.bench_sync.
BENCH_SYNCED = [
    ("bench_90x4_1_20260727", 4),
    ("bench_90x4_2_20260727", 4),
    ("bench_90x4_3_20260727", 4),
    ("bench_92.5x2_20260727", 2),
    ("bench_spoto_90x5_1_20260730", 5),
    ("bench_spoto_90x5_2_20260730", 5),
    ("bench_spoto_90x5_3_20260730", 5),
]


def _has(video: str, csv: str) -> bool:
    return (VIDEO / f"{video}.mov").exists() and (RAW / f"{csv}.csv").exists()


def _csv_for(stem: str) -> Path | None:
    return next(RAW.glob(f"{stem}_*.csv"), None) if RAW.is_dir() else None


def _bench_video_events(path: dict, third: float = 3.0) -> tuple[list, list]:
    """Chest touches and lockouts from the tracked height. Video clock.

    A bench rep is one descent and one press, so the reps are the height
    minima. `third` keeps only extrema in the outer third of the travel, and
    0.8 s of refractory merges the frame-to-frame jitter around a turnaround.
    """
    from src import truth

    t = path["t"]
    h = truth._smooth(path["height"], 15)
    span = h.max() - h.min()

    def extrema(sign, keep):
        s = sign * h
        out: list[int] = []
        for i in range(1, len(s) - 1):
            if s[i] <= s[i - 1] and s[i] <= s[i + 1] and keep(h[i]):
                if not out or t[i] - t[out[-1]] > 0.8:
                    out.append(i)
        return [float(t[i]) for i in out]

    return (extrema(+1, lambda x: x < h.min() + span / third),
            extrema(-1, lambda x: x > h.max() - span / third))


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

    Measured from the bar resting on the floor, so it excludes the 22.25 cm
    bumper radius: true bar height at lockout is this plus that.

    The band used to be 0.40-0.85 m, which was wide enough to pass anything.
    It is now `truth.VERTICAL_ROM_M["deadlift"]`, whose ceiling is measured for
    this lifter — and at that width the check finally bites: `deadlift_155x6_2`
    reads 67-70 cm and fails. That is the video's scale error, not the lifter's
    ROM, and it is xfailed below rather than papered over.
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

    if csv.startswith("deadlift_155x6_2"):
        pytest.xfail(
            "the video's vertical scale is wrong on this capture: 67-70 cm of "
            "lockout against a 61 cm bound, from the same lifter and the same "
            "plate radius as deadlift_155x6_1's 60 cm. See truth.VERTICAL_ROM_M")

    lo, hi = truth.VERTICAL_ROM_M["deadlift"]
    for p in peaks:
        assert lo < p < hi, (
            f"lockout {p*100:.0f} cm above the floor is outside the "
            f"{lo*100:.0f}-{hi*100:.0f} cm deadlift ROM band")


@pytest.mark.parametrize("video", ["bench_90x4_1_20260727", "bench_92.5x2_20260727"])
def test_bench_auto_seeding_still_does_not_find_the_plate(video):
    """Automatic seeding on bench misses the plate entirely. Pin how badly.

    This replaces `test_bench_tracking_fails_loudly_rather_than_silently`,
    which asserted that `bar_path` RAISES on bench. It no longer does:
    `truth.SEEDS` carries a hand-placed seed per capture and all seven now
    track. That test asked to be replaced by a real one rather than deleted
    when a seed was wired in, and this is it — the underlying claim it was
    really pinning was about the SEEDER, not about `bar_path`, and that claim
    is unchanged.

    So test the seeder directly. `find_plate` is a dark-disc matched filter,
    and on a bench frame the plate is small, sits against a dark ceiling and
    abuts the lifter-and-bench silhouette — a larger, darker, rounder blob. It
    does not miss by a few pixels; it lands somewhere else in the frame.

    Not a tuning problem, and four attempts on 2026-07-31 say so: dark disc,
    circular-edge radial gradient, dark disc weighted by temporal motion
    energy, and a dark-annulus rim filter all preferred the clutter. If this
    test ever fails, auto-seeding has been solved and `truth.SEEDS` may be able
    to go — check that before assuming a regression. The real bench tracking
    gates live in tests/test_video_truth.py.
    """
    if not (VIDEO / f"{video}.mov").exists():
        pytest.skip(f"{video} not present")
    from src import truth

    _, cy, cx, radius = truth.SEEDS[video]
    stack, fps, _ = truth.frames(VIDEO / f"{video}.mov")
    frame = stack[truth.SEEDS[video][0]]
    y, x, _, _ = truth.find_plate(frame)

    miss = float(np.hypot(y - cy, x - cx))
    assert miss > radius, (
        f"{video}: find_plate landed {miss:.0f} px from the hand seed, inside "
        f"the {radius} px plate. Auto-seeding may now work — see the docstring")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_deadlift_tracking_is_clean_where_it_is_clean(video, csv, reps):
    """Deadlifts track well on the floor and badly at lockout. Both, asserted.

    **This test used to be called `..._is_clean_enough_to_trust` and asserted
    that no quality warning fired at all. That premise is dead**, and it is
    worth saying how it died rather than quietly relaxing it.

    Two separate defects have now been found in tracks this test was passing:

    *Dimensional.* `deadlift_155x6_2` tracks beautifully — 0.85 median NCC, a
    floor baseline steady to 0.4 cm, per-rep lockouts agreeing to a couple of
    centimetres — and reports 69.5 cm of travel against a 61 cm ceiling. A
    confident, self-consistent, wrongly scaled track. Caught by
    `test_video_rom_is_flagged_where_it_is_implausible`, not here.

    *Localised.* C12: the tracker loses the plate at LOCKOUT on all three
    deadlifts. Top-of-travel NCC 0.371/0.395/0.440 against whole-clip medians
    of 0.830/0.846/0.937 — and 97-100% of frames in the top 10 cm of travel
    score below GOOD_SCORE, against 0% in the bottom 10 cm.

    Both were invisible here for the same reason: this test read aggregates.
    `travel_m` is a whole-clip number and `median(score)` is a whole-clip
    number, and each stayed healthy while something specific went wrong. So it
    now asserts the aggregates AND the localised failure, and it will fail if
    either changes — including if the lockout track is FIXED, which is the
    outcome we want and which should delete the last block.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} not present")
    import warnings as w
    from src import truth

    with w.catch_warnings(record=True) as caught:
        w.simplefilter("always")
        path = truth.bar_path(VIDEO / f"{video}.mov")
    messages = " ".join(str(c.message) for c in caught)

    # The aggregates, which are genuinely fine and always were.
    assert path["travel_m"] > 0.40
    assert np.nanmedian(path["score"]) > truth.GOOD_SCORE

    # The floor is where this tracker earns its keep — and where every gate
    # that depends on it (impacts, landings, sync, rest instants) reads.
    height, score = path["height"], path["score"]
    ok = np.isfinite(height) & np.isfinite(score)
    low = ok & (height < np.nanmin(height[ok]) + 0.10)
    assert (score[low] > truth.GOOD_SCORE).mean() > 0.95, (
        f"{video}: the tracker has stopped being reliable at the FLOOR too. "
        f"That breaks the landings, the sync and rest_instants, not just the "
        f"lockout — this is much worse than C12 and wants investigating first")

    # And the lockout failure, pinned so that fixing it is visible.
    assert truth.top_of_travel_score(path) < truth.GOOD_SCORE
    assert "losing the plate at LOCKOUT" in messages, (
        f"{video}: the lockout warning no longer fires. If better footage or a "
        f"better tracker fixed it, delete this block, re-measure every deadlift "
        f"beats_null, and update P2 — they are currently 15-45% too generous")


# ------------------------------------------------------------------- A4 --
@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_pipeline_runs_end_to_end_without_raising(path):
    """All nine steps run, and that is a statement about coverage only.

    This used to assert the OPPOSITE — `result["blocked"]` non-empty, because
    `project.project_to_plane` and `project.confidence` raised
    `NotImplementedError` and the driver's job was to record that rather than
    throw. Step 8 was implemented on 2026-07-30 and the premise inverted: 17 of
    17 captures now complete.

    Do not read that as progress toward the spec. The pipeline is still 5-15x
    outside its horizontal target where anything can measure it (P2), the
    display axis's sign is unresolved (B4), and 6 of 17 sets do not earn
    `project.confidence` at all. A completing pipeline is not a working one, and
    this gate deliberately asserts nothing about quality — `vs_truth` and the
    ROM bounds do that.
    """
    from src import pipeline

    result = pipeline.run(path)
    assert not result["blocked"], (
        f"{path.stem}: stages blocked again — {result['blocked']}. Step 8 was "
        f"implemented; if something now raises, the driver is right to record "
        f"it but this gate needs re-pinning")
    xfail_if_miscounted(path)
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


# Measured 2026-07-31 (C9), extended to all seven captures by C10. The video's
# chest touch lands at this fraction through each IMU rep window. A window HALF
# A REP out of step would put it near 0.0 or 1.0; nothing is close.
#
# **The spread across captures is the evidence, not the value.** C9 had only the
# three spoto captures and they all sat near 0.60, which a constant bias would
# also produce. C10 added four more and they run 0.42-0.56 — and the video's own
# descent fraction, measured with no IMU and no sync, tracks each one (shown in
# the comments). `bench_92.5x2` is the sharpest case: a 2-count chest pause puts
# its touch at 0.424 and the video independently says 0.431. The segmenter is
# following per-capture rep structure, not sitting at a number.
BENCH_TOUCH_PHASE = {
    "bench_90x4_1_20260727": 0.559,          # video 0.504
    "bench_90x4_2_20260727": 0.558,          # video 0.518
    "bench_90x4_3_20260727": 0.537,          # video 0.521
    "bench_92.5x2_20260727": 0.424,          # video 0.431, 2-count pause
    "bench_spoto_90x5_1_20260730": 0.593,    # video 0.573
    "bench_spoto_90x5_2_20260730": 0.613,    # video 0.590
    "bench_spoto_90x5_3_20260730": 0.619,    # video 0.582
}


@pytest.mark.parametrize("video,reps", BENCH_SYNCED, ids=[b[0] for b in BENCH_SYNCED])
def test_bench_rep_windows_are_in_phase_with_the_video(video, reps):
    """Bench windows hold exactly one chest touch, at ~0.6 through the window.

    **This is the first measurement of bench phase in the project.** Until C8
    gave bench a video clock sync there was no external time reference on this
    lift at all, and CLAUDE.md's P1 recorded the question as unverifiable. It
    is the half of P1 that matters: counting was clean at 72/72 and window
    extent was clean, while phase was untested — and phase is exactly what a
    clean count hides. The old segmenter scored a perfect 44/44 on deadlift
    while every window ran half a rep out of step.

    `_full_cycles` intends a bench window to run lockout -> descend -> chest ->
    press -> lockout, so the touch belongs strictly inside, one per window. Out
    of phase would mean 0 or 2 touches, or one sitting at the very edge.

    Result: **29 of 29 windows, one touch each**, phase 0.42-0.62. Bench windows
    are in phase. Note what this does NOT say — it constrains where the window
    sits relative to the bar, not whether the reconstructed PATH inside it is
    right, which is P2's 0.64-3.67 cm.

    C9 measured this on three captures, all near 0.60; C10 added the other four
    and they run 0.42-0.56. The spread is what makes it evidence — see
    `BENCH_TOUCH_PHASE`.

    On the sync's known weakness: `bench_sync`'s peak is only weakly isolated,
    its rivals one rep period away. A whole-rep-period error is invisible here
    BY CONSTRUCTION, because a periodic set looks the same shifted by one rep —
    so this test is robust to exactly the ambiguity bench_sync cannot resolve.
    A FRACTIONAL-period error would show up as a phase disagreeing with the
    video's own descent fraction, and none does: the seven captures track it
    individually to 0.007-0.055 across a 0.42-0.62 spread.
    """
    csv_path = _csv_for(video)
    if not (VIDEO / f"{video}.mov").exists() or csv_path is None:
        pytest.skip(f"{video} not present")
    from src import metrics, pipeline, truth

    result = pipeline.run(csv_path)
    path = truth.bar_path(VIDEO / f"{video}.mov")
    starts = [float(result["log"]["t"][a]) for a, _ in result["bounds"]]
    offset = metrics.bench_sync(path, result["log"], result["velocity"][:, 2],
                                float(np.median(np.diff(starts))))["offset"]
    touches, _ = _bench_video_events(path)

    t = result["log"]["t"]
    bounds = result["bounds"]
    assert len(bounds) == reps

    phases = []
    for n, (a, b) in enumerate(bounds, 1):
        t0, t1 = float(t[a]), float(t[b - 1])
        inside = [(x + offset - t0) / (t1 - t0)
                  for x in touches if t0 <= x + offset <= t1]
        assert len(inside) == 1, (
            f"{video} rep {n} [{t0:.1f},{t1:.1f}] contains {len(inside)} chest "
            f"touches, expected 1 — the window is out of phase with the bar")
        phases.append(inside[0])

    want = BENCH_TOUCH_PHASE[video]
    got = float(np.median(phases))
    assert abs(got - want) < 0.08, (
        f"{video}: chest touch at {got:.3f} through the window against "
        f"{want:.3f} when C9 measured it")
    assert 0.15 < min(phases) and max(phases) < 0.85, (
        f"{video}: a touch sits at the window edge ({min(phases):.2f}-"
        f"{max(phases):.2f}) — that is the half-a-rep-out failure mode")


@pytest.mark.parametrize("video,reps", BENCH_SYNCED, ids=[b[0] for b in BENCH_SYNCED])
def test_a_bench_rep_really_is_asymmetric(video, reps):
    """0.6 is the bar's own behaviour, not a segmentation bias. Video only.

    The test above finds the chest touch ~60% of the way through each IMU
    window rather than at the 50% a symmetric rep would give. That 0.1 gap is
    either a real property of benching or a systematic error in where the
    windows sit, and the two are not distinguishable from the IMU.

    So measure it in the video alone — no IMU, no sync, no reconstruction.
    Lockout to touch, over lockout to lockout. Across the seven captures the
    descent takes **0.431 to 0.590** of a rep by median, against the IMU
    windows' 0.424 to 0.619, tracking each capture individually to 0.007-0.055.

    A bench descent is controlled and a press is not: 1.6-1.9 s down against
    1.2-1.3 s up on a touch-and-go set. `bench_92.5x2` is the case that makes
    this an argument rather than a coincidence — its 2-count chest pause moves
    the touch to 0.431, well away from the others, and the IMU window follows to
    0.424. A constant bias could produce a cluster near 0.6; it cannot produce
    that.

    *Rep 1 of every set is excluded from the median rather than fitted around:
    it reads 0.69-0.73 because the "descent" there starts at the unrack, which
    includes the lift-off and settle. That is a property of the video landmark,
    not of the rep.*
    """
    if not (VIDEO / f"{video}.mov").exists():
        pytest.skip(f"{video} not present")
    from src import truth

    path = truth.bar_path(VIDEO / f"{video}.mov")
    touches, lockouts = _bench_video_events(path)

    fracs = []
    for x in touches:
        before = [y for y in lockouts if y < x]
        after = [y for y in lockouts if y > x]
        if before and after:
            fracs.append((x - before[-1]) / (after[0] - before[-1]))

    assert len(fracs) >= reps - 1
    got = float(np.median(fracs))

    # The assertion is AGREEMENT, not a band. A band was tried first and it was
    # the weaker test: it read 0.50-0.68, which `bench_92.5x2` breaks at 0.431
    # — and that capture is the strongest evidence here rather than an
    # exception, because its pause moves BOTH modalities together.
    want = BENCH_TOUCH_PHASE[video]
    assert abs(got - want) < 0.08, (
        f"{video}: the video puts the bottom of the rep at {got:.3f} and the "
        f"IMU window at {want:.3f}. They tracked each other to 0.055 across "
        f"seven captures spanning 0.42-0.62, so a gap this size means one of "
        f"the two has moved and the ~0.6 phase needs re-explaining")


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
    "deadlift_155x6_1": 5.05,       # was 5.1 at the assumed 450 mm plate
    "deadlift_155x6_2": 9.19,       # was 9.2
    "deadlift_180x3": 15.44,        # was 15.4
}
# Re-pinned 2026-07-30 against the measured 445 mm deadlift bumper. The whole
# correction is worth under 1% here, which is the useful negative result: the
# plate diameter was never what made these numbers 5-15x out of spec.
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


# beats_null: the pipeline's horizontal error against the error from drawing NO
# fore-aft motion at all. >1 means the reconstruction carries information; <1
# means a flat line would score better. Measured 2026-07-31 (C10) on every
# capture with video, and unchanged at C11.
BEATS_NULL = {
    "bench_90x4_1_20260727": 1.10,
    "bench_90x4_2_20260727": 4.80,
    "bench_90x4_3_20260727": 4.03,
    "bench_92.5x2_20260727": 1.14,
    "bench_spoto_90x5_1_20260730": 0.72,
    "bench_spoto_90x5_2_20260730": 0.80,
    "bench_spoto_90x5_3_20260730": 0.92,
    "deadlift_155x6_1_20260728": 0.70,
    "deadlift_155x6_2_20260728": 0.35,
    "deadlift_180x3_20260728": 0.13,
}
NULL_FLOOR = 0.80          # 20% headroom, matching CEILING's logic above


@pytest.mark.parametrize("video", sorted(BEATS_NULL), ids=lambda v: v)
def test_beats_null_does_not_regress(video):
    """Six of ten captures lose to a flat line. Pin that so it cannot worsen.

    `beats_null` is one line of arithmetic that nobody had run in the life of
    this project, and it reframes every horizontal number in it: measured
    against drawing no fore-aft motion at all, most of the reconstruction
    subtracts information rather than adding it. All three deadlifts lose, at
    0.70, 0.35 and 0.13.

    This is the cheapest guard available against the failure mode that let
    milestones 1-6 pass — reporting a change as an improvement when the thing
    it improved still loses to doing nothing. A change that lowers horizontal
    rms while lowering this too has not helped.
    """
    csv = _csv_for(video)
    if csv is None or not (VIDEO / f"{video}.mov").exists():
        pytest.skip(f"{video} not present")
    from src import metrics, pipeline

    result = pipeline.run(csv, video=VIDEO / f"{video}.mov")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")
    assert m["beats_null"] > BEATS_NULL[video] * NULL_FLOOR, (
        f"{video}: beats_null fell to {m['beats_null']:.2f} from the "
        f"{BEATS_NULL[video]:.2f} measured at C10")


@pytest.mark.xfail(reason="P2/P3 — six of ten captures lose to a flat line",
                   strict=False)
@pytest.mark.parametrize("video", sorted(BEATS_NULL), ids=lambda v: v)
def test_the_reconstruction_beats_drawing_nothing(video):
    """The floor beneath the spec: be better than a straight vertical line.

    xfail for the same reason `test_horizontal_meets_the_spec` is — so the
    target is executable and visible on every run rather than living in prose.
    It is a far weaker bar than the 1 cm spec and the pipeline fails it on six
    of ten captures, so expect four XPASS here (`bench_90x4_1`, `_2`, `_3` and
    `bench_92.5x2`). When a change makes the rest pass, tighten BEATS_NULL and
    delete this.
    """
    csv = _csv_for(video)
    if csv is None or not (VIDEO / f"{video}.mov").exists():
        pytest.skip(f"{video} not present")
    from src import metrics, pipeline

    result = pipeline.run(csv, video=VIDEO / f"{video}.mov")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")
    assert m["beats_null"] > 1.0, (
        f"{video}: drawing a flat vertical line scores "
        f"{m['null_h_rms']:.2f} cm against the pipeline's "
        f"{m['pipeline_h_rms']:.2f}")


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_dispersion_is_finite_and_reported(path):
    """dispersion must run on every MULTI-REP capture and produce usable numbers.

    Single-rep sets are excluded rather than special-cased, and `pipeline.run`
    is right to omit the key: dispersion is rep-to-rep spread, so on one rep it
    has nothing to measure. `squat_160x1` from the 2026-07-30 session is the
    first such capture and is the reason this is stated at all.
    """
    from src import metrics, pipeline

    if truth_reps(path) < 2:
        pytest.skip(f"{path.stem} is a single — dispersion needs >=2 reps")

    result = pipeline.run(path)
    d = result["dispersion"]
    xfail_if_miscounted(path)
    assert d["n_reps"] == truth_reps(path)
    for key in ("horizontal_rms", "horizontal_p95", "vertical_rms"):
        assert np.isfinite(d[key]) and d[key] >= 0
    assert d["horizontal_p95"] >= d["horizontal_rms"] * 0.5
    assert np.isfinite(d["per_axis_rms"]).all()


@needs_data
@pytest.mark.parametrize("stem", ["bench_spoto_90x5_1", "squat_130x5"])
def test_dispersion_flatters_a_broken_pipeline(stem):
    """The caveat in dispersion's docstring, asserted rather than promised.

    Dispersion reports well under 2 cm of rep-to-rep spread on bench and squat
    — comfortably inside the 1 cm-ish spec band. The reason is structural:
    error that repeats every rep lands in the mean rep and cancels out of every
    deviation from it, so a pipeline dominated by P3 scores well here by
    construction.

    **Rewritten 2026-07-31, and the point got sharper rather than weaker.**
    This used to assert the good dispersion number alongside `vs_truth` REFUSING
    to produce one, on the grounds that bench had no trustworthy video. Bench
    now has one. So the second half is no longer "there is no truth to check
    against" but the stronger "there IS, and it disagrees": on
    `bench_spoto_90x5_1` dispersion says under 2 cm of spread while the video
    says 3.67 cm of horizontal error. A metric needing no ground truth reported
    inside spec on a capture measured to be outside it.

    Squat keeps the older form, because squat video genuinely is not truth —
    see `test_vs_truth_refuses_squat`. Between them the two parametrisations
    cover both failure modes: flattery with no referee, and flattery with one.
    """
    from src import metrics, pipeline

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    assert result["dispersion"]["horizontal_rms"] < 2.0

    if stem.startswith("squat"):
        with pytest.raises(ValueError, match="refuses squat"):
            metrics.vs_truth(result, VIDEO / "deadlift_155x6_1_20260728.mov")
        return

    video = VIDEO / f"{path.stem.rsplit('_', 1)[0]}.mov"
    if not video.exists():
        pytest.skip(f"{video.name} not present")
    m = metrics.vs_truth(result, video)
    assert m["pipeline_h_rms"] > result["dispersion"]["horizontal_rms"], (
        f"{stem}: dispersion {result['dispersion']['horizontal_rms']:.2f} cm no "
        f"longer flatters the {m['pipeline_h_rms']:.2f} cm measured against "
        f"video — check which one moved before relaxing this")


@needs_data
@pytest.mark.parametrize("stem", ["squat_130x5", "squat_140x4_1"])
def test_vs_truth_refuses_squat(stem):
    """Squat is not truth, so vs_truth must raise rather than guess.

    Narrowed from bench-and-squat on 2026-07-31. Bench used to be refused on
    the grounds that it "does not seed automatically", which was true of
    `find_plate` and is no longer true of the shipped path — `truth.SEEDS`
    seeds it by hand and `metrics.bench_sync` aligns it to the IMU clock. Bench
    is scored now, on the three of seven captures whose correlation clears the
    floor.

    Squat's refusal stands and its reasons got worse rather than better. It
    tracks at median NCC ~0.40 with the plate leaving the top of frame at
    lockout, and of the four 2026-07-30 captures two do not track at all while
    two report ~12.5 cm of travel against a 45-76 cm band. Returning a number
    from that would invent the ground truth this module exists to supply — the
    exact move that let a broken pipeline look validated for months. The fix is
    a wider shot, not code.
    """
    from src import metrics, pipeline

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    with pytest.raises(ValueError, match="refuses squat"):
        metrics.vs_truth(result, VIDEO / "deadlift_155x6_1_20260728.mov")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_video_truth_is_physically_sane(video, csv, reps):
    """Guard the metric itself: if these drift, distrust the number, not the pipeline.

    A metric is only as good as the truth behind it, and this one leans on the
    video scale and on the IMU-video sync. These are the quantities that would
    make vs_truth confidently wrong, so they are asserted alongside it rather
    than taken on faith.

    The plate diameters are measured now (2026-07-30) rather than assumed, and
    that turned out not to be where the scale error was: 450 -> 445 mm moved
    everything about 1%, while the per-capture ROM spread is 19 cm. The ROM
    assertion below is the one that finds it.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")

    assert m["sync_rms_ms"] < 50.0, "rep timing is specified at +/-50 ms"
    assert abs(m["sync_drift_pct"]) < 1.0

    if csv.startswith("deadlift_155x6_2"):
        pytest.xfail("video vertical scale wrong on this capture; "
                     "see truth.VERTICAL_ROM_M")
    lo, hi = truth.VERTICAL_ROM_M["deadlift"]
    assert lo * 100 < m["video_rom_cm"] < hi * 100, (
        f"video ROM {m['video_rom_cm']:.0f} cm is not a deadlift ROM for this "
        f"lifter ({lo*100:.0f}-{hi*100:.0f} cm)")
    assert 2.0 < m["video_fore_aft_cm"] < 25.0, (
        "real fore-aft travel is 10-20 cm; outside that the tracker or the "
        "plate scale is wrong")


# Per-rep video ROM, measured 2026-07-30 against the 445 mm bumper. Same
# lifter, same lift, three captures — and a 19 cm spread, which a range of
# motion set by the lifter's own limbs cannot have.
VIDEO_ROM_CM = {
    "deadlift_155x6_1": 59.1,
    "deadlift_155x6_2": 66.8,   # over the 61 cm bound
    "deadlift_180x3": 47.6,     # implausibly low, and NOT flagged — see below
}


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_video_rom_is_flagged_where_it_is_implausible(video, csv, reps):
    """The referee is checked against the same bounds as the pipeline.

    This test asserts a defect, not a capability. `vs_truth` is the only
    external judge of P2, and on one of its three captures it measures the bar
    travelling 66.8 cm through a range whose ceiling is 61 — so its vertical
    scale is wrong there, and every vertical number it reports on that capture
    inherits the error. Pinning it here keeps that visible until the footage is
    re-shot with a known vertical reference in frame.

    Note what is NOT caught. `deadlift_180x3` reads 47.6 cm, 12 cm below the
    other 155 kg set and about 20% low, and it passes: the sanity floor is 40 cm
    and nothing measured justifies raising it to 50. So the flag is one-sided in
    practice, and a capture can still referee P2 with a scale ~20% too small.
    That capture is also the worst by horizontal error (15.4 cm) and the one
    that over-reads its impact velocity step by 58-72% (P6). Three independent
    complaints about the same capture is not a coincidence, and it is not
    diagnosed.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    m = metrics.vs_truth(result, VIDEO / f"{video}.mov")
    stem = next(k for k in VIDEO_ROM_CM if csv.startswith(k))

    assert abs(m["video_rom_cm"] - VIDEO_ROM_CM[stem]) < 1.0, (
        f"video ROM moved from {VIDEO_ROM_CM[stem]} to {m['video_rom_cm']:.1f} cm")

    hi = truth.VERTICAL_ROM_M["deadlift"][1] * 100
    assert bool(m["video_rom_flags"]) == (VIDEO_ROM_CM[stem] > hi), (
        f"{stem}: ROM {m['video_rom_cm']:.1f} cm vs a {hi:.0f} cm bound, but "
        f"flags={m['video_rom_flags']}")

    if stem == "deadlift_155x6_2":
        # The whole point, on the one capture that makes it: judged by the same
        # table, the video fails the bound and the IMU it is refereeing passes.
        assert m["video_rom_flags"]
        assert not truth.rom_flags("deadlift", result["rep_rom_m"]), (
            "the reconstruction now fails the bound too, so this capture no "
            "longer shows the referee failing alone")


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
    """0.0025 g on a table. The number the pipeline's residuals are read against.

    This docstring used to draw a conclusion from the gap to a 0.035 g on-wrist
    figure — that 0.035 g is g*sin(2.0 deg), so the on-wrist number was a two
    degree attitude error. C6 retracted that on both counts: the 0.035 g is a
    VERTICAL residual and vertical leaks g*(1-cos theta), which needs 15.2 deg;
    and the figure does not survive the acceleration sign fix. See
    `test_the_two_degree_attitude_error_is_not_there`.

    What the 0.0025 g is genuinely good for is the comparison C6 does make:
    bench and squat leave 0.003 g of per-rep residual, i.e. this floor, so
    there is nothing on those lifts to explain beyond the sensor itself.
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


# ------------------------------------------------------------------- C6 --
# The two-anchor measurement C1 was built for. Only the 2026-07-30 captures
# have both holds; older ones have no closing hold and are excluded by
# `calibrate.anchor_tilt` raising rather than by a filter here, so a capture
# that acquires a phase column joins automatically.
TWO_ANCHOR = [p for p in CAPTURES if p.stem.split("_2026")[0] in {
    "bench_spoto_90x5_1", "bench_spoto_90x5_2", "bench_spoto_90x5_3",
    "squat_140x4_1", "squat_140x4_2", "squat_140x4_3", "squat_160x1"}]


@needs_data
@pytest.mark.parametrize("path", TWO_ANCHOR, ids=lambda p: p.stem)
def test_a_working_set_does_not_wreck_core_motions_attitude(path):
    """The answer C1 was built to get, and it is "no lasting damage".

    Measured 2026-07-30: tilt error bounds at 0.05 deg at the opening anchor
    and 0.14 deg at the closing anchor, across 40-55 s of loaded lifting with
    20 g impacts in it. Gyro-only propagation over the same span drifts
    0.35-1.49 deg, so Core Motion's fusion is doing real work and winning.

    Deliberately asserts only the two ends, never `change_deg`. The watch is
    not in the same posture at both anchors — 3.5 to 161 deg between them — so
    the body-frame accel bias projects differently at each, and the change
    moves for reasons that have nothing to do with the attitude. Both figures
    are upper bounds for the same reason: 0.0025 g of accel bias is
    g*sin(0.143 deg), which is the closing-anchor median itself.

    The ceiling is 0.5 deg, well above the 0.27 deg worst case, because this
    gate exists to catch a REGIME change — a set that leaves the attitude
    degrees out — not to pin a number that will wander with how still the
    lifter stood.
    """
    from src import calibrate, orient

    log = io.load_log(path)
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    a = calibrate.anchor_tilt(log, world)

    assert a["open_deg"] < 0.2, (
        f"the OPENING hold is already {a['open_deg']:.2f} deg out, before any "
        f"lifting has happened")
    assert a["close_deg"] < 0.5, (
        f"attitude is {a['close_deg']:.2f} deg out after {a['span_s']:.0f} s "
        f"of lifting — a set now damages the attitude solution, which it did "
        f"not on 2026-07-30")
    assert a["gyro_only_deg"] > a["close_deg"], (
        "gyro-only propagation is no worse than Core Motion's fusion, so the "
        "fusion is no longer buying anything")


@needs_data
def test_the_two_degree_attitude_error_is_not_there():
    """P4 inferred a ~2 deg attitude error. Retracted 2026-07-30, twice over.

    It rested on `analysis/11`'s 0.035 g, and two things are wrong with the
    inference:

    1. That figure is a VERTICAL residual, off-pipeline, from before the
       acceleration sign fix (3c2cbed). It does not survive: bench_92.5x2, the
       capture it was measured on, now reads 0.0005 g per rep.
    2. Converting it with g*sin(theta) is the horizontal leak. Vertical leaks
       g*(1-cos theta) — orient.py's own docstring states the asymmetry. 0.035 g
       of VERTICAL implies 15.2 deg, not 2.0. The anchors exclude that by two
       orders of magnitude.

    This test pins the arithmetic and the data, so the claim cannot come back
    without both being re-argued.
    """
    from src import orient, pipeline

    assert abs(np.degrees(np.arcsin(0.035)) - 2.0) < 0.05          # the sin
    assert abs(np.degrees(np.arccos(1 - 0.035)) - 15.2) < 0.1      # the truth
    assert (1 - np.cos(np.radians(2.0))) < 0.001, (
        "a 2 deg tilt puts under 0.001 g into vertical, not 0.035")

    path = next((p for p in CAPTURES if p.stem.startswith("bench_92.5x2")), None)
    if path is None:
        pytest.skip("bench_92.5x2 not present")
    result = pipeline.run(path)
    log = result["log"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    per_rep = [abs(world[a:b, 2].mean()) / io.G for a, b in result["bounds"]]

    assert max(per_rep) < 0.005, (
        f"the vertical residual P4 was built on is back: {max(per_rep):.4f} g "
        f"against the 0.035 g that analysis/11 recorded")


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_per_rep_residual_is_at_the_noise_floor_except_on_deadlift(path):
    """A rep starts and ends at rest, so its mean world acceleration is zero.

    Whatever is left is error, in the same units as the still-hold residual, so
    the two are directly comparable. Measured: bench and squat sit at 0.003 g,
    which is the 0.0025 g accel bias measured on a table — nothing to explain.
    Deadlift runs 0.010-0.030 g, and `test_the_deadlift_residual_enters_at_the
    _floor_impact` localises it.

    Excludes the two captures with known bad windows: a window that spans the
    re-rack has a large genuine net acceleration and this check would be
    measuring the segmenter, not the sensor.
    """
    from src import orient, pipeline

    if any(path.stem.startswith(k) for k in KNOWN_ROM_FAILURES):
        pytest.skip(f"{path.stem} has known bad rep windows; see P1")

    result = pipeline.run(path)
    log = result["log"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    med = float(np.median([np.linalg.norm(world[a:b].mean(axis=0)[:2]) / io.G
                           for a, b in result["bounds"]]))

    ceiling = 0.05 if path.stem.startswith("deadlift") else 0.008
    assert med < ceiling, f"{path.stem}: per-rep horizontal residual {med:.4f} g"
    if not path.stem.startswith("deadlift"):
        assert med > 0.0005, (
            f"{path.stem}: {med:.4f} g is BELOW the sensor's own noise floor, "
            f"which means this is measuring nothing")


@needs_data
@pytest.mark.parametrize("stem", ["deadlift_155x6_1", "deadlift_155x6_2",
                                  "deadlift_180x3"])
def test_the_deadlift_residual_enters_at_the_floor_impact(stem):
    """6% of the samples carry ~75% of the deadlift's per-rep error.

    Excluding +/-100 ms around each impact takes the residual from 0.015-0.031 g
    to 0.006-0.010 g. That is not an argument for discarding those samples — the
    impulse there is real and B5 measured it against video at a ratio of 1.04.
    It says the error is concentrated where the signal is largest and where
    Core Motion's gravity reference is most corrupted, which is the first
    specific location P3 has ever had.
    """
    from src import orient, pipeline, segment

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    log = result["log"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    imp = segment.impact_anchors(log)

    def residual(pad_ms):
        pad = int(pad_ms * log["fs"] / 1000)
        keep = np.ones(len(world), bool)
        for k in imp:
            keep[max(0, k - pad):k + pad + 1] = False
        return float(np.median(
            [np.linalg.norm(world[a:b][keep[a:b]].mean(axis=0)[:2]) / io.G
             for a, b in result["bounds"] if keep[a:b].sum() > 10]))

    whole, without = residual(0), residual(100)
    assert without < whole * 0.75, (
        f"{stem}: excluding the impact moved the residual {whole:.4f} -> "
        f"{without:.4f} g. The impact is no longer where the error enters")


@needs_data
@pytest.mark.parametrize("stem", ["deadlift_155x6_1", "deadlift_155x6_2",
                                  "deadlift_180x3"])
def test_deadlift_vertical_momentum_does_not_close(stem):
    """A defect this project had not recorded, on the axis assumed to be fine.

    Measured between `segment.rest_instants`, which are validated against video
    at |v| < 0.10 m/s, so the bar really is at rest at both ends and the
    integral of vertical acceleration between them must be zero. It is -0.37 to
    -1.48 m/s, negative on 8 of 9 intervals.

    Rep windows are the WRONG place to measure this and the first version of
    this test used them, reporting -0.05 to -2.36 m/s. Every rep boundary sits
    exactly 10 ms after its impact — one sample into a 2-3 sample spike — so
    part of one impulse falls outside the window and the figure inherits the
    boundary placement. The defect is real; that range overstated it.

    This does not contradict B5. B5 measured the velocity STEP across the
    impact against video and got a ratio of 1.04; that is a local measurement
    over a few hundred milliseconds and it is right. The deficit is what the
    rest of the rep does, and the per-rep detrend hides it completely — which
    is why vertical ROM comes out at a plausible 53-61 cm regardless.

    Asserts the defect, not a target. It should fail when B6 fixes it.
    """
    from src import orient, pipeline, segment

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    log = result["log"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    rest = segment.rest_instants(log)
    if len(rest) < 2:
        pytest.skip(f"{stem}: fewer than two validated rest instants")

    dv = [float(np.trapezoid(world[a:b, 2], log["t"][a:b]))
          for a, b in zip(rest, rest[1:])]

    assert np.median(dv) < -0.2, (
        f"{stem}: median vertical closure between rest instants "
        f"{np.median(dv):.2f} m/s has improved — if that was deliberate, "
        f"re-pin this test")
    assert min(dv) > -2.0, (
        f"{stem}: closure {min(dv):.2f} m/s is worse than anything measured")


# ------------------------------------------------------------------ C11 --
@pytest.mark.parametrize("video,reps", BENCH_SYNCED, ids=[b[0] for b in BENCH_SYNCED])
def test_bench_vertical_momentum_closes(video, reps):
    """The control the deadlift deficit needed: loaded lifting, no impact.

    Between two moments the video says the bar was still, the integral of
    vertical acceleration must be zero. On bench it is, to |dv| <= 0.102 m/s
    over 44 intervals on all seven captures — 0.0019 g of residual, which is
    the 0.0025 g accel bias measured on a table. Bench closes at the sensor's
    own noise floor.

    Deadlift, measured identically, loses 0.36-1.43 m/s on every interval with
    a floor impact in it. See the sibling test.

    This is asserted as a PASS, unlike almost everything else in this file, so
    it will start failing if a change to the world-frame acceleration breaks
    the one lift that currently works. It is also the reason B6 may splice at
    the impact rather than reworking the integrator: the integrator is fine.
    """
    csv = _csv_for(video)
    if csv is None or not (VIDEO / f"{video}.mov").exists():
        pytest.skip(f"{video} not present")
    from src import metrics, pipeline

    result = pipeline.run(csv, video=VIDEO / f"{video}.mov")
    m = metrics.momentum_closure(result, VIDEO / f"{video}.mov")

    assert m["n_with_impact"] == 0, (
        f"{video}: impact_anchors found {m['n_with_impact']} floor impacts on a "
        f"bench press, which is a segmentation bug, not a closure result")
    assert m["n_intervals"] >= 2
    assert m["max_abs_dv"] < 0.15, (
        f"{video}: vertical momentum closes to {m['max_abs_dv']:.3f} m/s, "
        f"against 0.102 measured at C11. Bench was the impact-free control and "
        f"it has stopped closing")
    assert abs(m["median_dv"]) < 0.05


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_the_momentum_deficit_is_the_floor_impact(video, csv, reps):
    """Within one capture: the pull closes and the landing does not.

    The dwell detector splits a deadlift rep at the lockout, so the concentric
    and the descent-plus-landing are separate intervals of the same capture.
    Floor-to-lockout carries 55-66 cm of loaded bar travel and closes to
    |dv| <= 0.063 m/s; every interval containing an impact loses 0.36-1.43.

    Same lift, same load, same wrist, same calibration, same 30 seconds of
    recording. The only thing the two halves do not share is the landing, so
    this rules out the whole family of explanations that blame the lift, the
    load or the reconstruction generally — which the bench comparison alone
    could not.

    Do not judge these intervals by peak acceleration. A 155 kg pull leaves the
    wrist's total |accel| at 0.6-1.1 g, indistinguishable from resting, and
    reading that number is how these were twice mistaken for the bar sitting on
    the floor. The video's bar travel is what separates them.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline

    result = pipeline.run(RAW / f"{csv}.csv", video=VIDEO / f"{video}.mov")
    m = metrics.momentum_closure(result, VIDEO / f"{video}.mov")

    with_impact = [iv["dv"] for iv in m["intervals"] if iv["spans_impact"]]
    clean = [iv["dv"] for iv in m["intervals"] if not iv["spans_impact"]]
    assert with_impact and clean, (
        f"{csv}: {len(with_impact)} impact intervals and {len(clean)} clean — "
        f"this test needs both halves of a rep to compare")

    assert max(with_impact) < -0.2, (
        f"{csv}: an impact-spanning interval closed to {max(with_impact):+.3f} "
        f"m/s. If B6 fixed this, re-pin the test and say so")
    assert max(abs(d) for d in clean) < 0.15, (
        f"{csv}: a pull-only interval failed to close "
        f"({max(clean, key=abs):+.3f} m/s), so the deficit is no longer "
        f"isolated to the landing and C11's attribution needs redoing")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_the_impact_amplitude_is_right_and_its_net_is_not(video, csv, reps):
    """Why B5's 1.04 and C11's deficit are both true. Measured together.

    B5 reports the impact's velocity step at a median 1.04 of the video's, and
    it is right — it measures min-to-max AMPLITUDE within +/-0.3 s, and its
    docstring explicitly warns off net-change windows. C11 measures the net,
    which is the quantity the closure identity constrains, and gets ~0.4.

    Both on the same 15 impacts: amplitude ratio ~1.10, net ratio ~0.41.

    **The spike's size is captured; where the velocity settles afterwards is
    not.** That is B6's ringing, and this pins it as the deficit rather than a
    cosmetic wobble. It also says what a fix has to do: preserve the amplitude
    B5 measured while correcting the settling point, which is why a constant
    bias cannot do it.

    Per capture, amplitude then net: 1.10/0.35, 0.99/0.37, 1.78/0.96.

    The amplitude is checked against B5's own `IMPACT_STEP_RATIO` bands rather
    than a fresh constant, which is what makes this a reconciliation: the same
    quantity measured here lands where B5 pinned it, including
    `deadlift_180x3`'s known 58-72% over-read, so the disagreement really is
    about WHICH quantity and not about how either is computed.

    The net is asserted as a fraction of the amplitude, not absolutely. A
    capture that over-reads everything inflates both — 180x3's net ratio is
    0.96 and it still loses 0.36 m/s per interval — so the ratio between them
    is the robust statement. Any fixed post-impact offset also oscillates with
    the ring (0.72, 0.49, 0.76, 0.54 at 50, 100, 150, 200 ms), which is the
    same reason.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from scipy.signal import savgol_filter
    from src import metrics, orient, pipeline, segment, truth

    result = pipeline.run(RAW / f"{csv}.csv", video=VIDEO / f"{video}.mov")
    log = result["log"]
    t = log["t"]
    world = orient.to_world(log["accel"], log["quat"], log["quat"])
    vel = np.concatenate([[0.0], np.cumsum(world[:-1, 2] * np.diff(t))])

    path = truth.bar_path(VIDEO / f"{video}.mov")
    impacts = segment.impact_anchors(log)
    fit = truth.sync(truth.landings(path),
                     np.array([float(t[k]) for k in impacts]))
    t_video = truth.to_imu_time(path, fit)
    v_video = np.gradient(savgol_filter(path["height"], 9, 3), t_video)

    amplitude, net = [], []
    for k in impacts:
        tk = float(t[k])
        a = int(np.searchsorted(t, tk - 0.30))
        b = int(np.searchsorted(t, tk + 0.30))
        m = (t_video > tk - 0.30) & (t_video < tk + 0.30)
        if not m.any():
            continue
        amplitude.append((vel[a:b].max() - vel[a:b].min())
                         / float(np.nanmax(v_video[m]) - np.nanmin(v_video[m])))
        pre = int(np.searchsorted(t, tk - 0.08))
        post = int(np.searchsorted(t, tk + 0.60))
        step = (float(np.interp(t[post], t_video, v_video))
                - float(np.interp(t[pre], t_video, v_video)))
        net.append((vel[post] - vel[pre]) / step)

    stem = next(k for k in IMPACT_STEP_RATIO if csv.startswith(k))
    lo, hi = IMPACT_STEP_RATIO[stem]
    amp, net_ = float(np.median(amplitude)), float(np.median(net))

    assert lo < amp < hi, (
        f"{stem}: impact amplitude ratio {amp:.2f} is outside the {lo}-{hi} "
        f"B5 measured for this capture, so this is no longer measuring the "
        f"same quantity B5 did and the reconciliation does not hold")
    assert net_ < amp * 0.65, (
        f"{stem}: the net impulse recovers {net_ / amp:.2f} of what the "
        f"amplitude suggests, against 0.32-0.54 at C11. If the settled "
        f"velocity now matches the video, B6 has landed — re-pin this")


# ------------------------------------------------------------------- B6 --
@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_the_impact_splice_fixes_the_closure_and_loses_anyway(video, csv, reps):
    """B6's splice, measured and rejected. The second negative result here.

    The idea was sound and C11 aimed it precisely: the vertical deficit is
    injected at the landing, the bar's velocity there is zero and externally
    validated, so stop integrating THROUGH the impact and splice across it.
    Implemented inline rather than shipped, exactly as the constant-bias family
    below is, so the measurement stays executable without the code living in
    `correct.py`.

    **It does what it was built to do.** Vertical momentum closure across a
    landing goes from -0.778 / -0.522 / -0.339 m/s to -0.049 / -0.004 / -0.019.
    The defect C6 found and C11 localised is gone.

    **And it loses on every variant tried:**

        splice     detrend    horizontal rms, cm
        none       xyz        5.05 /  9.19 / 15.44   <- shipping
        z only     xyz        5.05 /  9.19 / 15.44   <- bit-identical
        xyz        xyz       10.09 /  5.90 / 14.61
        xyz        z only    28.51 / 18.00 / 61.36

    Three things that rules out, and the third is the one worth carrying.

    *A vertical-only splice cannot help the spec.* `pipeline_h_rms` reads
    columns 0 and 1; a correction confined to column 2 leaves it bit-identical.
    Measured, not argued — and it means no vertical fix can ever satisfy a
    horizontal decision rule.

    *An all-axis splice over-corrects.* Step 7's detrend already removes the
    horizontal drift, and doing it twice is worse on the capture with the best
    baseline (5.05 -> 10.09).

    *And the splice cannot REPLACE the detrend either*, which was the last live
    hypothesis. Row 4 is the test: splice everything, then close vertical only.
    It gives 28.51 / 18.00 / 61.36 against the detrend's 5.05 / 9.19 / 15.44.
    The detrend constrains position across a whole rep; the splice constrains
    velocity at one instant per rep. **A sparse true constraint does not
    substitute for a dense false one** — which is B7's conclusion reached from
    the opposite direction, and now measured on the vertical too.

    It also breaks a bound it was never aimed at: per-rep vertical ROM goes to
    82.6 / 65.4 / 64.1 cm against a 61 cm ceiling, because removing an error `e`
    over a window `T` injects about `e*T/2` of position and step 7's LINEAR
    detrend cannot remove a quadratic. See `analysis/32`.

    Asserts the negative result. If a future change makes the splice win, this
    fails and should be deleted in favour of shipping it.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from scipy.integrate import cumulative_trapezoid
    from src import correct, metrics, pipeline, segment, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    log = result["log"]
    t = log["t"]
    impacts = segment.impact_anchors(log)
    rest = segment.rest_instants(log, impacts)

    # Only rest instants inside the rep span. `impact_anchors` also fires on the
    # re-rack of bench_90x4_1/_3 and squat_140x5, all after the last rep ends.
    lo, hi = result["bounds"][0][0], result["bounds"][-1][1] - 1
    rest = [k for k in rest if lo <= k <= hi]
    if not rest:
        pytest.skip(f"{csv}: no validated rest instant inside the rep span")

    def spliced(axes):
        v = result["velocity"].copy()
        keep = np.zeros(v.shape[1])
        keep[list(axes)] = 1.0
        for r in rest:
            k = max([i for i in impacts if i < r], default=None)
            if k is None:
                continue
            e = v[r] * keep
            w = np.zeros(len(v))
            w[k:r + 1] = (t[k:r + 1] - t[k]) / (t[r] - t[k])
            w[r + 1:] = 1.0
            v = v - w[:, None] * e
        return v

    def score(velocity, detrend_axes):
        pos = cumulative_trapezoid(velocity, np.cumsum(log["dt"]), axis=0,
                                   initial=0)
        reps = correct.detrend_set(pos, result["bounds"], t, axes=detrend_axes)
        m = metrics.vs_truth({**result, "reps": reps, "velocity": velocity},
                             VIDEO / f"{video}.mov")
        roms = [float(p[:, 2].max() - p[:, 2].min()) * 100 for p in reps]
        return m["pipeline_h_rms"], max(roms)

    shipped = result["vs_truth"]["pipeline_h_rms"] if "vs_truth" in result else None
    if shipped is None:
        shipped = score(result["velocity"], (0, 1, 2))[0]

    # A vertical-only splice cannot move a horizontal metric. Bit-identical.
    assert score(spliced((2,)), (0, 1, 2))[0] == pytest.approx(shipped, abs=1e-9)

    # Every variant that does move it, moves it the wrong way overall.
    all_axis, rom_all = score(spliced((0, 1, 2)), (0, 1, 2))
    replace, _ = score(spliced((0, 1, 2)), (2,))
    assert replace > shipped * 1.5, (
        f"{csv}: splice-instead-of-detrend gives {replace:.2f} cm against "
        f"{shipped:.2f}. If it now wins, B6 should ship and this test go")

    # And the position artefact breaks the physical ROM ceiling.
    assert rom_all > truth.VERTICAL_ROM_M["deadlift"][1] * 100, (
        f"{csv}: spliced ROM {rom_all:.1f} cm no longer exceeds the bound, so "
        f"the e*T/2 artefact is gone and the splice deserves re-measuring")


@pytest.mark.parametrize("video,csv,reps", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_constant_bias_corrections_are_worse_than_none(video, csv, reps):
    """B6's first candidate, measured and rejected. Asserts a negative result.

    A rep starts and ends at rest, so its mean world acceleration must be zero.
    Enforcing that looked like the right constraint — velocity closure is
    physically TRUE where step 7's position closure is measurably false (A3:
    the real bar misses closing horizontally by 1.9-4.3 cm). It makes things
    much worse, on every capture and every variant tried.

    The arithmetic says why, and it is worth keeping because it rules out the
    whole family rather than one attempt. A constant bias b leaves b*T^2/8 of
    position error after a linear detrend. The MEASURED error implies b of
    0.0016-0.0047 g. Every closure-derived estimate is 0.0076-0.0266 g, 1.9 to
    7.1x larger. So the signal does not contain a constant bias of the
    estimated size: the constraint is absorbing an error localised at the floor
    impact and spreading it across the whole rep, which injects a parabola
    bigger than the error it removes.

    This is also why TASKS.md's oracle cap holds — a constant-bias model cannot
    represent an impulse. Do not re-propose one without new evidence.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import correct, integrate, metrics, pipeline

    base = pipeline.run(RAW / f"{csv}.csv", video=VIDEO / f"{video}.mov")
    log, world = base["log"], base["world_accel"]

    reps_zero_mean = []
    for a, b in base["bounds"]:
        acc = world[a:b] - world[a:b].mean(axis=0)
        _, p = integrate.integrate(acc, log["dt"][a:b])
        reps_zero_mean.append(
            correct.detrend_rep(p, 0, len(p), log["t"][a:b]))

    shipped = base["vs_truth"]["pipeline_h_rms"]
    zeroed = metrics.vs_truth({**base, "reps": reps_zero_mean},
                              VIDEO / f"{video}.mov")["pipeline_h_rms"]

    if csv.startswith("deadlift_180x3"):
        # The one capture it helps, 15.4 -> 6.6 cm, and it is the capture that
        # over-reads its impact by 58-72% (P6). Helping there is consistent
        # with the diagnosis rather than against it: the constraint removes
        # part of an impact error that is unusually large on this capture.
        assert zeroed < shipped
        return
    assert zeroed > shipped * 1.5, (
        f"{csv}: zero-mean acceleration now HELPS ({shipped:.2f} -> "
        f"{zeroed:.2f} cm). The B6 diagnosis above needs re-running")


# ------------------------------------------------------------------- #14 --
@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_quality_flags_rejects_only_actual_clipping(path):
    """No real rep may be rejected. Nothing in data/raw/ clips, so nothing goes.

    This pins the removal of the strap-resonance flag (#14), which rejected
    **33 of 73** real reps. Three measurements retired it, and they are worth
    keeping because any replacement has to beat them:

    It fired where resonance cannot be — bench 26/30, deadlift 6/15, squat
    1/28. Hard landings happen on deadlift and nowhere else, so it was
    anti-correlated with its own phenomenon.

    Neither formulation works. As a FRACTION it flags quiet reps for having
    little signal; as ABSOLUTE energy it separates by lift alone (squat 3e3-4e4,
    bench 6e3-1.4e5, deadlift 5.8e5-7.4e6) and is just a deadlift detector,
    because the floor impact is real broadband signal.

    And there is no resonance to find at 100 Hz: the 400 ms after the 15 floor
    impacts peaks at 10 through 47.5 Hz with no repeatable frequency and
    peak/median of 2.7-12.5. Nyquist is 50 Hz and a watch-on-strap resonance is
    plausibly above it, so whatever exists aliases to an arbitrary bin.

    `clipped` survives because a rail is real and well defined, and it now
    delegates to `io.clipped_runs` rather than thresholding against an assumed
    16 g full scale that B5 disproved.
    """
    from src import pipeline

    result = pipeline.run(path)
    bad = [q for q in result["quality"] if not q["ok"]]
    assert not bad, (
        f"{path.stem}: {len(bad)} of {len(result['quality'])} reps rejected. "
        f"B5 established that nothing in data/raw/ clips, so a rejection here "
        f"means either a genuine rail or a detector that has regained the "
        f"habit of discarding real lifting")

    assert all("strap_resonance" not in q for q in result["quality"]), (
        "the strap-resonance flag is back. It rejected 33 of 73 real reps and "
        "fired hardest on the lift with no floor impact; see the docstring "
        "above and segment.quality_flags before reinstating it")

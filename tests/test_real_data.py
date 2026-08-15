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

RAW = Path(__file__).resolve().parents[1] / "data_v2" / "raw"

# Must stay identical to pipeline.REP_LABEL. The optional middle token is a
# lift variant (bench_spoto_90x5); without it the three 2026-07-30 benches
# matched nothing, dropped out of CAPTURES, and every gate below skipped them
# silently — which is how a 6-window segmentation of a 5-rep set survived.
REP_COUNT = re.compile(r"^(bench|squat|deadlift)(?:_[a-z]+)*_[\d.]+x(\d+)")

# Every log, including non-lifts. Use for format-level checks — clipping,
# sampling, quaternion norms — which are about the FILE, not about lifting.
#
# **`RAW` is `data_v2/raw` as of 2026-08-14**, because `data/raw` was deleted
# with the rest of v1 on the owner's instruction. Every gate in this file was
# written against the v1 corpus and would otherwise skip silently — 132 of 133
# tests did exactly that for one run, which is the failure mode this project
# has been bitten by repeatedly: a suite that reports success by not running.
# The four diagnostic logs (a stationary watch on a table, and the room
# captures) went with v1, so `ALL_LOGS` and `CAPTURES` are now nearly the same
# list; `CAPTURES` is kept distinct because the distinction is real and the
# next diagnostic capture will restore it.
ALL_LOGS = sorted(RAW.glob("*.csv")) if RAW.is_dir() else []

# Rep-labelled lifts only. Nearly every gate here means "a set of reps".
CAPTURES = [p for p in ALL_LOGS if REP_COUNT.match(p.name)]

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data_v2/raw/")

# Captures whose rep COUNT is wrong. P1 recorded counting as closed at 44/44,
# and it was, on the ten captures that existed on 2026-07-29. The 2026-07-30
# session added seven more and took it to 71/72 — `bench_spoto_90x5_1` counted
# the re-rack as a sixth rep, hidden by a REP_COUNT regex that did not match
# the 'spoto' variant token.
#
# EMPTY as of 2026-07-31 (C5): counting is 72/72. The cause was
# `segment._longest_cadence`'s tolerance of 1.6, which admitted the 4.50 s gap
# between the last rep and the re-rack (4.50/2.86 = 1.573) and grew a run of
# six that beat the true run of five on length. C5 set it to 1.45, the middle
# of a plateau that gave 17/17.
#
# STILL EMPTY as of 2026-08-06 (C31a), but that constant is gone. The four
# paused squats of 2026-08-06 closed C5's plateau to nothing — a paused set's
# cadence lengthens rep by rep, so `squat_pause_140x4_3` needs tol >= 1.574
# where `bench_spoto_90x5_1` needs tol <= 1.572, DISJOINT. `_longest_cadence`
# now compares each gap to its NEIGHBOUR rather than to the run's global
# spread, and breaks length ties on cadence evenness before lateness. Counting
# is 30/30 labelled captures across both datasets, and every window that was
# already correct is bit-identical.
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
# It was NOT EMPTY between 2026-08-14 (F1) and 2026-08-15 (G1), and those two
# entries were invisible until the v1 corpus was deleted. Every gate in this
# file globbed `data/raw`, so the 2026-08-08 captures had NEVER been segmented
# under test — the suite reported success by not running, which is this
# project's oldest failure shape. Pointing RAW at `data_v2/raw` took the file
# from 1 passing test to 311 across the suite, and surfaced two immediately:
#
#     deadlift_150x4_1_20260808   5 windows for a labelled 4
#     bench_117.5x1_20260808      2 windows for a labelled SINGLE
#
# **G1 fixed both and this is empty again (2026-08-15).** The first was
# `impact_anchors` reading a setup wrist swing as a floor landing — the video
# has the bar flat on the floor at that instant. The second was a real press
# and a setup arm movement forming a false cluster of TWO, on the corpus's
# first bench single, with no third rep to out-vote them. See
# `segment.impact_anchors`, `segment._upright` and `analysis/53`. Counting is
# 16/16 captures and 64/64 reps.
#
# Empty is the normal state and it is load-bearing: an entry here means the
# suite asserts a defect rather than a requirement, so nothing belongs in it
# that is not being actively worked.
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
    velocity, position = world(log)
    # `position` is what the pipeline passes, and it is what turns on the
    # verticality discriminator (G1). A gate that omits it tests a path nothing
    # ships — which is how `bench_117.5x1` read as a miscount here after the
    # fix that repaired it.
    bounds = segment.rep_bounds(log, velocity[:, 2], position=position)
    assert len(bounds) == truth_reps(path)


@needs_data
def test_reps_do_not_overlap_and_are_ordered(path=None):
    """Rep windows must be disjoint and in time order on every capture."""
    for p in CAPTURES:
        log = io.load_log(p)
        velocity, position = world(log)
        bounds = segment.rep_bounds(log, velocity[:, 2], position=position)
        for (_, stop), (start, _) in zip(bounds, bounds[1:]):
            assert stop <= start, f"{p.name}: overlapping rep windows"






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
    vel3, position = world(log)
    velocity = vel3[:, 2]
    filtered = segment.bandpass(velocity, log["fs"])

    for n, (a, b) in enumerate(
            segment.rep_bounds(log, velocity, position=position), 1):
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
#   windows at 27.6-30.0 cm. (C31a rewrote the rule behind that tolerance on
#   2026-08-06; this capture still gives the same 5 windows, bit-identically,
#   and remains the capture that sets the plateau's CEILING.)
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
# NOT EMPTY as of 2026-08-14 (F1). Same cause as WRONG_REP_COUNT above and the
# same reason nobody had seen it: these captures were never under test while
# the gates globbed the v1 corpus.
KNOWN_ROM_FAILURES: dict[str, str] = {
    "deadlift_170x4_3_20260808":
        "rep 4 spans 67.5 cm against 40-61, on a capture that counts 4/4 — so "
        "this one is extent WITHOUT a miscount, the squat_160x1 shape. **The "
        "only one of F1's three left after G1 (2026-08-15)**, and the two that "
        "went were both segmentation: bench_117.5x1's 42.1 cm was a window "
        "swallowing the un-rack and deadlift_150x4_1's 67.8 cm was a spurious "
        "floor anchor. This one is not: its window runs impact to impact like "
        "every other deadlift window and those impacts match the video. What "
        "is different is that the lifter rested 5.8 s before the last rep "
        "against 3.5-4.3 s for the others, making it the longest window in the "
        "corpus — and across all 28 deadlift windows duration correlates 0.575 "
        "with reconstructed ROM. **That is a correlation and not the cause**: "
        "the second-longest window (deadlift_185x3, 5.03 s) comes out at a "
        "perfectly ordinary 53.9 cm. So this is a reconstruction defect "
        "surfacing in a segmentation gate — no window change fixes it — and "
        "the mechanism is not established. Open.",
}


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_reconstructed_rom_is_physically_possible(path):
    """Every rep's vertical ROM must be a range this lifter can move a bar through.

    Bounds are measured per lift (`capture.VERTICAL_ROM_M`); the floors are
    inferred, so read a floor violation as "that window is not a whole rep".

    Where this is measured matters. Run on `result["position"]` instead of
    `result["reps"]` — that is, before step 7 — the same numbers are absurd:
    deadlift_155x6_1 climbs from 100 cm on rep 1 to 1939 cm on rep 6. Passing
    here is therefore a statement about the detrended output only, and says
    nothing about the acceleration reaching the integrator, which is P3.

    The bounds are anatomical and quoted to the nearest centimetre, so this
    gate allows `SLACK_M` on each end where `capture.rom_flags` allows none. The
    flag is a thing to look at; a build failure is a claim that something is
    wrong. `deadlift_180x3` rep 2 lands at 61.1 cm against the 61 cm bound —
    worth surfacing in `pipeline.summary`, not worth failing over.
    """
    from src import pipeline, capture

    result = pipeline.run(path)
    reason = next((r for k, r in KNOWN_ROM_FAILURES.items()
                   if path.stem.startswith(k)), None)
    lo, hi = capture.VERTICAL_ROM_M[capture.lift_of(path)]
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
VIDEO = Path(__file__).resolve().parents[1] / "data_v2" / "video"


















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
















# Re-pinned 2026-07-30 against the measured 445 mm deadlift bumper. The whole
# correction is worth under 1% here, which is the useful negative result: the
# plate diameter was never what made these numbers 5-15x out of spec.
CEILING = 1.25                      # 25% headroom, so noise does not flap it












@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_dispersion_is_finite_and_reported(path):
    """dispersion must run on every MULTI-REP capture and produce usable numbers.

    Single-rep sets are excluded rather than special-cased, and `pipeline.run`
    is right to omit the key: dispersion is rep-to-rep spread, so on one rep it
    has nothing to measure. The corpus holds three singles, one per lift, and
    they are the reason this is stated at all — `src/shortset.py` gives them a
    referee but it cannot give them a rep-to-rep spread.
    """
    from src import pipeline

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
@pytest.mark.parametrize("stem", ["bench_spoto_95x5_1", "squat_pause_140x4_3"])
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

    **Squat used to keep the older form and no longer does (G2, 2026-08-15).**
    It was parametrised on `squat_130x5` — a v1 capture, deleted — and asserted
    that `vs_truth` refused. Squat is scored now, so both parametrisations
    assert the SAME, stronger thing: there is a referee, and it disagrees with
    dispersion. On `squat_pause_140x4_3` dispersion reports under 2 cm of spread
    against 2.97 cm measured from the video.

    That both lifts now take the strong form is the point rather than a tidy-up.
    The weak form could only ever say "no referee exists here"; it could not
    catch the failure the docstring is about.
    """
    from src import metrics, pipeline

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    assert result["dispersion"]["horizontal_rms"] < 2.0

    video = VIDEO / f"{path.stem.rsplit('_', 1)[0]}.mov"
    if not video.exists():
        pytest.skip(f"{video.name} not present")
    m = metrics.vs_truth(result, video)
    assert m["pipeline_h_rms"] > result["dispersion"]["horizontal_rms"], (
        f"{stem}: dispersion {result['dispersion']['horizontal_rms']:.2f} cm no "
        f"longer flatters the {m['pipeline_h_rms']:.2f} cm measured against "
        f"video — check which one moved before relaxing this")


@needs_data
@pytest.mark.parametrize("stem", ["squat_pause_140x4_2", "squat_pause_140x4_3",
                                  "squat_pause_145x4_1"])
def test_vs_truth_scores_squat_and_the_sync_is_corroborated(stem):
    """Squat is refereed now, and the sync that makes it possible is checked. G2.

    **This replaces `test_vs_truth_refuses_squat`, which asserted the opposite
    and had been skipping since v1 was deleted.** Its parametrisation was
    `squat_130x5` and `squat_140x4_1`, both gone, so the gate protecting the
    refusal had not run in any form since 2026-08-14. The refusal's stated
    reason — median NCC ~0.40, the plate clipping the top of frame, "a wider
    shot, not code" — was entirely about the v1 plate template on `data/video/`
    footage, and BOTH the tracker and the footage were deleted with it. It was
    gating on a fact that could no longer be checked in either direction.

    What changed underneath it: `src/vtrack/` tracks these four clips at 100%
    coverage and 63-66 cm of travel with rep counts matching their labels, and
    `metrics.bench_sync` — which `_video_on_imu_clock` has always routed
    non-deadlift lifts to — turns out to work BETTER on a paused squat than on
    any bench. Correlation 0.73-0.76 against bench's 0.46-0.63, and **zero
    whole-rep rivals** where every bench capture has two to four. The bottom
    dwell breaks the periodicity that makes bench ambiguous.

    Asserts three independent things, because the count of them is the point:
    the capture scores at all, the correlation is corroborated by a landmark
    that cannot see it, and the result is physically sane.
    """
    from src import metrics, pipeline, capture

    path = next((p for p in CAPTURES if p.stem.startswith(stem)), None)
    if path is None:
        pytest.skip(f"{stem} not present")

    result = pipeline.run(path)
    video = pipeline.find_video(path)
    if video is None:
        pytest.skip(f"{stem} has no paired video")
    m = metrics.vs_truth(result, video)

    assert m["n_compared"] == truth_reps(path), (
        f"{stem}: {m['n_compared']} of {truth_reps(path)} reps fell inside the "
        f"video's coverage — a sync error looks exactly like this")

    # The corroboration, which is what licenses scoring squat at all.
    assert m["sync_landmark_reps"] == truth_reps(path)
    assert m["sync_landmark_disagree_reps"] < metrics.LANDMARK_TOL_REPS, (
        f"{stem}: correlation and per-rep bottoms disagree by "
        f"{m['sync_landmark_disagree_reps']:.3f} rep periods")

    # Physically sane: a squat's horizontal error is centimetres, not metres,
    # and its video ROM sits in the band measured for this lifter.
    assert 0.0 < m["pipeline_h_rms"] < 10.0
    lo, hi = capture.VERTICAL_ROM_M["squat"]
    assert lo * 100 <= m["video_rom_cm"] <= hi * 100, (
        f"{stem}: video ROM {m['video_rom_cm']:.1f} cm outside the squat band")


@needs_data
def test_the_sync_landmark_catches_a_whole_rep_error():
    """The gate that makes the squat sync trustworthy, tested by breaking it. G2.

    `bench_sync` identifies its lag only up to a whole rep period, and its own
    docstring is explicit that the ambiguity is harmless ONLY for the two
    quantities it was measured against — and that `vs_truth`'s `covered` flag
    and per-rep table are not among them. So the ambiguity had to be closed
    before squat could be scored per rep, not argued around.

    `metrics.pause_landmark` closes it: the bottom of each rep, named by the raw
    IMU (`segment.dwell_instants`, no attitude or integration) and by the video
    independently. Across all seven multi-rep bench and squat captures the two
    agree to 0.003-0.083 of a rep period.

    This asserts the other half — that the check would FIRE. A one-rep error is
    injected in both directions on every capture that has a cadence, and every
    one must be refused. Fourteen for fourteen when written.
    """
    from src import metrics, pipeline, capture

    real = metrics.bench_sync
    caught, missed = [], []
    try:
        for shift in (+1, -1):
            def shifted(p, log, vz, cadence, max_lag_s=None, _s=shift):
                fit = real(p, log, vz, cadence, max_lag_s)
                fit["offset"] = fit["offset"] + _s * cadence
                return fit
            metrics.bench_sync = shifted
            for path in CAPTURES:
                if capture.lift_of(path) == "deadlift":
                    continue
                result = pipeline.run(path)
                if len(result["bounds"]) < metrics.LANDMARK_MIN_REPS:
                    continue
                video = pipeline.find_video(path)
                if video is None:
                    continue
                try:
                    metrics.vs_truth(result, video)
                except ValueError as exc:
                    (caught if "sync refused" in str(exc) else missed).append(
                        (path.stem, shift, str(exc)[:60]))
                else:
                    missed.append((path.stem, shift, "scored anyway"))
    finally:
        metrics.bench_sync = real

    assert not missed, f"a whole-rep sync error went undetected: {missed}"
    assert len(caught) >= 6, (
        f"only {len(caught)} captures exercised the guard; it was 14 when "
        f"written, so either the corpus shrank or captures stopped syncing")








# ------------------------------------------------------------------- B7 --


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










# ------------------------------------------------------------------- B2 --


@needs_data
@pytest.mark.parametrize("path", CAPTURES, ids=lambda p: p.stem)
def test_step_six_runs_and_is_ON_by_default(path):
    """apply_offset must be applied by default, and must be defeatable.

    **This test was inverted on 2026-08-06 (C31) and the inversion is the
    point.** It used to assert step 6 was OFF by default, and that was right
    while `d` was unmeasured — B2 had shown it cannot be fitted from the video,
    so a guessed `d` cost up to 0.8 cm and bought nothing. The owner then
    tape-measured it (`correct.WRIST_OFFSET_M`) and ruled that it should always
    be applied, on the ground that this project reconstructs the BAR path and
    the sensor is on the WRIST: omitting a measured geometric term does not make
    the answer safer, it answers a different question.

    So what is gated here now is (a) the default really applies the measured
    vector for this capture's lift, (b) `None` still gets the old watch-path
    behaviour back, because every number recorded in the docs before 2026-08-06
    was measured that way and they are not comparable otherwise.
    """
    from src import correct, pipeline, capture

    plain = pipeline.run(path)
    assert not any("apply_offset" in b for b in plain["blocked"])
    assert plain["wrist_offset"] is not None, "step 6 must be on by default"
    np.testing.assert_allclose(plain["wrist_offset"],
                               correct.WRIST_OFFSET_M[capture.lift_of(path)])

    off = pipeline.run(path, wrist_offset=None)
    assert off["wrist_offset"] is None
    assert any("step 6 OFF" in n for n in off["notes"])
    assert not np.allclose(off["bar_position"], plain["bar_position"])


















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






# ------------------------------------------------------------------ C11 --






# ------------------------------------------------------------------- B6 --


# ------------------------------------------------------------------- B3 --




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


# ------------------------------------------- the pause and Core Motion's fusion --
# C31, 2026-08-06. The owner's hypothesis: a pause holds the watch quasi-static
# long enough for the accelerometer to serve as a gravity reference, so Core
# Motion corrects accumulated tilt MID-REP — a step at the same phase every rep,
# which is P3's signature and is what step 7's boundary-anchored linear detrend
# cannot remove.
#
# It is HALF RIGHT and the half that fails is the interesting one, so both
# halves are pinned here. See analysis/49, `python run.py --pauseattitude`.


# Both datasets: the paused squats live in `data_v2/raw` and `ALL_LOGS` above is
# `data/raw` only, so the pause tests would silently have no paused squat to
# look at and would pass on an empty group. Named separately rather than
# widening ALL_LOGS, which many older tests are calibrated against.
_RAW_V2 = Path(__file__).resolve().parents[1] / "data_v2" / "raw"
BOTH_DATASETS = ALL_LOGS + (sorted(_RAW_V2.glob("*.csv")) if _RAW_V2.is_dir() else [])


def _fusion_tilt_yaw(log):
    """Core Motion's attitude increment minus the gyro's, split tilt vs yaw.

    Gravity can correct TILT and is geometrically incapable of correcting yaw
    about gravity, while numerical error has no such preference — which is what
    makes the RATIO the decisive statistic rather than the magnitude. Midpoint
    gyro rule, because a left-endpoint one makes fast motion look like fusion.
    """
    from scipy.spatial.transform import Rotation

    q, dt, w = log["quat"], log["dt"], log["gyro"]
    R = Rotation.from_quat(q, scalar_first=True)
    wm = 0.5 * (w[:-1] + w[1:])
    inc = Rotation.from_rotvec(wm * dt[:-1, None]).inv() * (R[:-1].inv() * R[1:])
    world = R[:-1].apply(inc.as_rotvec())
    return (np.degrees(np.linalg.norm(world[:, :2], axis=1)) / dt[:-1],
            np.degrees(np.abs(world[:, 2])) / dt[:-1])


def test_the_gravity_correction_mechanism_is_real():
    """Tilt beats yaw in the fusion correction, and more so when still.

    This is the owner's mechanism, confirmed: Core Motion really does lean on
    the accelerometer for gravity, and it leans harder when the watch is
    quasi-static. Measured 22 of 30 captures with the ratio higher when still.
    """
    from src import io, pipeline

    rose = total = 0
    for p in BOTH_DATASETS:
        if pipeline.expected_reps(p) is None:
            continue
        log = io.load_log(p)
        tilt, yaw = _fusion_tilt_yaw(log)
        a = np.linalg.norm(log["accel"], axis=1)[:-1]
        wm = np.degrees(np.linalg.norm(log["gyro"], axis=1))[:-1]
        q = (wm < 20.0) & (a < 1.5)
        if not q.any() or not (~q).any():
            continue
        total += 1
        r_qs = np.median(tilt[q]) / max(np.median(yaw[q]), 1e-9)
        r_dy = np.median(tilt[~q]) / max(np.median(yaw[~q]), 1e-9)
        # Tilt always dominates: a gravity-referencing filter, not a free gyro.
        assert r_qs > 1.0, f"{p.name}: tilt/yaw {r_qs:.2f} when still"
        rose += r_qs > r_dy
    # 16, not the 25 this asserted until 2026-08-14. The corpus was 30 labelled
    # captures across two datasets; deleting v1 left the 16 in `data_v2/raw`.
    # This is a "did we actually check enough captures" floor, so it tracks the
    # corpus rather than encoding a finding.
    assert total >= 16
    assert rose >= 0.6 * total, (
        f"tilt/yaw rose when still on only {rose} of {total}; the "
        f"accelerometer-as-gravity-reference mechanism is not visible")


# REMOVED 2026-08-14 — test_the_pause_concentrates_the_correction_on_SQUAT_but
# _NOT_on_BENCH, and it is removed rather than re-tuned on purpose.
#
# It contrasted PAUSED squats against CONTINUOUS ones, and every continuous
# squat in the project lived in `data/raw/`, which the owner deleted with the
# rest of v1. What survives is three paused squats and one continuous SINGLE,
# so `sq_c` was being computed from one capture of one rep — the comparison the
# test is named after no longer exists in the corpus.
#
# It failed at 3.84 against 2.95 x 1.4. Lowering the factor would have made it
# pass, and that is exactly what must not happen: the effect was measured across
# a set of continuous squats and there is no longer a set to measure it across.
# The finding it gated is in TASKS.md and CLAUDE.md as history.
#
# If continuous squats are captured again, restore it from git history rather
# than rewriting it from the description above.

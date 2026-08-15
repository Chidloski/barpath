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

from src import calibrate, correct, integrate, io, orient, segment, capture  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data_v2" / "raw"
REP_COUNT = re.compile(r"^(bench|squat|deadlift)(?:_[a-z]+)*_[\d.]+x(\d+)")
CAPTURES = ([p for p in sorted(RAW.glob("*.csv")) if REP_COUNT.match(p.name)]
            if RAW.is_dir() else [])

# `ALL_CAPTURES` used to be `CAPTURES` plus a second dataset, because the
# cadence plateau's two edges came from different corpora: `bench_spoto_90x5_1`
# set the ceiling from `data/raw/` and `squat_pause_140x4_3` the floor from
# `data_v2/raw/`. **v1 was deleted on 2026-08-14 (F1) and `data/raw/` with it**,
# and the two constants were left pointing at the same directory — so every
# capture was counted TWICE and `n` read 32 for a 16-capture corpus. Found and
# collapsed by G1. The consequence for the plateau itself is not cosmetic and
# is recorded in `test_cadence_tolerance_is_a_plateau_not_a_point`.
ALL_CAPTURES = CAPTURES

needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data_v2/raw/")

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
    """The windows the PIPELINE gets, which means passing `position` (G1).

    `pipeline.run` supplies it, so a gate that omits it is testing a path
    nothing ships. It is what turns on `segment._upright`, and without it
    `bench_117.5x1` counts two — which is exactly how these gates read before
    G1 wired the argument through.
    """
    log, vel, pos = prepared(path)
    return log, segment.rep_bounds(log, vel[:, 2], position=pos)


def roms_cm(path: Path, bounds) -> list[float]:
    log, _, pos = prepared(path)
    return [float(r[:, 2].max() - r[:, 2].min()) * 100
            for r in correct.detrend_set(pos, bounds, log["t"])]






# ------------------------------------------------------- the margins ------
@needs_data
def _count_at(tol: float, captures) -> int:
    """How many captures segment to their labelled rep count at this `tol`."""
    original = segment._longest_cadence
    try:
        segment._longest_cadence = functools.partial(original, tol=tol)
        return sum(
            len(segment.rep_bounds(log, vel[:, 2], position=pos)) == int(
                REP_COUNT.match(p.name).group(2))
            for p in captures
            for log, vel, pos in [prepared(p)])
    finally:
        segment._longest_cadence = original


@needs_data
def test_cadence_tolerance_is_a_plateau_not_a_point():
    """`_longest_cadence`'s tolerance must pass over a RANGE, not at a value.

    This is the anti-fitted-constant gate. The tolerance decides whether a gap
    belongs to the set's rhythm, and it was bounded by real data on both sides:

    * Below 1.4598, `squat_pause_140x4_3` splits. Its four paused reps are
      genuinely 5.43, 5.85 and 8.53 s apart — a fatiguing set lengthens its
      cadence rep by rep, and the worst ADJACENT step is 8.53/5.85 = 1.460.
    * Above 1.5306, `bench_spoto_90x5_1` admitted the post-set gap that arrives
      as a step of 4.50/2.94 = 1.531 and counted six.

    **THE CEILING IS GONE, AND SO IS THE TWO-SIDEDNESS THIS GATE EXISTS FOR
    (measured by G1, 2026-08-15).** `bench_spoto_90x5_1` lived in `data/raw/`,
    which F1 deleted with v1 on 2026-08-14. Nothing in the live 16-capture
    corpus pushes back from above **at any value**: swept to tol=1e6, which
    disables the cadence rule outright, all 16 still count correctly. The
    plateau is now [1.46, unbounded).

    Read what that costs. `tol` is still admissible at 1.50 and still 2.7%
    clear of the one real edge, so nothing needs re-tuning — but the constant
    is no longer FALSIFIABLE FROM ABOVE, and the discriminator it implements is
    unexercised: on this corpus `_similar_cluster` and `_upright` already
    deliver the right candidates and cadence removes nothing except, below
    1.46, one real paused-squat run. The captures that made cadence necessary
    (`bench_spoto_90x5_1`'s post-set run of five, `bench_92.5x2`'s unrack) were
    all v1. **A capture with a post-set movement inside the rep cluster is the
    single most valuable thing that could be filmed for this module.**

    C5's original edges were 1.35 and 1.60 on `data/raw/` alone, under a rule
    that compared a run's global SPREAD. C31a replaced that rule because the
    paused squats closed its plateau to nothing — see
    `test_the_old_global_spread_rule_has_no_admissible_tolerance`, which is the
    gate that stops anyone re-tuning their way back into it.

    So this asserts the floor as a plateau and the missing ceiling as a FACT,
    not as a pass. If the ceiling assertion starts failing, a capture has
    restored the upper bound — good news, and `segment._longest_cadence`'s
    docstring needs its edges re-measured.
    """
    n = len(ALL_CAPTURES)
    counts = {tol: _count_at(tol, ALL_CAPTURES)
              for tol in (1.44, 1.455, 1.46, 1.47, 1.50, 1.52, 1.56, 1e6)}

    for tol in (1.46, 1.47, 1.50, 1.52):
        assert counts[tol] == n, (
            f"tol={tol} gives {counts[tol]}/{n} — the plateau has shrunk, so "
            f"1.50 is no longer comfortably inside it")
    for tol in (1.44, 1.455):
        assert counts[tol] < n, (
            f"tol={tol} now also gives {counts[tol]}/{n}. The floor has moved "
            f"and segment._longest_cadence's docstring quotes it")
    assert counts[1e6] == n, (
        "something in the live corpus now constrains the cadence tolerance "
        "from above, where G1 measured nothing that did. That restores the "
        "two-sided evidence this gate was written for — re-measure the ceiling "
        "and correct both docstrings")


@needs_data
def test_the_old_global_spread_rule_has_no_admissible_tolerance():
    """The rule C31a replaced CAN now be rescued, and that is not good news. C31a, G1.

    This is the evidence for replacing the rule rather than re-tuning it, and
    it is a gate rather than a note because the tempting fix — nudge `tol` —
    looks reasonable right up until you measure it.

    Until 2026-08-06 a run was admitted when the ratio of its largest to its
    smallest gap stayed under `tol`. Under that rule the two paused squats and
    `bench_spoto_90x5_1` constrain the constant from opposite sides, and the
    constraints are DISJOINT: the bench needs tol <= 1.572 and
    `squat_pause_140x4_3` needs tol >= 1.574. A fatiguing set's cadence drifts
    monotonically, so measured by global spread it looks exactly like a set
    with a post-set movement tacked on.

    **It works again, measured 2026-08-15 (G1): swept as shipped, the old rule
    reaches 16/16 at tol=2.49.** The docstring below used to say "if a future
    capture makes some tolerance work again, this fails — and that is worth
    knowing, not worth suppressing", so it is recorded here rather than
    suppressed, and the assertion is inverted to pin the new state.

    **Read it as a loss, not as a vindication.** Nothing about the old rule
    improved. Two things happened to the CORPUS:

      * `bench_spoto_90x5_1` — one of the two disjoint constraints, and the
        capture whose post-set gap the global spread could not refuse — was
        deleted with v1 on 2026-08-14 (F1). The other constraint,
        `squat_pause_140x4_3`, survives; a single constraint cannot be
        disjoint with anything.
      * `segment._upright` now removes the false candidate on `bench_117.5x1`
        before any cadence rule sees it, so cadence has less left to do.

    So this is the same finding as the missing ceiling in
    `test_cadence_tolerance_is_a_plateau_not_a_point`, from a second direction:
    **deleting v1 removed this corpus's ability to tell two segmentation rules
    apart.** Do NOT read a passing sweep as licence to restore the global
    spread. C31a's evidence was measured and is not refuted by the absence of
    the capture that produced it — it is merely no longer reproducible here.

    Swept as the pipeline ships, `position` included. Without it the old rule
    reaches 15/16 instead, which measures a code path nothing runs.
    """
    def spread_cadence(chosen, t, tol):
        """`_longest_cadence` exactly as it stood before C31a."""
        if len(chosen) < 3:
            return chosen
        times = [t[l[0]] for l in chosen]
        found, i = [], 0
        while i < len(chosen):
            j = i + 1
            while j < len(chosen):
                gaps = np.diff(times[i:j + 1])
                if gaps.min() <= 0 or gaps.max() / gaps.min() > tol:
                    break
                j += 1
            found.append((j - i, float(np.median(times[i:j])), i, j))
            i += 1
        best = max(found, key=lambda r: (r[0], r[1]))
        return chosen[best[2]:best[3]]

    original = segment._longest_cadence
    n, best = len(ALL_CAPTURES), (0, None)
    try:
        for tol in np.arange(1.05, 2.50, 0.01):
            segment._longest_cadence = functools.partial(spread_cadence,
                                                         tol=float(tol))
            got = sum(
                len(segment.rep_bounds(log, vel[:, 2], position=pos)) == int(
                    REP_COUNT.match(p.name).group(2))
                for p in ALL_CAPTURES
                for log, vel, pos in [prepared(p)])
            best = max(best, (got, float(tol)))
    finally:
        segment._longest_cadence = original

    assert best[0] == n, (
        f"the pre-C31a global-spread rule reaches only {best[0]}/{n} at "
        f"tol={best[1]:.2f}, where G1 measured {n}/{n} on 2026-08-15. Something "
        f"has restored this corpus's ability to tell the two cadence rules "
        f"apart — most likely a new capture with a post-set movement inside the "
        f"rep cluster, which is the capture both this gate and "
        f"test_cadence_tolerance_is_a_plateau_not_a_point are missing. That is "
        f"GOOD NEWS: re-measure the disjointness and restore C31a's emptiness "
        f"result, in this docstring and in segment._longest_cadence's")


@needs_data
def test_only_a_single_has_a_degenerate_cluster():
    """The singleton tie-break can only ever fire on squat_160x1.

    `_similar_cluster` ranks clusters by size and falls back to displacement
    only when the best cluster has one member — the case where the size key
    carries no information at all. That fallback is a judgement about lifting
    (a rep moves the bar further than the movements bracketing it) which is
    measurably FALSE on bench, where `bench_92.5x2`'s unrack carries 0.433 m
    against 0.295 for a real rep.

    So the containment matters as much as the rule, and this test pins it: a
    capture landing in the degenerate branch announces itself instead of being
    silently judged by a rule known not to hold on bench.

    **It has now announced two, and the corpus it was written against is gone
    (G1, 2026-08-15).** `squat_160x1` was a v1 capture and F1 deleted it. The
    live corpus's degenerate captures are `squat_170x1` and `deadlift_200x1` —
    both genuine SINGLES, which is the case the fallback was written for, and
    both checked by hand against the cached video track. **Checking them is how
    G1 found that the fallback was picking the DROP on `deadlift_200x1`**, so
    the rule they reach is no longer displacement: singletons now rank by
    verticality, which puts the squat at 35.0 s and the deadlift at 16.6 s.
    See `test_the_deadlift_single_lands_on_the_pull_not_the_drop`.

    **The bench single the docstring feared does not arrive here.**
    `bench_117.5x1` is the first bench single in the corpus and its winning
    cluster has size 2 — the real press paired with a setup arm movement they
    correlate 0.80 with — so the size key never degenerates and this branch
    never runs. It is split by `segment._upright` instead. That matters,
    because the fallback WOULD have got it wrong: the largest displacement in
    that capture is the 5.4 s unrack at 0.455 m against the real press's 0.304,
    which is precisely the falsification `_similar_cluster` predicted.
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

    known = {"squat_170x1", "deadlift_200x1"}
    assert {s.split("_2026")[0] for s in degenerate} == known, (
        f"captures reaching the displacement fallback: {degenerate}, expected "
        f"{sorted(known)}. That rule does not hold on bench (bench_92.5x2's "
        f"unrack carried 0.433 m against 0.295 for a rep), so a new capture "
        f"landing here needs checking by hand — against the video, not against "
        f"the rep count — rather than trusting the fallback")

    for stem in degenerate:
        assert "x1_" in stem, (
            f"{stem} reaches the singleton fallback but is not a single. The "
            f"fallback assumes there is nothing to cluster WITH; on a multi-rep "
            f"set a degenerate cluster means the reps failed to match each "
            f"other, which is a different defect and needs a different fix")


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

    **One capture is RED here and it is expected to be: `deadlift_170x4_3`
    rep 4, at 67.5 cm against 40-61.** It counts 4/4 and its windows run impact
    to impact like every other deadlift, so this is wrong EXTENT without a
    miscount — a reconstruction defect surfacing in a segmentation gate. It is
    registered with its evidence in `test_real_data.KNOWN_ROM_FAILURES` and is
    left RED rather than xfailed here, on F1's principle that a finding buried
    under an expected-failure mark is how the previous ones stayed invisible.
    """
    log, bounds = windows(path)
    expected = int(REP_COUNT.match(path.name).group(2))
    assert len(bounds) == expected

    lo, hi = capture.VERTICAL_ROM_M[capture.lift_of(path)]
    slack = 0.02                    # bounds are anatomical, quoted to the cm
    for n, rom in enumerate(roms_cm(path, bounds), 1):
        assert (lo - slack) * 100 <= rom <= (hi + slack) * 100, (
            f"{path.stem} rep {n}: {rom:.1f} cm outside "
            f"{lo*100:.0f}-{hi*100:.0f} cm")


# ------------------------------------------------------- the G1 defects ---
@needs_data
def test_a_setup_wrist_swing_is_not_a_floor_impact():
    """deadlift_150x4_1 is four reps, not five. G1, 2026-08-15.

    The defect: `impact_anchors` read acceleration MAGNITUDE alone, and a wrist
    rotation arrested hard enough puts the watch's ~9.5 cm lever arm above the
    6 g threshold. The extra anchor sits at 7.03 s, where the cached video track
    has the bar flat on the floor at 1.4-1.5 cm and holds it there until 11 s.

    Asserted against the VIDEO rather than the count, because the count is what
    was already wrong: the four surviving anchors must line up with the four
    landings the tracker sees, and they do to 0.11 s.

    Not fixable by threshold, and that is asserted too — the counterfeit peaks
    at 7.01 g and the weakest real landing in the corpus at 6.69 g.
    """
    path = find("deadlift_150x4_1")
    log = io.load_log(path)
    anchors = segment.impact_anchors(log)
    assert len(anchors) == 4, (
        f"{[round(float(log['t'][k]), 2) for k in anchors]} — the 7.03 s "
        f"anchor is a setup wrist swing, not a landing")
    assert all(log["t"][k] > 11.0 for k in anchors), (
        "an anchor lands before the bar first leaves the floor at 11 s")

    quiet = [segment._quiet_before(log, k) for k in anchors]
    assert max(quiet) < 1.3 <= 2.83, f"real landings measured {quiet}"

    unfiltered = segment.impact_anchors(log, max_wrist_rate=None)
    assert len(unfiltered) == 5, "the defect no longer reproduces"
    mag = np.linalg.norm(log["accel"], axis=1) / 9.80665
    spurious = next(k for k in unfiltered if abs(float(log["t"][k]) - 7.03) < 0.1)
    w = int(0.3 * log["fs"])
    assert mag[spurious - w:spurious + w].max() > 6.69, (
        "the counterfeit now peaks below the weakest real landing in the "
        "corpus, so a threshold WOULD separate them and this rule is no "
        "longer the only option")


@needs_data
def test_the_bench_single_is_one_rep_and_it_is_the_right_one():
    """bench_117.5x1 is one rep, and the count alone cannot say so. G1.

    The first bench SINGLE in the corpus, and the capture `_similar_cluster`'s
    docstring predicted would falsify its singleton rule. Its winning cluster
    is the real press at 21.9 s together with a setup arm movement at 10.6 s,
    correlating 0.80 in fixed-duration shape and carrying 0.290 m against
    0.304 — indistinguishable to shape, to size and to cadence.

    **Both halves are asserted because raising `similarity` passes the first
    and fails the second.** At 0.83 the false pair breaks and the singleton
    fallback then picks the 5.4 s unrack, which carries 0.455 m: one window,
    right count, wrong rep. Only the video says which. So this pins the window
    against the cached track's rep, and pins the mechanism — `_upright` — that
    put it there.
    """
    path = find("bench_117.5x1")
    log, bounds = windows(path)
    assert len(bounds) == 1, [
        (round(float(log["t"][a]), 1), round(float(log["t"][b - 1]), 1))
        for a, b in bounds]

    (a, b), = bounds
    start, stop = float(log["t"][a]), float(log["t"][b - 1])
    # The video's single rep runs 18.67-24.23 s. The window must sit inside the
    # press, not on the setup 11 s earlier; its END is early by the half-rep
    # phase error bench has always had (P3), so only the start is pinned tight.
    assert 18.0 < start < 20.0, f"window starts at {start:.2f} s, video says 18.67"
    assert stop > 21.5, f"window ends at {stop:.2f} s, before the press completes"

    rom = roms_cm(path, bounds)[0]
    lo, hi = capture.VERTICAL_ROM_M["bench"]
    assert lo * 100 <= rom <= hi * 100, (
        f"window spans {rom:.1f} cm; the setup window this replaced spanned "
        f"42.1 cm, outside the {lo*100:.0f}-{hi*100:.0f} cm bench bound")

    # Without `position` the discriminator cannot run, and the defect returns.
    _, vel, _ = prepared(path)
    assert len(segment.rep_bounds(log, vel[:, 2])) == 2, (
        "the defect no longer reproduces without `position`, so `_upright` is "
        "not what is fixing this capture")


@needs_data
def test_the_deadlift_single_lands_on_the_pull_not_the_drop():
    """deadlift_200x1 counted 1/1 and had the wrong window entirely. G1.

    Found while checking G1's own work, which is why it is worth stating: the
    count was right, the ROM looked plausible at 43.8 cm inside a 40-61 cm band,
    and the window was the DROP. The video has the pull at 15.7-17.5 s, the
    lockout held to 19.3 and the bar back on the floor by 19.8; the shipped
    window was 18.97-19.92 s. `squat_160x1`'s shape for the third time.

    **Two independent defects had to be fixed for this capture, and each one
    alone leaves it wrong.**

      * `_similar_cluster` ranked its degenerate cluster by DISPLACEMENT, and
        the largest of the ten lobes is the reconstruction's invented velocity
        across the drop (0.529 m) rather than the pull (0.280 m). Ranking by
        verticality picks the pull: 2.59 against 2.13.
      * `_full_cycles` was then handed a hardcoded `sets_down=False`, so a lift
        that rests on the FLOOR was given the bench convention and its
        eccentric taken from the wrong side. That window ran 13.17-16.97 s at
        28.1 cm — the approach plus half a pull, cut off before lockout.

    Asserted against the video and against the ROM band, not against the count,
    because the count was never the thing that was wrong.
    """
    path = find("deadlift_200x1")
    log, bounds = windows(path)
    assert len(bounds) == 1

    (a, b), = bounds
    start, stop = float(log["t"][a]), float(log["t"][b - 1])
    assert start < 16.61 < stop, (
        f"window {start:.2f}-{stop:.2f} s does not contain the concentric peak "
        f"at 16.61 s, which the video puts inside the pull")
    assert stop > 19.0, (
        f"window ends at {stop:.2f} s, before the bar is back on the floor at "
        f"19.8 — a deadlift rep is floor to floor")

    rom = roms_cm(path, bounds)[0]
    lo, hi = capture.VERTICAL_ROM_M["deadlift"]
    assert lo * 100 <= rom <= hi * 100, (
        f"window spans {rom:.1f} cm; the two defective windows this replaced "
        f"spanned 43.8 cm (the drop) and 28.1 cm (half a pull)")

    # Both fixes are load-bearing. Without `position` the singleton ranking
    # falls back to displacement and the drop wins again.
    _, vel, _ = prepared(path)
    (a2, b2), = segment.rep_bounds(log, vel[:, 2])
    assert not (log["t"][a2] < 16.61 < log["t"][b2 - 1]), (
        "the displacement fallback now finds the pull too, so this capture no "
        "longer demonstrates why the singleton rule was replaced")

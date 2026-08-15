"""Gates on the short-set pipeline variant. G3.

`src/shortset.py` exists because the only three captures in `data_v2/` that
have never been refereed are the three SINGLES, and both existing sync routes
need repeated events to identify an alignment. The tests here are in the order
the module's claims have to be believed in:

1. it scores the three real singles at all (the point of the exercise);
2. it changes NOTHING about the thirteen captures that already scored, which is
   what makes it safe to install;
3. its accuracy is measured against known answers, on singles and doubles cut
   from the multi-rep captures;
4. its guards actually FIRE — checked by injecting the error they exist to
   catch, rather than by observing that they never complain;
5. its central constant sits on a plateau rather than at a point.

(5) is the house rule and it has teeth here: `test_real_data` records a 1 cm
synthetic gate that passed only because seed=0 landed inside a 0.29-1.86 cm
spread. A constant that works at one value and fails either side is fitted.

`data_v2/raw/` and the cached tracks are gitignored, so everything skips
cleanly without captures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import capture, metrics, pipeline, shortset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_v2" / "raw"

SINGLES = ["bench_117.5x1", "deadlift_200x1", "squat_170x1"]


def _captures():
    return sorted(RAW.glob("*.csv")) if RAW.is_dir() else []


def _find(prefix):
    hits = [p for p in _captures() if p.name.startswith(prefix)]
    return hits[0] if hits else None


def _multi():
    """The thirteen captures with three or more reps."""
    return [p for p in _captures()
            if not any(p.name.startswith(s) for s in SINGLES)]


def _same(a, b):
    """Equality that treats NaN as equal to itself.

    Needed because most of what a sync reports is deliberately NaN — a field
    that cannot be measured reads NaN rather than a number from somewhere else
    — and `nan != nan` would report every capture as changed.
    """
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a, b = np.asarray(a, dtype=object), np.asarray(b, dtype=object)
        if a.shape != b.shape:
            return False
        return all(_same(x, y) for x, y in zip(a.ravel(), b.ravel()))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return (np.isnan(a) and np.isnan(b)) or a == b
    return a == b


# The fields G3 added to `vs_truth`. Excluded from the bit-identity check
# because they are new keys rather than changed values — an addition every
# caller can ignore, where a changed number is not.
NEW_FIELDS = {"sync_offset", "sync_slope", "sync_method",
              "sync_containment_phase", "sync_corr"}


# ------------------------------------------------------- 1. it scores them --

@pytest.mark.parametrize("prefix", SINGLES)
def test_the_three_singles_are_refereed(prefix):
    """The whole point. Each of these raised before G3, one per lift.

    Two distinct refusals were being lifted, which is why all three are named
    here rather than one standing for the set: bench and squat died on
    `bench_sync`'s cadence precondition, the deadlift never reached it because
    `capture.sync` fits a slope and wants two landings.
    """
    csv = _find(prefix)
    if csv is None:
        pytest.skip(f"{prefix} not present")
    result = shortset.run(csv)
    assert result["short_set"], f"{prefix} should be a short set"
    assert len(result["bounds"]) == 1
    vt = result.get("vs_truth")
    assert vt is not None, f"{prefix} still refused: {result['blocked']}"
    assert np.isfinite(vt["pipeline_h_rms"])
    assert vt["sync_method"].startswith("short set")


@pytest.mark.parametrize("prefix", SINGLES)
def test_the_old_pipeline_still_refuses_them(prefix):
    """The refusal is real and is not being imagined.

    If this ever passes, the singles have acquired a sync somewhere else and
    the variant may be redundant — which is a good outcome, but it should be
    noticed rather than silently duplicated.
    """
    csv = _find(prefix)
    if csv is None:
        pytest.skip(f"{prefix} not present")
    result = pipeline.run(csv, video=pipeline.find_video(csv))
    assert result.get("vs_truth") is None
    assert any("vs_truth" in b for b in result["blocked"])


# ------------------------------------------- 2. it disturbs nothing else --

@pytest.mark.parametrize("csv", _multi(), ids=lambda p: p.name[:24])
def test_multi_rep_captures_are_bit_identical(csv):
    """Installing the hook must not move a single number that already existed.

    This is what licenses `shortset.run` being pointed at a whole directory,
    and it is checked per capture rather than in aggregate because an aggregate
    that passes while one capture moves is this project's recurring failure.
    """
    video = pipeline.find_video(csv)
    if video is None:
        pytest.skip("no video")
    base = pipeline.run(csv, video=video)
    var = shortset.run(csv, video=video)

    assert not var["short_set"]
    a, b = base.get("vs_truth"), var.get("vs_truth")
    assert (a is None) == (b is None), "the hook changed whether this scores"
    if a is None:
        return
    changed = [k for k in a if k not in NEW_FIELDS and not _same(a[k], b.get(k))]
    assert not changed, f"{csv.name}: {changed}"


@pytest.mark.parametrize("csv", _multi(), ids=lambda p: p.name[:24])
def test_the_hook_declines_long_sets(csv):
    """`shortset.sync` returns None for anything it is not for.

    The decision about WHICH captures are short lives in one function, so that
    is where it is tested. `_video_on_imu_clock` treats None as "not mine" and
    falls through to its own two routes.
    """
    result = pipeline.run(csv)
    if len(result["bounds"]) <= shortset.SHORT_SET_MAX_REPS:
        pytest.skip("not a long set")
    assert shortset.sync(result, {"t": np.zeros(1), "height": np.zeros(1)}) is None


# ------------------------------------------------------- 3. is it right? --

def _truncate(csv, full, keep, dest):
    """`shortset.truncate_capture`, which is where the instrument lives."""
    return shortset.truncate_capture(csv, full["bounds"], full["log"]["t"],
                                     keep, dest)


def _reference_offset(full):
    """The full capture's offset, normalised to `video t + offset = IMU t`.

    `capture.sync` fits video = slope * imu + offset and `bench_sync` returns
    imu = video + offset — OPPOSITE SIGNS. Normalising through a reference time
    rather than by flipping a sign also picks the slope up at the moment that
    matters instead of at t=0.
    """
    try:
        _, _, _, fit = metrics._video_on_imu_clock(
            full, pipeline.find_video(full["path"]))
    except (ValueError, FileNotFoundError):
        return None
    t_ref = float(full["log"]["t"][full["bounds"][0][0]])
    if fit.get("method", "").startswith("floor"):
        t_vid = fit["slope"] * t_ref + fit["offset"]
    else:
        t_vid = t_ref - fit["offset"]
    return {"offset": t_ref - t_vid, "slope": float(fit.get("slope", 1.0)),
            "rms_ms": float(fit.get("rms_ms", float("nan")))}


def _cut_video(csv, t_cut, offset):
    path = metrics.resolve_path(pipeline.find_video(csv))
    keep = path["t"] <= (t_cut - offset)
    return {k: (v[keep] if isinstance(v, np.ndarray)
                and v.shape[:1] == path["t"].shape else v)
            for k, v in path.items()}


# `deadlift_170x4_3` is EXCLUDED from the accuracy claims below, and the reason
# is a finding rather than a convenience: its own full-capture sync fits a slope
# of 0.7715 — a 22.8% clock drift with a 216 ms residual, against under 0.4% and
# ~9 ms on every other deadlift — so it cannot supply a reference. Nothing in the
# pipeline gates on `drift_pct` or `rms_ms`, which is why that has gone unnoticed;
# `test_a_broken_reference_sync_is_detectable` below pins it so it stays visible.
BAD_REFERENCE = "deadlift_170x4_3"


@pytest.mark.parametrize("keep", [1, 2])
def test_truncated_sets_recover_the_known_offset(tmp_path, keep):
    """Cut real captures to a single and to a double; ask for the answer back.

    This is the only way the corpus can say anything about accuracy on short
    sets: there are three real singles, no real doubles at all, and only one of
    the three singles carries an independent offset. Truncation manufactures
    thirteen of each with the full capture as the reference.
    """
    errors = {}
    for csv in _multi():
        if pipeline.find_video(csv) is None or BAD_REFERENCE in csv.name:
            continue
        full = pipeline.run(csv, video=None)
        ref = _reference_offset(pipeline.run(csv))
        if ref is None:
            continue
        cut = _truncate(csv, full, keep, tmp_path)
        if cut is None:
            continue
        out, t_cut = cut
        short = pipeline.run(out)
        if len(short["bounds"]) != keep:
            continue          # segmentation, not sync — not what this measures
        fit = shortset.short_sync(_cut_video(csv, t_cut, ref["offset"]),
                                  short["log"], short["velocity"][:, 2],
                                  short["bounds"], short["impacts"])
        errors[csv.name] = abs(fit["offset"] - ref["offset"])

    assert len(errors) >= 8, f"too few usable truncations: {len(errors)}"
    worst = max(errors.values())
    # 250 ms. Generous against the 1.6-104 ms measured, because the reference
    # itself carries 8-10 ms and the assumed slope contributes ~0.1 s over a
    # 30 s capture; this is a gate against a WRONG ALIGNMENT, not a precision
    # claim. The precision claim is in the module docstring, with its numbers.
    assert worst < 0.250, f"worst offset error {worst * 1000:.0f} ms: {errors}"


def test_the_deadlift_single_agrees_with_its_own_floor_impact():
    """`deadlift_200x1` is the control: two unrelated sensors, one event.

    The only real single carrying an offset that owes nothing to this module.
    It is the reason the method is measured rather than transferred, and the
    reason bench and squat singles can be believed at all.
    """
    csv = _find("deadlift_200x1")
    if csv is None or pipeline.find_video(csv) is None:
        pytest.skip("capture or video missing")
    result = pipeline.run(csv)
    path = metrics.resolve_path(pipeline.find_video(csv))

    landmark = shortset.impact_landmark(path, result["log"], result["impacts"])
    assert landmark is not None, "the single landing/impact pair went missing"

    fit = shortset.short_sync(path, result["log"], result["velocity"][:, 2],
                              result["bounds"], result["impacts"])
    assert abs(fit["offset"] - landmark) < shortset.LANDMARK_TOL_S


def test_a_broken_reference_sync_is_detectable():
    """`deadlift_170x4_3` is scored through a physically impossible clock.

    Not this module's bug and deliberately not fixed here — `capture.sync` is
    not `shortset`'s to change and the right fix is a gate on `drift_pct`,
    which is a decision rather than a patch. Pinned so that it stays visible
    and so that whoever adds the gate finds a test already describing it.

    If this starts failing, the gate has been added or the sync fixed. Delete
    the test and say which.
    """
    csv = _find(BAD_REFERENCE)
    if csv is None or pipeline.find_video(csv) is None:
        pytest.skip("capture or video missing")
    result = pipeline.run(csv)
    _, _, _, fit = metrics._video_on_imu_clock(result, pipeline.find_video(csv))
    assert abs(fit["drift_pct"]) > 5.0, "the 22.8% drift is gone — see docstring"
    assert fit["rms_ms"] > 100.0
    # And nothing refused it, which is the actual complaint.
    assert result.get("blocked") == [] or all(
        "vs_truth" not in b for b in result["blocked"])


# ------------------------------------------------- 4. do the guards fire? --

@pytest.mark.parametrize("prefix", SINGLES)
def test_containment_refuses_an_injected_whole_rep_error(prefix):
    """Perturb the OFFSET by a whole rep and containment must reject it.

    A guard observed never to complain is not evidence of anything — it may be
    unreachable. This injects exactly the error the guard exists to catch, so
    the branch is known to fire on real footage. It is the same discipline
    `bench_sync` records for its fractional-rival branch and G2 for the
    landmark gate.

    Note what is perturbed. An earlier version of this test shifted the VIDEO'S
    CLOCK and asserted the sync refused; it did not, and it was right not to —
    moving the video's time base moves the correlation peak with it, so the sync
    simply re-finds the same alignment and reports a compensating offset. That
    is the sync working. The error that has to be caught is a wrong OFFSET
    against an unmoved record, which is what a whole-rep sync failure actually
    is.
    """
    csv = _find(prefix)
    if csv is None or pipeline.find_video(csv) is None:
        pytest.skip("capture or video missing")
    result = pipeline.run(csv)
    path = metrics.resolve_path(pipeline.find_video(csv))
    log, bounds = result["log"], result["bounds"]

    fit = shortset.short_sync(path, log, result["velocity"][:, 2],
                              bounds, result["impacts"])
    good = shortset.containment(path, log, bounds, fit["offset"])
    assert 0.0 <= good <= 1.0, f"{prefix}: the true offset is not interior"

    a, b = bounds[0]
    rep_s = float(log["t"][b] - log["t"][a])
    limit = (-shortset.CONTAINMENT_TOL, 1.0 + shortset.CONTAINMENT_TOL)
    for shift in (-rep_s, rep_s):
        phase = shortset.containment(path, log, bounds, fit["offset"] + shift)
        assert not (limit[0] <= phase <= limit[1]), (
            f"{prefix}: a {shift:+.2f} s error lands at phase {phase:.2f}, "
            f"inside the permitted {limit} — the guard would not catch it")


def test_containment_phase_is_interior_on_every_single():
    """The video's one movement lands inside the IMU's one window, on all of them.

    Measured 0.44-0.88. The gate permits -0.25..1.25, so this asserts the
    MARGIN rather than the gate — a capture creeping toward the edge is
    information, and a gate that only just passes is not a gate.
    """
    seen = []
    for prefix in SINGLES:
        csv = _find(prefix)
        if csv is None or pipeline.find_video(csv) is None:
            continue
        r = shortset.run(csv)
        vt = r.get("vs_truth")
        if vt is None:
            continue
        seen.append((prefix, vt["sync_containment_phase"]))
    if not seen:
        pytest.skip("no singles present")
    for prefix, phase in seen:
        assert 0.0 <= phase <= 1.0, f"{prefix} phase {phase:.2f} left the window"


def test_a_sparse_track_is_refused_rather_than_correlated():
    """Too few tracked frames and there is nothing to align. Say so."""
    log = {"t": np.linspace(0, 10, 1000), "fs": 100.0}
    path = {"t": np.linspace(0, 10, 20), "height": np.zeros(20)}
    with pytest.raises(ValueError, match="too sparse"):
        shortset.short_sync(path, log, np.zeros(1000), [(0, 500)])


# --------------------------------------------------- 5. plateau, not point --

def test_the_overlap_floor_is_a_plateau_not_a_point():
    """Sweep `MIN_OVERLAP_FRAC` and assert the answer stops moving.

    The house rule, and the reason this module has a constant at all. The floor
    is what replaces `bench_sync`'s tuned lag window: below it the records slide
    apart until they are correlating flat against flat, and the wrong answer
    scores HIGHER than the right one — on `deadlift_200x1` a 17 s error reaches
    0.642 against the true peak's 0.335.

    Measured, 0.80 through 0.95 give the same offsets on every single. The
    shipping value is the LOW edge on purpose: the failure gets worse as the
    floor drops, so the conservative edge is the informative one.
    """
    cases = []
    for prefix in SINGLES:
        csv = _find(prefix)
        if csv is None or pipeline.find_video(csv) is None:
            continue
        r = pipeline.run(csv)
        cases.append((prefix, metrics.resolve_path(pipeline.find_video(csv)), r))
    if not cases:
        pytest.skip("no singles present")

    grid = [0.80, 0.85, 0.90, 0.95]
    answers = {}
    for prefix, path, r in cases:
        offs = []
        for frac in grid:
            try:
                fit = shortset.short_sync(path, r["log"], r["velocity"][:, 2],
                                          r["bounds"], r["impacts"],
                                          min_overlap_frac=frac)
                offs.append(fit["offset"])
            except ValueError:
                offs.append(float("nan"))
        answers[prefix] = offs

    for prefix, offs in answers.items():
        assert all(np.isfinite(o) for o in offs), f"{prefix} refused inside the plateau"
        assert max(offs) - min(offs) < 0.020, \
            f"{prefix} moves {max(offs) - min(offs):.3f} s across the plateau: {offs}"

    assert shortset.MIN_OVERLAP_FRAC == pytest.approx(grid[0]), \
        "the shipping value should be the low edge of the swept plateau"


def test_a_wide_sweep_is_what_the_overlap_floor_prevents():
    """The failure the floor exists to stop, reproduced.

    Without an overlap floor the correlation on `deadlift_200x1` prefers a lag
    ten to seventeen seconds out, and prefers it CONFIDENTLY. This asserts the
    broken behaviour still breaks, so that the floor is never mistaken for
    decoration.
    """
    csv = _find("deadlift_200x1")
    if csv is None or pipeline.find_video(csv) is None:
        pytest.skip("capture or video missing")
    r = pipeline.run(csv)
    path = metrics.resolve_path(pipeline.find_video(csv))
    truth = shortset.impact_landmark(path, r["log"], r["impacts"])

    # `bounds=[]` makes `containment` return NaN and so disables both guards,
    # which is the only way to SEE what the bare correlation does. With the
    # guards on it refuses, and that is asserted separately below.
    loose = shortset.short_sync(path, r["log"], r["velocity"][:, 2],
                                bounds=[], impacts=[], min_overlap_frac=0.05)
    tight = shortset.short_sync(path, r["log"], r["velocity"][:, 2],
                                r["bounds"], r["impacts"])

    assert abs(tight["offset"] - truth) < 0.05, "the tight sweep should be right"
    assert abs(loose["offset"] - truth) > 1.0, \
        "the loose sweep no longer fails — re-derive the floor before trusting it"
    assert loose["corr"] > tight["corr"], \
        "the wrong answer used to score HIGHER; if it no longer does, say why"

    # And with the guards on, that same loose sweep is refused rather than
    # returned — the floor is the first line and containment is the second.
    with pytest.raises(ValueError, match="containment|phase"):
        shortset.short_sync(path, r["log"], r["velocity"][:, 2],
                            r["bounds"], impacts=[], min_overlap_frac=0.05)


# ------------------------------------------------------- sign conventions --

def test_impact_landmark_is_in_the_bench_sync_convention():
    """video t + offset = IMU t, the opposite sign to `capture.sync`.

    This caught a measurement mid-flight and would have shipped a 1 s error in
    six places. Pinned against a synthetic pair where the answer is arithmetic.
    """
    t = np.linspace(0, 20, 2000)
    log = {"t": t, "fs": 100.0}
    # the video sees the bar land at 10.0 s; the IMU spike is at 10.4 s
    path = {"t": t, "height": np.where((t > 10.0) & (t < 10.5), 0.0, 0.5)}
    k = int(np.searchsorted(t, 10.4))
    off = shortset.impact_landmark(path, log, impacts=[k])
    assert off is not None
    assert off == pytest.approx(0.4, abs=0.02), \
        "sign flipped: shortset must return IMU minus video"


def test_a_landing_in_the_first_ten_seconds_is_not_discarded():
    """`capture.landings` defaults to skipping 10 s; a short record cannot afford it.

    Two of the thirteen synthetic doubles could not sync at all through the
    existing route for exactly this reason, and it reads as a missing landing
    rather than as a discarded one.
    """
    t = np.linspace(0, 20, 2000)
    path = {"t": t, "height": np.where((t > 4.0) & (t < 4.5), 0.0, 0.5)}
    assert len(capture.landings(path)) == 0, "the default still skips 10 s"
    assert len(capture.landings(path, skip_s=0.0)) == 1

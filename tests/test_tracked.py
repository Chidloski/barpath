"""Gates for the track-once-and-look-at-it cache (C31, 2026-08-07).

Two things are being protected here and they are not the same thing.

**The cache must be transparent.** A path read back from CSV must score
identically to the one that was tracked, or every number in the project quietly
depends on whether a cache file happened to exist. That is tested against real
captures, not synthetically, because the failure would be in the round trip of
real values.

**The implausibility flag must keep firing.** It is the thing that would have
caught six unusable squat clips that had been feeding comparisons for days
behind healthy-looking coverage and residual. A gate that stops noticing is
worse than no gate, so it is pinned to specific captures known to be bad AND to
specific captures known to be good.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIRS = [ROOT / "data_v2" / "video"]
CLIPS = sorted(p for d in VIDEO_DIRS if d.is_dir() for p in d.glob("*.mov"))
CACHED = [p for p in CLIPS
          if (p.resolve().parents[1] / "tracked" / f"{p.stem}.csv").is_file()]

pytestmark = pytest.mark.skipif(not CACHED, reason="no cached tracks present")


def test_every_clip_that_can_be_tracked_has_a_cached_csv():
    """The protocol is 'cache the moment a video is supplied'. Check it held.

    Not every clip CAN be tracked — `squat_140x4_3` and `squat_160x1` raise from
    `capture.validate`, which is the tracker correctly refusing footage where it
    found 0.2 and 0.4 cm of travel. Those are allowed to be absent. What is not
    allowed is a clip that tracks fine and was simply never cached, because then
    someone pays the ffmpeg cost again and, worse, nobody has looked at it.
    """
    from src import tracked

    missing = [p.stem for p in CLIPS if not tracked.csv_path(p).is_file()]
    # Known-unusable footage, refused by the tracker itself.
    allowed = {"squat_140x4_3_20260730", "squat_160x1_20260730"}
    assert set(missing) <= allowed, f"uncached clips that should be cached: {missing}"


@pytest.mark.parametrize("clip", CACHED[:6], ids=lambda p: p.stem)
def test_the_cache_round_trips_the_path(clip):
    """Read-back must reproduce the per-frame arrays, not approximately.

    12 significant figures in the CSV. At 6 this drifted ~1.6e-3 cm in a scored
    result — negligible against a 1 cm spec and still wrong to ship, because
    this repo checks regressions by bit-identity and a cache that is silently
    0.1% different is how a day gets lost.
    """
    from src import tracked

    got = tracked.read(clip)
    assert got is not None
    for key in ("t", "x", "height"):
        assert key in got, f"{clip.stem}: cached CSV lost the {key!r} column"
        assert np.isfinite(got[key]).any(), f"{clip.stem}: {key} is all NaN"
    assert len(got["t"]) == len(got["height"]) == len(got["x"])
    assert got["t"][0] <= got["t"][-1], "time must be non-decreasing"


def test_resolve_path_prefers_the_cache_and_agrees_with_a_fresh_track():
    """`metrics.resolve_path` must return the same answer either way.

    One capture only — the point is the equivalence, and a fresh track costs
    1-2 minutes of ffmpeg per clip. Tolerance is 1e-6 cm, i.e. the CSV's
    12-significant-figure write, NOT a physically meaningful tolerance.
    """
    from src import metrics

    # `bench_95x2` until 2026-08-16 — a v1 capture F1 deleted, so this test
    # SILENTLY SKIPPED rather than failing and had stopped checking anything.
    # `deadlift_200x1` is the shortest clip in the live corpus at 20.3 s, which
    # matters because the whole cost of this test is the fresh track.
    clip = next((p for p in CACHED if "deadlift_200x1" in p.stem), None)
    if clip is None:
        pytest.skip("deadlift_200x1 not present")

    cached = metrics.resolve_path(clip)
    fresh = metrics.resolve_path(clip, use_cache=False)
    assert len(cached["t"]) == len(fresh["t"])
    for key in ("t", "x", "height"):
        a, b = np.asarray(cached[key]), np.asarray(fresh[key])
        ok = np.isfinite(a) & np.isfinite(b)
        assert np.allclose(a[ok], b[ok], rtol=0, atol=1e-8), (
            f"cached {key} differs from a fresh track by "
            f"{np.nanmax(np.abs(a[ok] - b[ok])):.2e} m")


def _fake_cached_clip(tmp_path, stem, travel_m, n=900):
    """A cached track with a chosen vertical travel, in a throwaway dataset.

    Returns the .mov path `tracked.review` should be pointed at. The clip itself
    never exists — `review` reads the CACHE, and `csv_path` derives that from the
    video path, so a directory layout is all this needs. The stem carries the
    lift and the rep count because `capture.lift_of` and `pipeline.expected_reps`
    both read the filename.
    """
    from src import tracked

    video = tmp_path / "data_v2" / "video" / f"{stem}.mov"
    video.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, 30.0, n)
    # One smooth descent and return, which is what `video_reps` looks for.
    height = travel_m * 0.5 * (1.0 - np.cos(2.0 * np.pi * (t - t[0]) / (t[-1] - t[0])))
    tracked.write({"t": t, "height": height, "x": np.zeros(n)}, video)
    return video


def test_the_implausible_flag_fires_on_a_track_that_is_too_short(tmp_path):
    """The gate that six unusable squat clips got past for days.

    `squat_170x1` reported 14.0 cm of travel and `squat_pause_140x4_3` 24.7 cm,
    against squats of 65-70 cm. Coverage read 96.7-97.8% and the whole-clip
    residual 1.11-1.12 px on both, because the tracker locked onto gym furniture
    and two static points pin a similarity fit (D2, 2026-08-07). Every summary
    statistic said healthy. Travel against the lift's own range of motion is the
    statistic that does not.

    **This used to name those clips and it no longer can, which is the point.**
    Two of the four it listed were v1 captures F1 deleted on 2026-08-14, and the
    other two NOW TRACK CORRECTLY under the rebuilt `src/vtrack/` — `squat_170x1`
    at 63.7 cm and `squat_pause_140x4_3` at 65.8 cm. Measured 2026-08-16, all
    sixteen cached clips are plausible, so there is no mis-tracked capture left
    in the corpus for a positive test to point at, and editing the list could not
    have fixed that. See `test_every_cached_clip_is_plausible_now` below, which
    is the finding stated as a gate.

    So the flag is driven from a CONSTRUCTED track instead. That is strictly
    better than what it replaced: the flag's behaviour is what is under test, not
    the corpus, and this keeps a positive gate on it that cannot rot when the
    tracking improves again. 14.0 cm is D2's real measurement, kept so the test
    still records the defect it came from.
    """
    from src import tracked

    clip = _fake_cached_clip(tmp_path, "squat_140x1_20260101", 0.140)
    r = tracked.review(clip)
    assert r["travel_cm"] == pytest.approx(14.0, abs=0.1)
    assert r["implausible"], (
        f"a squat tracking {r['travel_cm']:.1f} cm must be flagged; the floor "
        f"is 0.9 x the bottom of capture.VERTICAL_ROM_M['squat']")


def test_the_implausible_flag_is_not_merely_always_on(tmp_path):
    """The same constructed route, at a plausible travel. Must NOT fire.

    Paired with the test above deliberately: a flag exercised only on bad input
    cannot be shown to discriminate, and `_fake_cached_clip` makes it cheap to
    show both halves on the same synthetic path.
    """
    from src import tracked

    clip = _fake_cached_clip(tmp_path, "squat_140x1_20260101", 0.650)
    assert not tracked.review(clip)["implausible"]


def test_every_cached_clip_is_plausible_now():
    """No capture in the corpus is mis-tracked. Recorded as a gate, not prose.

    This is the state that made the old registry unfixable, so it is asserted
    rather than left in a docstring — if a future capture or tracker change
    breaks one, this fails and names it, which is what the registry was for.

    Measured 2026-08-16: travel 26.1-65.8 cm against floors of 18.0-40.5,
    coverage 97.4-100%, every rep count matching its filename.
    """
    from src import tracked

    if not CACHED:
        pytest.skip("no cached tracks present")
    bad = []
    for clip in CACHED:
        r = tracked.review(clip)
        if r["implausible"]:
            bad.append(f"{clip.stem} travel {r['travel_cm']:.1f} cm")
    assert not bad, "mis-tracked clips are back: " + "; ".join(bad)


@pytest.mark.parametrize(
    # `bench_95x2_20260803` until 2026-08-16 — a v1 capture F1 deleted, so that
    # parametrisation skipped silently and the bench arm of this gate had not
    # run since. Replaced with a live bench rather than dropped: the three
    # entries are one per lift on purpose.
    "stem", ["squat_pause_145x4_1_20260806", "bench_92.5x6_1_20260808",
             "deadlift_160x6_1_20260804"])
def test_the_implausible_flag_does_NOT_fire_on_good_clips(stem):
    """The other half of the gate. A flag that fires on everything says nothing."""
    from src import tracked

    clip = next((p for p in CACHED if p.stem == stem), None)
    if clip is None:
        pytest.skip(f"{stem} not present")
    r = tracked.review(clip)
    assert not r["implausible"], (
        f"{stem} is a good track and the flag fired: travel {r['travel_cm']:.1f} cm")


def test_video_reps_needs_no_imu_and_finds_reps_on_a_clean_clip():
    """Rep windows come from the video ALONE — that is the point of them.

    This figure exists to check the tracking, so it must not inherit a
    segmentation error from the pipeline it is checking, and it must work on a
    clip with no paired IMU capture at all.
    """
    from src import tracked

    clip = next((p for p in CACHED if "deadlift_160x6_1" in p.stem), None)
    if clip is None:
        pytest.skip("deadlift_160x6_1 not present")
    path = tracked.read(clip)
    reps = tracked.video_reps(path)
    assert reps, "found no reps on a clip that tracks at 99% coverage"
    assert all(b > a for a, b in reps), "rep windows must be non-empty and ordered"
    assert all(b <= len(path["t"]) for _, b in reps)


def test_camera_side_is_recorded_for_every_lift():
    """It is not recoverable from the footage, so losing it loses it for good.

    On bench and squat the camera is on the lifter's right and the watch is on
    the LEFT wrist, so the referee watches the plate on the opposite end of the
    bar from the sensor and bar tilt is scored as pipeline error. Deadlift is the
    only lift where the two are on the same side.
    """
    from src import tracked, capture

    assert set(tracked.CAMERA_SIDE) == set(capture.PLATE_DIAMETER_M), (
        "a lift gained or lost a camera-side record")
    assert tracked.CAMERA_SIDE["deadlift"] != tracked.CAMERA_SIDE["bench"]


def test_the_video_finds_the_rep_count_the_FILENAME_says():
    """The check that makes this figure a gate rather than a picture.

    The filename is the only rep label these captures carry. If the video cannot
    find that many reps, either the tracking is wrong or the clip is not the set
    the name claims — and the first version of `video_reps` reported n-1 windows
    on every bench and n-2 on every deadlift while looking perfectly plausible.

    Two structural bugs caused that and both are pinned here by consequence.
    A rep is bracketed by the extremum the set STARTS on — bottoms for a
    deadlift, TOPS for a bench or squat — and `find_peaks` cannot return an
    extremum at index 0 or -1, which is exactly where a deadlift's first and
    last floor rests sit.

    Every clip must agree with its filename EXCEPT the ones independently
    flagged as mis-tracked. That exception is the point: the two checks are
    computed from different quantities — rep count from the height's extrema,
    `implausible` from total travel against the lift's range of motion — and
    they land on the same clips.
    """
    from src import tracked

    disagree = []
    for clip in CACHED:
        r = tracked.review(clip)
        if r["expected_reps"] is None or r["reps_match"]:
            continue
        disagree.append((clip.stem, r["expected_reps"], r["n_reps"],
                         r["implausible"]))

    unexplained = [d for d in disagree if not d[3]]
    assert not unexplained, (
        "clips whose rep count disagrees with the filename and which are NOT "
        f"flagged as mis-tracked: {unexplained}")

    # And the check must still be capable of firing, or it is measuring nothing.
    # 14, not the 20 this asserted until 2026-08-14. That floor was set when
    # both datasets were cached — 28 clips — and the v1 half has since been
    # deleted, leaving 16. This tracks the corpus; it is a "the rep finder has
    # not broadly regressed" floor, not a finding.
    assert len(CACHED) - len(disagree) >= 14, (
        f"only {len(CACHED) - len(disagree)} clips match their filename; the "
        f"rep finder has probably regressed")

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
VIDEO_DIRS = [ROOT / "data" / "video", ROOT / "data_v2" / "video"]
CLIPS = sorted(p for d in VIDEO_DIRS if d.is_dir() for p in d.glob("*.mov"))
CACHED = [p for p in CLIPS
          if (p.resolve().parents[1] / "tracked" / f"{p.stem}.csv").is_file()]

pytestmark = pytest.mark.skipif(not CACHED, reason="no cached tracks present")


def test_every_clip_that_can_be_tracked_has_a_cached_csv():
    """The protocol is 'cache the moment a video is supplied'. Check it held.

    Not every clip CAN be tracked — `squat_140x4_3` and `squat_160x1` raise from
    `truth.validate`, which is the tracker correctly refusing footage where it
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
    from src import metrics, tracked

    clip = next((p for p in CACHED if "bench_95x2" in p.stem), None)
    if clip is None:
        pytest.skip("bench_95x2 not present")

    cached = metrics.resolve_path(clip)
    fresh = metrics.resolve_path(clip, use_cache=False)
    assert len(cached["t"]) == len(fresh["t"])
    for key in ("t", "x", "height"):
        a, b = np.asarray(cached[key]), np.asarray(fresh[key])
        ok = np.isfinite(a) & np.isfinite(b)
        assert np.allclose(a[ok], b[ok], rtol=0, atol=1e-8), (
            f"cached {key} differs from a fresh track by "
            f"{np.nanmax(np.abs(a[ok] - b[ok])):.2e} m")


def test_the_implausible_flag_fires_on_the_clips_known_to_be_broken():
    """The gate that six unusable squat clips got past for days.

    `squat_170x1` reports 14.0 cm of travel and `squat_pause_140x4_3` 24.7 cm,
    against squats of 65-70 cm. Coverage reads 96.7-97.8% and the whole-clip
    residual 1.11-1.12 px on both, because the tracker locked onto gym furniture
    and two static points pin a similarity fit (D2, 2026-08-07). Every summary
    statistic said healthy. Travel against the lift's own range of motion is the
    statistic that does not.
    """
    from src import tracked

    known_bad = ["squat_170x1_20260806", "squat_pause_140x4_3_20260806",
                 "squat_140x4_1_20260730", "squat_140x4_2_20260730"]
    seen = 0
    for stem in known_bad:
        clip = next((p for p in CACHED if p.stem == stem), None)
        if clip is None:
            continue
        seen += 1
        assert tracked.review(clip)["implausible"], (
            f"{stem} is known to be mis-tracked and the flag stopped firing")
    if not seen:
        pytest.skip("none of the known-bad clips are present")


@pytest.mark.parametrize(
    "stem", ["squat_pause_145x4_1_20260806", "bench_95x2_20260803",
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
    from src import tracked, truth

    assert set(tracked.CAMERA_SIDE) == set(truth.PLATE_DIAMETER_M), (
        "a lift gained or lost a camera-side record")
    assert tracked.CAMERA_SIDE["deadlift"] != tracked.CAMERA_SIDE["bench"]

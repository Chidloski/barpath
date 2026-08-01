"""
Gates for the sticker tracker.

Two kinds, kept apart on purpose, because this project has been burned by
mixing them. The algebraic ones build a constellation, transform it by a known
similarity and check the transform comes back — they catch sign and convention
bugs and they are unit tests, not evidence. The rest run on the real
`data_v2/` captures and are the only ones that say the tracker works.

`data_v2/video_only/` is gitignored, as `data/video/` is. Everything needing it
skips when it is absent rather than failing, so a fresh clone still runs green
on the algebra.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from src import markers, truth

VIDEO_DIR = Path(__file__).resolve().parents[1] / "data_v2" / "video_only"
CAPTURES = ["deadlift_150x5_20260801", "deadlift_160x5_20260801",
            "deadlift_190x1_20260801", "bench_85x6_20260801",
            "bench_110x1_20260801"]
DEADLIFTS = [c for c in CAPTURES if c.startswith("deadlift")]


def _video(stem: str) -> Path:
    p = VIDEO_DIR / f"{stem}.mov"
    if not p.exists():
        pytest.skip(f"{p.name} not present (data_v2 is gitignored)")
    return p


@pytest.fixture(scope="module")
def paths() -> dict:
    """Every capture tracked once. Decoding and tracking is ~10 s each."""
    out = {}
    for stem in CAPTURES:
        p = VIDEO_DIR / f"{stem}.mov"
        if not p.exists():
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out[stem] = markers.bar_path(p)
    if not out:
        pytest.skip("no data_v2 captures present")
    return out


# ------------------------------------------------------------- algebra --
def _constellation(radius=80.0, centre=(300.0, 180.0), angles=(0, 120, 240)):
    a = np.deg2rad(np.asarray(angles, float))
    return np.column_stack([centre[0] + radius * np.sin(a),
                            centre[1] + radius * np.cos(a)])


@pytest.mark.parametrize("scale,angle_deg,shift", [
    (1.0, 0.0, (0.0, 0.0)),
    (1.0, 37.0, (0.0, 0.0)),
    (0.8, -12.0, (25.0, -40.0)),
    (1.35, 180.0, (-60.0, 15.0)),
])
def test_similarity_round_trips(scale, angle_deg, shift):
    """A similarity applied and then recovered returns what was applied.

    The one test that would catch a (y, x) versus (x, y) slip, which this
    module is exposed to throughout: image points are stored row-first and the
    complex-number fit in `_similarity` is naturally x-first.
    """
    src = _constellation()
    ang = np.deg2rad(angle_deg)
    dst = markers._apply_yx(scale, ang, src - src.mean(axis=0),
                            src.mean(axis=0) + np.array(shift))
    s, a, off = markers._similarity(src, dst)
    assert s == pytest.approx(scale, rel=1e-9)
    assert np.cos(a - ang) == pytest.approx(1.0, abs=1e-12)
    back = markers._apply_yx(s, a, src, off)
    assert np.allclose(back, dst, atol=1e-8)


def test_similarity_recovers_centroid():
    """The model origin maps to the transformed centroid.

    This is the identity the whole path rests on: `track` reports the model
    origin through the fitted pose and calls it the bar. If that is not the
    centroid, every distance downstream is wrong by a constant nobody would see.
    """
    src = _constellation()
    local = src - src.mean(axis=0)
    dst = markers._apply_yx(1.2, 0.5, local, np.array([410.0, 95.0]))
    s, a, off = markers._similarity(local, dst)
    origin = markers._apply_yx(s, a, np.zeros((1, 2)), off)[0]
    assert np.allclose(origin, dst.mean(axis=0), atol=1e-9)


def test_triangle_regularity_rejects_a_sliver():
    assert markers._triangle_ok(_constellation()) == pytest.approx(1.0)
    sliver = np.array([[0.0, 0.0], [0.0, 100.0], [1.0, 50.0]])
    assert markers._triangle_ok(sliver) == 0.0


def test_correspondence_is_rotation_invariant_in_the_centroid():
    """Relabelling the triangle moves the angle, never the centre.

    This is why `track` reports a centroid rather than a labelled point: a
    re-acquisition cannot tell which sticker is which on a near-equilateral
    triangle, and this test is the statement that it does not have to.
    """
    src = _constellation()
    local = src - src.mean(axis=0)
    tri = markers._apply_yx(1.0, np.deg2rad(25.0), local,
                            np.array([250.0, 140.0]))
    centres = []
    for roll in range(3):
        s, a, off, r = markers._best_correspondence(local, np.roll(tri, roll, 0), 0.0)
        centres.append(markers._apply_yx(s, a, np.zeros((1, 2)), off)[0])
        assert r == pytest.approx(0.0, abs=1e-8)
    assert np.allclose(centres[0], centres[1], atol=1e-8)
    assert np.allclose(centres[0], centres[2], atol=1e-8)


def test_detect_finds_a_blob_to_a_tenth_of_a_pixel():
    """A blurred marker is located to ~0.05 px, swept over sub-pixel offsets.

    The accuracy claim in the module docstring is what makes 360x640 footage
    adequate, so it is gated rather than asserted. Measured here over 40 random
    sub-pixel placements: mean 0.05 px, worst 0.13.

    **The marker is modelled as a Gaussian, and that is the honest model rather
    than the convenient one.** A hard-edged binary disc scores 0.32 px mean and
    0.61 worst on the same code — but that error is pixel quantisation of the
    test's own synthetic disc, not of the estimator, and no lens produces one.
    Blur is what makes sub-pixel centroiding work; a test without it measures
    the wrong thing and would have set this gate five times too loose.
    """
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:120, 0:120]
    errs = []
    for _ in range(40):
        ty, tx = 60 + rng.uniform(-0.5, 0.5), 70 + rng.uniform(-0.5, 0.5)
        g = np.exp(-(((yy - ty) ** 2 + (xx - tx) ** 2) / (2 * 1.1 ** 2)))
        frame = (0.15 + 0.75 * g).astype(np.float32)
        frame += rng.normal(0, 0.01, frame.shape).astype(np.float32)
        dets = markers.detect(frame)
        assert len(dets) >= 1
        errs.append(np.hypot(dets[0, 0] - ty, dets[0, 1] - tx))
    assert np.mean(errs) < 0.10
    assert np.max(errs) < 0.20


# --------------------------------------------------------- real capture --
@pytest.mark.parametrize("stem", CAPTURES)
def test_every_capture_tracks_essentially_completely(paths, stem):
    """Coverage, and it is the headline improvement over `truth.py`.

    All five captures track 100% of frames with all three rim markers seen.
    The bar is what this asserts against: the first working version held lock
    through 12 s of setup on `deadlift_150x5` and lost the bar at the instant of
    lift-off, reporting nothing for the 13 s that mattered.
    """
    if stem not in paths:
        pytest.skip(f"{stem} not present")
    p = paths[stem]
    tracked = np.isfinite(p["height"]).mean()
    assert tracked > 0.97, f"{stem}: only {tracked:.1%} of frames tracked"
    assert (p["n_markers"] == 3).mean() > 0.95


@pytest.mark.parametrize("stem", CAPTURES)
def test_fit_residual_is_sub_pixel(paths, stem):
    """The rigid model actually fits the detections.

    Note this is only meaningful because `track` refuses to report a frame on
    fewer than three markers here — a two-marker fit is exact and its residual
    is zero whatever it is looking at. See `track`.
    """
    if stem not in paths:
        pytest.skip(f"{stem} not present")
    assert np.nanmedian(paths[stem]["residual_px"]) < 1.5


@pytest.mark.parametrize("stem", CAPTURES)
def test_apparent_size_is_rigid(paths, stem):
    """A steel plate does not change size.

    The gate that catches the failure the per-step scale limit let through: on
    `bench_85x6` the fitted circumradius once wandered from 29 px to 94 px, each
    individual step inside a 6% limit. Rigidity is the physical fact that says
    that cannot happen, so it is the thing to assert.
    """
    if stem not in paths:
        pytest.skip(f"{stem} not present")
    r = paths[stem]["circumradius_px"]
    r = r[np.isfinite(r)]
    assert r.max() / r.min() < 1.25, f"{stem}: circumradius {r.min():.0f}..{r.max():.0f} px"


@pytest.mark.parametrize("stem", CAPTURES)
def test_vertical_rom_is_anatomically_possible(paths, stem):
    """Whole-clip travel sits inside `truth.VERTICAL_ROM_M`.

    The same table the reconstruction is judged by, applied to the referee.
    `truth.rom_flags`' own docstring makes the argument: a referee has no
    standing to be exempt from the check it applies. The old tracker fails this
    on `bench_85x6`, where it reports 0.2 cm of travel and raises.
    """
    if stem not in paths:
        pytest.skip(f"{stem} not present")
    lift = truth.lift_of(stem)
    assert truth.rom_flags(lift, [paths[stem]["travel_m"]]) == []


def test_deadlift_rom_spread_beats_the_old_tracker(paths):
    """One lifter's deadlift ROM does not vary by much, and this is the check.

    `truth.VERTICAL_ROM_M` records the old tracker's 19 cm spread across three
    captures of a range of motion fixed by the lifter's own limbs, and calls it
    the largest known error in that module. On the same lifter's 2026-08-01
    captures the sticker tracker spans 4.8 cm.

    Asserted loosely at 10 cm. The point is the order of magnitude, and pinning
    it tighter would make an arbitrary threshold out of three samples — the
    mistake `synthetic-threshold-inside-seed-spread` records.
    """
    got = [paths[s]["travel_m"] for s in DEADLIFTS if s in paths]
    if len(got) < 3:
        pytest.skip("need all three deadlifts")
    assert (max(got) - min(got)) * 100 < 10.0


def test_scale_agrees_with_the_rim_detector_on_deadlift(paths):
    """Where the rim IS detectable, the constant scale agrees with it.

    This is what makes `STICKER_RATIO` a measurement rather than a fitted
    convenience. It is deliberately asserted on deadlift only: on bench the rim
    detector returns a plate half again too large, which is exactly why the
    scale does not depend on it.
    """
    for stem in DEADLIFTS:
        if stem not in paths:
            continue
        cal = paths[stem]["calibration"]
        assert cal["rim_detection_credible"], (
            f"{stem}: detected ratio {cal['sticker_ratio']:.3f} against "
            f"STICKER_RATIO {markers.STICKER_RATIO}")


def test_hub_sticker_is_not_in_the_path(paths):
    """The end-cap marker's offset tracks height, so it must stay out of the fit.

    The measurement behind the design decision, re-made as a gate. The hub sits
    on the sleeve, which protrudes toward the camera, so its offset from the rim
    centroid is parallax and moves as the bar rises past the lens. Correlation
    with height was 0.949 when this was found. If a future change folds the hub
    into the pose, the vertical inherits that.
    """
    for stem in DEADLIFTS:
        if stem not in paths:
            continue
        p = paths[stem]
        off = p["hub"][:, 0] - p["centre_px"][:, 0] if "centre_px" in p else None
        if off is None:
            pytest.skip("centre_px not exposed")
        m = np.isfinite(off) & np.isfinite(p["height"])
        if m.sum() > 50:
            assert abs(np.corrcoef(off[m], p["height"][m])[0, 1]) > 0.5


def test_validate_raises_on_a_motionless_track():
    """The failure `truth.validate` exists for, re-checked here.

    A tracker that reports a confident path through a static piece of gym is the
    expensive failure in this project's history, and it is worth having a gate
    that the loud version is still loud.
    """
    path = {"height": np.zeros(100), "x": np.zeros(100),
            "travel_m": 0.01, "n_markers": np.full(100, 3),
            "calibration": {"sticker_ratio": markers.STICKER_RATIO,
                            "spacing_bias_cm": 0.0, "centre_offset_px": 1.0,
                            "rotation_deg": 1.0}}
    with pytest.raises(ValueError, match="not on a barbell"):
        markers.validate(path, "deadlift_fake.mov")

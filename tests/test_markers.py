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

from unittest import mock

import numpy as np
import pytest

from src import markers







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








def test_top_of_travel_residual_sees_what_a_whole_clip_median_cannot():
    """The gate discriminates — asserted, not assumed.

    Algebraic, so it runs without `data_v2`. Builds the exact blind spot: a
    track that is excellent everywhere except the top of travel. The old
    whole-clip gate passes it with a 30x margin; the new one must fail it.

    Worth having as a test rather than a comment because "we replaced an
    aggregate with a stratified statistic" is only worth anything if the
    stratified one actually responds to the stratification.
    """
    n = 400
    h = np.linspace(0.0, 1.0, n)
    r = np.where(h > 0.85, 6.0, 0.05)
    path = {"height": h, "residual_px": r, "m_per_px_t": np.full(n, 0.002)}

    top = markers.top_of_travel_residual(path)
    assert np.nanmedian(r) < 1.5                       # old gate: passes
    assert top["median_cm"] > markers.MAX_TOP_RESIDUAL_CM   # new gate: fails
    assert top["ratio"] > 50
    assert top["n"] > 20

    # and it stays quiet on a track that is uniformly good
    flat = {"height": h, "residual_px": np.full(n, 0.4),
            "m_per_px_t": np.full(n, 0.002)}
    good = markers.top_of_travel_residual(flat)
    assert good["median_cm"] < markers.MAX_TOP_RESIDUAL_CM
    assert 0.9 < good["ratio"] < 1.1
















def test_validate_raises_on_a_motionless_track():
    """The failure `capture.validate` exists for, re-checked here.

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


# ------------------------------------------------- C21: static suppression --
def _blob_frame(points, shape=(200, 160), rng=None):
    """A frame with a blurred Gaussian marker at each (y, x)."""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    frame = np.full(shape, 0.15, np.float32)
    for ty, tx in points:
        frame = np.maximum(
            frame, (0.15 + 0.75 * np.exp(
                -(((yy - ty) ** 2 + (xx - tx) ** 2) / (2 * 1.1 ** 2)))
            ).astype(np.float32))
    if rng is not None:
        frame = frame + rng.normal(0, 0.01, shape).astype(np.float32)
    return frame


def test_static_points_finds_the_fixtures_and_not_the_bar():
    """C21's premise: on a tripod, furniture is at a fixed pixel and the bar is not.

    Three fixed markers stand for rack holes and ceiling lights; one sweeps
    down the frame as a barbell does. `static_points` must return the three and
    none of the sweep, because everything downstream — the whole seeding fix —
    rests on that separation holding.
    """
    rng = np.random.default_rng(0)
    fixtures = [(40.0, 30.0), (150.0, 120.0), (60.0, 140.0)]
    stack = np.stack([_blob_frame(fixtures + [(30.0 + 4.0 * k, 80.0)], rng=rng)
                      for k in range(30)])

    static = markers.static_points(stack, n_sample=30)

    assert len(static) == 3, f"expected the three fixtures, got {len(static)}"
    for f in fixtures:
        assert np.hypot(*(static - np.array(f)).T).min() < 2.0, f"missed {f}"
    # no returned point lies on the sweep
    sweep = np.array([(30.0 + 4.0 * k, 80.0) for k in range(30)])
    d = np.hypot(static[:, 0, None] - sweep[None, :, 0],
                 static[:, 1, None] - sweep[None, :, 1])
    assert d.min() > 3.0, "a moving marker was judged static"


def test_static_points_suppresses_a_bar_that_barely_moves():
    """The limit C21 carries, pinned rather than left in prose.

    `static_points` cannot distinguish a fixture from a bar that sits racked
    for most of the clip — both recur at one pixel. This is the failure mode to
    know about, so it is a test that asserts the WRONG-looking behaviour on
    purpose: with the marker still for 26 of 30 frames it is suppressed.

    What it costs in practice is bounded by the real measurement behind the 0.7
    default: on `bench_95x2` the worst real sticker recurs at 0.48, because the
    bar is racked for about half the clip and not much more. A capture that
    breaks this surfaces as `bar_path` raising "no sticker constellation found"
    on footage with plainly visible markers, and the response is to RAISE
    `recur_max`, not lower it.
    """
    rng = np.random.default_rng(1)
    frames = [_blob_frame([(100.0, 80.0)], rng=rng) for _ in range(26)]
    frames += [_blob_frame([(100.0 + 20.0 * k, 80.0)], rng=rng) for k in range(1, 5)]
    static = markers.static_points(np.stack(frames), n_sample=30)

    assert len(static) == 1
    assert np.hypot(*(static[0] - np.array([100.0, 80.0]))) < 2.0

    # and it is recovered by raising the threshold, which is the documented fix
    assert len(markers.static_points(np.stack(frames), n_sample=30,
                                     recur_max=0.9)) == 0


def test_suppress_drops_static_detections_and_keeps_the_rest():
    dets = np.array([[10.0, 10.0, 0.9], [50.0, 50.0, 0.8], [90.0, 20.0, 0.7]])
    static = np.array([[10.2, 9.9], [90.0, 20.0]])

    kept = markers._suppress(dets, static)

    assert len(kept) == 1
    assert kept[0, 0] == 50.0
    # no static points is a no-op, not an error
    assert len(markers._suppress(dets, np.empty((0, 2)))) == 3






# --------------------------------------------- C23: selection by verification --
def test_spread_members_covers_the_group_not_one_moment():
    """A shortlist of near-duplicates from one frame would be no shortlist.

    Hypotheses within a group are dominated by near-identical triples from the
    same frame, differing only in sub-pixel detection picks. Taking the top `k`
    by score returns `k` copies of one moment, which is what C23 had to stop
    doing — the group is right and the moment is what needs choosing.
    """
    group = []
    for frame in (0, 100, 200, 300, 400):
        for dup in range(4):
            group.append((frame, {"score": 0.5 + 0.01 * dup,
                                  "centre": np.array([10.0 + frame, 20.0]),
                                  "circumradius": 90.0}))

    picked = markers._spread_members(group, 3)

    assert len(picked) == 3
    assert len({i for i, _ in picked}) == 3, "three distinct frames"
    # and it keeps the best-scoring member of each frame it picks
    for _, c in picked:
        assert c["score"] == pytest.approx(0.53)


def test_trial_merit_refuses_a_two_marker_fit_and_a_floppy_one():
    """The two failure modes the merit is shaped around, both measured on real
    captures and both pinned here on synthetic tracks.

    A two-marker fit is EXACT — four degrees of freedom, four equations — so it
    reports 0.00 px however wrong it is. That is what the pre-C23 seeder did on
    `bench_95x2`: 0.00 px, while tracking the bench. And a triple that
    re-acquires onto whatever is nearby can hold three markers while its
    apparent size swings; on `deadlift_190x1` one did, 88 to 128 px, and it
    outscored the real plate until the rigidity term was added.
    """
    n = 400
    rng = np.random.default_rng(0)

    def fake(n_markers, resid, scale):
        return {"n_markers": np.full(n, n_markers),
                "residual_px": np.full(n, resid, float),
                "scale": np.asarray(scale, float),
                "centre": np.zeros((n, 2))}

    good = fake(3, 0.15, np.full(n, 1.0) + rng.normal(0, 0.004, n))
    pairs = fake(2, 0.00, np.full(n, 1.0))               # exact, and worthless
    floppy = fake(3, 0.60, np.linspace(0.85, 1.15, n))   # 3 markers, not rigid

    scores = []
    for trk in (good, pairs, floppy):
        with mock.patch.object(markers, "track", return_value=trk):
            scores.append(markers._trial_merit(np.zeros((n, 8, 8)), 0, {}, None, None))

    assert scores[1] == 0.0, "a pure two-marker track must score nothing"
    assert scores[0] > 3 * scores[2], (
        f"a rigid track must beat a floppy one: {scores[0]:.3f} vs {scores[2]:.3f}")


PAIRED_BENCH = ["bench_92.5x4_1_20260803", "bench_92.5x4_2_20260803",
                "bench_92.5x4_3_20260803", "bench_95x2_20260803"]








# --------------------------------------------------------------------- C26 --
# The conic path, for a plate with more than three stickers. None of these can
# run on a real capture: every clip held carries THREE rim stickers, and three
# points cannot determine a conic, so there is no regression footage for this
# and will not be until an 8-sticker plate is filmed. What follows is therefore
# synthetic on purpose and is confined to what synthetic data can still settle
# here — algebraic identities about projection, in CLAUDE.md's words. It is not
# evidence that the tracker works on footage.

def _project_circle(n_markers, tilt_deg, roll_deg, f=1200.0, dist=3.0,
                    r=0.20, centre_yx=(300.0, 400.0), spacing_deg=None):
    """Perspective-project markers on a circle. Returns (points_yx, true_centre_yx).

    `spacing_deg` gives uneven placement, so the real plates C23 measured —
    129/102/129 on bench, 94.9/111.4/153.7 on squat — can be reproduced exactly.
    """
    if spacing_deg is None:
        ang = np.arange(n_markers) * 2 * np.pi / n_markers
    else:
        ang = np.deg2rad(np.cumsum([0.0] + list(spacing_deg))[:n_markers])
    pts3 = np.stack([r * np.cos(ang), r * np.sin(ang), np.zeros(len(ang))], 1)
    t, ro = np.deg2rad(tilt_deg), np.deg2rad(roll_deg)
    rz = np.array([[np.cos(ro), -np.sin(ro), 0], [np.sin(ro), np.cos(ro), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
    cam = ((rx @ rz) @ pts3.T).T + np.array([0, 0, dist])
    ys = f * cam[:, 1] / cam[:, 2] + centre_yx[0]
    xs = f * cam[:, 0] / cam[:, 2] + centre_yx[1]
    return np.column_stack([ys, xs]), np.array(centre_yx, float)


def test_fit_ellipse_recovers_a_known_circle_exactly():
    """Zero tilt: the projection is a circle and the fit must return it."""
    pts, true_c = _project_circle(8, 0, 0)
    ell = markers.fit_ellipse(pts)
    assert ell is not None
    assert np.hypot(*(ell["centre"] - true_c)) < 1e-6
    assert abs(ell["semi_minor"] / ell["semi_major"] - 1.0) < 1e-6


@pytest.mark.parametrize("n", [5, 6, 8, 12])
def test_fit_ellipse_is_indifferent_to_how_many_markers(n):
    """Five is the minimum and more must not change the answer.

    The claim the whole layout change rests on: a conic has five degrees of
    freedom, so any number of points on the same circle determines the same
    conic.
    """
    pts, _ = _project_circle(n, 25, 40)
    ell = markers.fit_ellipse(pts)
    ref = markers.fit_ellipse(_project_circle(64, 25, 40)[0])
    assert ell is not None and ref is not None
    assert np.hypot(*(ell["centre"] - ref["centre"])) < 0.05
    assert abs(ell["semi_major"] - ref["semi_major"]) < 0.05


def test_fit_ellipse_needs_five_points():
    """Four cannot determine a conic and the fit must refuse rather than guess."""
    pts, _ = _project_circle(4, 20, 0)
    assert markers.fit_ellipse(pts) is None


def test_conic_beats_the_centroid_on_the_REAL_plate_spacings():
    """The claim that justifies eight stickers, on the spacings C23 measured.

    Note what is NOT claimed. On IDEAL 120-degree spacing the centroid is the
    better estimator of the two — both are biased outward by perspective and
    the conic's bias is about twice the centroid's — and the companion test
    below pins that, so nobody re-derives this as "the conic fixes
    perspective". It does not. It removes the SPACING term, and on real plates
    that term is the larger one.
    """
    for name, spacing in (("bench", [129.0, 102.0]),
                          ("squat", [94.9, 111.4])):
        p3, true_c = _project_circle(3, 20, 37, spacing_deg=spacing)
        centroid_err = np.hypot(*(p3.mean(axis=0) - true_c))
        p8, _ = _project_circle(8, 20, 37)
        ell = markers.fit_ellipse(p8)
        conic_err = np.hypot(*(ell["centre"] - true_c))
        assert conic_err < centroid_err / 2.0, (
            f"{name}: conic {conic_err:.2f} px vs centroid {centroid_err:.2f} px")


def test_the_conic_centre_is_NOT_a_perspective_fix():
    """Pinned so the limitation cannot quietly become a claim.

    With three stickers at exactly 120 degrees the centroid is EXACT under an
    affine camera and merely biased under a real one; the ellipse centre is
    biased harder. If this ever starts failing, someone has made the conic
    perspective-aware and the docstrings in `fit_ellipse` need rewriting.
    """
    p3, true_c = _project_circle(3, 30, 0)
    p8, _ = _project_circle(8, 30, 0)
    centroid_err = np.hypot(*(p3.mean(axis=0) - true_c))
    conic_err = np.hypot(*(markers.fit_ellipse(p8)["centre"] - true_c))
    assert conic_err > centroid_err


@pytest.mark.parametrize("tilt", [0, 10, 20, 30, 40])
def test_semi_major_is_tilt_invariant_where_the_mean_radius_is_not(tilt):
    """The scale half, and the larger of the two errors this fixes.

    `track` fits a similarity, which reads foreshortening as a change of
    distance, so a tilting plate shrinks its own scale and drives it into
    `m_per_px_t`. The semi-major axis of a projected circle is unforeshortened
    under an affine camera.
    """
    ref = markers.fit_ellipse(_project_circle(8, 0, 0)[0])["semi_major"]
    pts, _ = _project_circle(8, tilt, 0)
    semi = markers.fit_ellipse(pts)["semi_major"]
    mean_r = float(np.hypot(*(pts - pts.mean(axis=0)).T).mean())
    assert abs(semi / ref - 1.0) < 0.005, f"semi-major moved {100*(semi/ref-1):.2f}%"
    if tilt >= 30:
        assert abs(mean_r / ref - 1.0) > 0.05, (
            "the mean radius is supposed to be the BROKEN one here; if it has "
            "stopped degrading, this test is no longer measuring anything")


def test_axis_ratio_reports_the_tilt_it_assumes():
    """`axis_ratio` is cos(tilt) under an affine camera, and is the falsifier."""
    for tilt in (0, 20, 40):
        pts, _ = _project_circle(8, tilt, 0)
        ell = markers.fit_ellipse(pts)
        ratio = ell["semi_minor"] / ell["semi_major"]
        assert abs(ratio - np.cos(np.deg2rad(tilt))) < 0.02


def test_ellipse_candidates_finds_eight_stickers_among_clutter():
    """Seeding, on the layout the current seeder cannot admit at all."""
    rng = np.random.default_rng(4)
    pts, _ = _project_circle(8, 15, 25, dist=3.0, r=0.20,
                             centre_yx=(100.0, 80.0))
    clutter = np.column_stack([rng.uniform(5, 195, 14), rng.uniform(5, 155, 14)])
    frame = _blob_frame(np.vstack([pts, clutter]), rng=rng)
    got = markers.ellipse_candidates(frame, radius_band=(20.0, 150.0),
                                     require_hub=False)
    assert got, "no ellipse hypothesis found at all"
    best = got[0]
    d = np.hypot(*(best["rim"][:, None, :] - pts[None, :, :]).transpose(2, 0, 1))

    # RECALL is what the seeder must not get wrong: every sticker on the plate
    # has to be in the model, or `track` follows a partial constellation.
    found = (d.min(axis=0) < 1.5).sum()
    assert found == 8, f"only {found} of 8 stickers recovered"

    # PRECISION is allowed to be imperfect and the arithmetic says it must be.
    # A `tol_px` annulus round a 79 px ellipse is ~2450 px2 of a 200x160 frame,
    # about 8% of it, so each unrelated detection has roughly a one-in-twelve
    # chance of sitting on the true ellipse by luck; with ~25 of them, one or
    # two coincidental inliers is the expected outcome, not a defect. They cost
    # `track` a permanently unmatched slot — `score` caps at 8/9 rather than
    # 1.0 — and nothing else, because association simply never finds them.
    spurious = int((d.min(axis=1) >= 1.5).sum())
    assert spurious <= 2, f"{spurious} inliers are not stickers, expected 0-2"


def test_the_current_triangle_seeder_cannot_admit_eight_stickers():
    """Why C26 exists, pinned as a fact rather than left in a commit message.

    Eight evenly spaced stickers have no near-equilateral triple: the best
    available is every third one, at 135/135/90 degrees, whose chord spread is
    0.255 against `_triangle_ok`'s tolerance of 0.25. It misses by 0.005 and
    the candidate list comes back empty.
    """
    import itertools
    ang = np.arange(8) * 2 * np.pi / 8
    pts = np.column_stack([np.cos(ang), np.sin(ang)]) * 100.0
    best = max(markers._triangle_ok(pts[list(c)])
               for c in itertools.combinations(range(8), 3))
    assert best == 0.0, "8 evenly spaced stickers now pass _triangle_ok"


def test_conic_track_falls_back_where_markers_are_missing():
    """Occlusion must degrade to the similarity pose, not to a hole."""
    pts, _ = _project_circle(8, 10, 0, centre_yx=(100.0, 80.0))
    matched = np.repeat(pts[None, :, :], 4, axis=0)
    matched[1, 5:] = np.nan          # 5 left: still enough
    matched[2, 4:] = np.nan          # 4 left: not enough
    con = markers.conic_track({"matched": matched})
    assert np.isfinite(con["centre"][0, 0])
    assert np.isfinite(con["centre"][1, 0])
    assert not np.isfinite(con["centre"][2, 0])
    assert con["n_used"].tolist() == [8, 5, 4, 8]



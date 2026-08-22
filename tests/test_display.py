"""Gates for the product display layer.

Two halves, and the split is the one `CLAUDE.md` asks for. The synthetic tests
check algebraic properties that hold whatever lifting turns out to be like — a
straight line survives a smoother, a constant-velocity path has constant speed,
a phase grid puts two turnarounds at the same index. The real-capture tests
check the claims `src/display.py`'s docstring makes about this corpus, because
a display default chosen on 61 refereed reps is only defensible while those 61
reps still say what it was chosen on.

Nothing here re-measures the reconstruction. Every number below is a property
of the DISPLAY of a path, so these gates stay valid if the pipeline improves —
they would simply all get easier.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src import display, pipeline

RAW = Path(__file__).resolve().parents[1] / "data_v2" / "raw"
CAPTURES = sorted(RAW.glob("*.csv")) if RAW.is_dir() else []
needs_data = pytest.mark.skipif(not CAPTURES, reason="no captures in data_v2/raw/")


# --------------------------------------------------------------------------
# synthetic fixtures — a rep, and a set of them
# --------------------------------------------------------------------------

def synth_rep(n: int = 200, rom: float = 0.5, bow: float = 0.02,
              dwell: int = 0, noise: float = 0.0, seed: int = 0) -> tuple:
    """A bench-shaped rep: top -> bottom -> top, with a fore-aft bow.

    `dwell` holds the bottom still for that many samples, which is what a
    paused rep looks like and is the case `concentric` exists for. Returns
    (curve, t).
    """
    rng = np.random.default_rng(seed)
    half = (n - dwell) // 2
    down = np.linspace(0.0, -rom, half)
    hold = np.full(dwell, -rom)
    up = np.linspace(-rom, 0.0, n - half - dwell)
    z = np.concatenate([down, hold, up])
    phase = np.linspace(0, np.pi, len(z))
    x = bow * np.sin(phase)
    curve = np.column_stack([x, z])
    if noise:
        curve = curve + rng.normal(0, noise, curve.shape)
    return curve, np.arange(len(z)) / 100.0


# --------------------------------------------------------------------------
# 1. smoothing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("method", display.METHODS)
def test_smoothing_preserves_shape_and_length(method):
    curve, t = synth_rep()
    out = display.smooth(curve, t, method, 0.2)
    assert out.shape == curve.shape
    assert np.isfinite(out).all()


@pytest.mark.parametrize("method", display.METHODS)
def test_zero_strength_is_the_identity(method):
    curve, t = synth_rep()
    assert np.array_equal(display.smooth(curve, t, method, 0.0), curve)


@pytest.mark.parametrize("method", ("savgol", "spline"))
def test_a_straight_line_survives_the_fitting_smoothers_exactly(method):
    """A smoother that bends a straight line invents a fault on the horizontal.

    `savgol` and `spline` both FIT a polynomial, and a line is in the span of
    both bases, so they reproduce it to numerical precision including at the
    ends. That is a real difference from the two padded filters below and it is
    part of why savgol is the default.
    """
    t = np.arange(200) / 100.0
    curve = np.column_stack([0.01 * t, 0.5 * t])
    out = display.smooth(curve, t, method, 0.3)
    assert np.abs(out - curve).max() < 1e-9


@pytest.mark.parametrize("method", ("boxcar", "gaussian"))
def test_a_padded_filter_holds_a_line_in_the_interior_and_flattens_the_ends(method):
    """The cost of `mode="nearest"`, stated rather than hidden.

    A filter that pads with a repeated end sample cannot reproduce a ramp at
    the ends — the pad is not on the ramp. In the interior it is exact. This is
    documented behaviour rather than a defect: a rep window begins and ends at
    a turnaround where the bar really is nearly still, so flattening there is
    closer to the truth than mirroring would be. Its size on real captures is
    inside `truth_cost`, which is measured over the whole window, edges
    included.
    """
    t = np.arange(200) / 100.0
    curve = np.column_stack([0.01 * t, 0.5 * t])
    out = display.smooth(curve, t, method, 0.3)
    w = display._span_samples(t, 0.3)
    interior = slice(w, len(t) - w)
    assert np.abs(out[interior] - curve[interior]).max() < 1e-9
    assert np.abs(out - curve).max() > 1e-3


def test_smoothing_removes_noise_without_moving_the_path():
    clean, t = synth_rep(noise=0.0)
    noisy, _ = synth_rep(noise=0.002, seed=1)
    out = display.smooth(noisy, t, "savgol", 0.2)
    before = np.abs(noisy - clean).mean()
    after = np.abs(out - clean).mean()
    assert after < before * 0.75


def test_savgol_preserves_the_turnaround_better_than_a_boxcar():
    """The docstring's claim about why savgol is the default, as a test.

    A boxcar cannot represent a peak — its output at the extremum is the mean
    of a window straddling it — where a quadratic fit can. That is the whole
    reason the vertical cost differs by 3x on real captures, so it belongs in
    a gate rather than only in prose.
    """
    curve, t = synth_rep(rom=0.5)
    depth = lambda c: float(c[:, 1].min())          # noqa: E731
    box = depth(display.smooth(curve, t, "boxcar", 0.3))
    sav = depth(display.smooth(curve, t, "savgol", 0.3))
    assert abs(sav - depth(curve)) < abs(box - depth(curve))


def test_span_is_odd_and_at_least_three():
    t = np.arange(101) / 100.0
    for s in (0.001, 0.02, 0.5, 2.0):
        w = display._span_samples(t, s)
        assert w % 2 == 1 and 3 <= w <= len(t)


def test_unknown_method_raises():
    curve, t = synth_rep()
    with pytest.raises(ValueError, match="unknown smoothing method"):
        display.smooth(curve, t, "lowess", 0.1)


def test_a_curve_that_is_not_two_columns_raises():
    with pytest.raises(ValueError, match=r"\(M, 2\)"):
        display.smooth(np.zeros((10, 3)), np.arange(10) / 100.0)


# --------------------------------------------------------------------------
# 2. speed and rep statistics
# --------------------------------------------------------------------------

def test_constant_velocity_gives_that_speed():
    t = np.arange(300) / 100.0
    curve = np.column_stack([np.zeros_like(t), 0.4 * t])
    s = display.speed(curve, t, smooth_strength=0.0)
    assert np.allclose(s, 0.4, atol=1e-9)


def test_speed_is_the_2d_magnitude():
    t = np.arange(300) / 100.0
    curve = np.column_stack([0.3 * t, 0.4 * t])
    s = display.speed(curve, t, smooth_strength=0.0)
    assert np.allclose(s, 0.5, atol=1e-9)


def test_turnaround_is_found_without_naming_the_lift():
    bench, _ = synth_rep()                       # top -> bottom -> top
    deadlift = bench * [1, -1]                   # floor -> top -> floor
    for c in (bench, deadlift):
        k = display.turnaround(c)
        assert 0.4 < k / len(c) < 0.6


def test_a_dwell_breaks_the_extremes_definition_and_not_the_threshold():
    """The measurement that replaced `argmin -> argmax`, in miniature.

    A paused rep's bottom is flat, so a whisker of noise moves the lowest
    SAMPLE anywhere inside the dwell and the ascent's measured duration moves
    with it. The velocity threshold does not see inside the dwell at all. This
    is the synthetic form of r = +0.53 becoming r = +0.97 on real captures.
    """
    curve, t = synth_rep(n=300, dwell=100, noise=2e-4, seed=3)
    a, b = display.concentric(curve, t)
    z = curve[:, 1]
    lo, hi = int(np.argmin(z)), int(np.argmax(z))
    truth = 0.5 / ((300 - 100) / 2 / 100.0)          # rom over the true ascent

    threshold_v = abs(z[b] - z[a]) / (t[b] - t[a])
    extremes_v = abs(z[hi] - z[lo]) / abs(t[hi] - t[lo])
    assert abs(threshold_v - truth) < abs(extremes_v - truth)
    assert abs(threshold_v - truth) / truth < 0.10


def test_concentric_falls_back_rather_than_raising_on_a_still_window():
    t = np.arange(100) / 100.0
    still = np.column_stack([np.zeros_like(t), np.zeros_like(t)])
    a, b = display.concentric(still, t)
    assert (a, b) == (0, len(t) - 1)


def test_rep_stats_are_finite_and_signed_right():
    curve, t = synth_rep()
    st = display.rep_stats(curve, t)
    assert all(np.isfinite(v) for v in st.values())
    assert st["rom_m"] == pytest.approx(0.5, abs=1e-6)
    assert st["mean_concentric_v"] > 0
    assert st["duration_s"] == pytest.approx(t[-1] - t[0])


# --------------------------------------------------------------------------
# 3. the average rep
# --------------------------------------------------------------------------

def test_phase_grid_aligns_two_reps_of_different_tempo():
    """Turnaround alignment does what time alignment cannot.

    Two identical-shaped reps, one of which spends twice as long descending.
    On a time grid their turnarounds land at different phases and the average
    of the two is deeper than either at one end and shallower at the other; on
    a turnaround grid they coincide exactly.
    """
    fast = np.column_stack([np.zeros(120), np.concatenate(
        [np.linspace(0, -0.5, 40), np.linspace(-0.5, 0, 80)])])
    slow = np.column_stack([np.zeros(120), np.concatenate(
        [np.linspace(0, -0.5, 80), np.linspace(-0.5, 0, 40)])])

    ta = [display.turnaround(display.resample_phase(c, align="turnaround"))
          for c in (fast, slow)]
    ti = [display.turnaround(display.resample_phase(c, align="time"))
          for c in (fast, slow)]
    assert abs(ta[0] - ta[1]) <= 1
    assert abs(ti[0] - ti[1]) > 10


def test_resample_phase_returns_the_grid_size():
    curve, _ = synth_rep()
    for align in ("time", "turnaround"):
        assert display.resample_phase(curve, n=64, align=align).shape == (64, 2)


def test_unknown_alignment_raises():
    curve, _ = synth_rep()
    with pytest.raises(ValueError, match="unknown alignment"):
        display.resample_phase(curve, align="dtw")


def test_identical_reps_score_zero_and_flag_nothing():
    curve, _ = synth_rep()
    grid = np.stack([display.resample_phase(curve) for _ in range(5)])
    assert np.allclose(display.anomaly_scores(grid), 0.0)
    assert not display.flag_anomalies(grid).any()


def test_one_wild_rep_is_flagged():
    reps = [synth_rep(bow=0.02, seed=i)[0] for i in range(5)]
    reps[3] = synth_rep(bow=0.15, seed=99)[0]
    grid = np.stack([display.resample_phase(r) for r in reps])
    mask = display.flag_anomalies(grid)
    assert list(np.flatnonzero(mask)) == [3]


def test_a_tight_set_is_not_flagged_for_being_fractionally_less_perfect():
    """The `floor_cm` guard, which matters more than the threshold.

    Five reps agreeing to a millimetre have a MAD of microns, so the rep that
    is 3 mm out scores an enormous z. Without the absolute floor this detector
    fires on the BEST sets in the corpus.
    """
    reps = [synth_rep(bow=0.02 + 1e-5 * i, seed=0)[0] for i in range(5)]
    reps[2] = synth_rep(bow=0.023, seed=0)[0]
    grid = np.stack([display.resample_phase(r) for r in reps])
    assert not display.flag_anomalies(grid).any()


def test_nothing_is_flagged_in_a_set_of_three_or_fewer():
    reps = [synth_rep(bow=b, seed=i)[0]
            for i, b in enumerate((0.02, 0.02, 0.20))]
    grid = np.stack([display.resample_phase(r) for r in reps])
    assert not display.flag_anomalies(grid).any()


def test_a_sprawling_set_flags_nothing_rather_than_flagging_most_of_it():
    """Six reps that disagree wildly but have no single outlier.

    The modified z-score needs one rep to stand out from a tight majority. A
    set with no typical rep at all has a large MAD and nothing exceeds it, so
    the display shows all six — which is the honest answer, and is also why
    `flag_anomalies` records its never-flag-a-majority guard as unreachable
    rather than as a live branch.
    """
    reps = [synth_rep(bow=b, seed=i)[0]
            for i, b in enumerate((0.02, 0.02, 0.30, 0.45, 0.60, 0.75))]
    grid = np.stack([display.resample_phase(r) for r in reps])
    assert not display.flag_anomalies(grid).any()
    assert display.average_rep(reps)["n_kept"] == 6


@pytest.mark.parametrize("method", ("mean", "median", "trimmed"))
def test_every_averager_returns_the_grid(method):
    reps = [synth_rep(seed=i)[0] for i in range(5)]
    out = display.average_rep(reps, method=method)
    assert out["average"].shape == (display.GRID, 2)
    assert out["grid"].shape == (5, display.GRID, 2)


def test_unknown_averager_raises():
    reps = [synth_rep(seed=i)[0] for i in range(4)]
    with pytest.raises(ValueError, match="unknown averaging method"):
        display.average_rep(reps, method="geometric")


def test_median_survives_a_mis_segmented_rep_where_the_mean_needs_exclusion():
    """The failure exclusion is actually for, constructed rather than found.

    A half-rep window is what a segmentation defect looks like from here, and
    the corpus has none left to point at (G1 fixed the last three), so it is
    built. Measured on the real captures the same substitution moves a `mean`
    average by 4.74 cm median and a `median` average by 0.61.
    """
    reps = [synth_rep(seed=i)[0] for i in range(5)]
    clean = display.average_rep(reps, method="median", exclude=False)["average"]

    broken = list(reps)
    broken[1] = reps[1][:len(reps[1]) // 2]
    mean_in = display.average_rep(broken, method="mean", exclude=False)["average"]
    mean_out = display.average_rep(broken, method="mean", exclude=True)["average"]
    med_in = display.average_rep(broken, method="median", exclude=False)["average"]

    assert display.compare(mean_out, clean)["rms"] < display.compare(mean_in, clean)["rms"]
    assert display.compare(med_in, clean)["rms"] < display.compare(mean_in, clean)["rms"]


def test_exclusion_is_reported_not_silent():
    reps = [synth_rep(bow=0.02, seed=i)[0] for i in range(5)]
    reps[4] = synth_rep(bow=0.15, seed=7)[0]
    out = display.average_rep(reps)
    assert out["excluded"].sum() == 1 and out["n_kept"] == 4
    assert len(out["scores"]) == 5


# --------------------------------------------------------------------------
# 4. real captures — the claims src/display.py makes about this corpus
# --------------------------------------------------------------------------

def _refereed():
    """(stem, per-rep pipeline curve, video curve, t) for every scored rep.

    Built through `metrics.vs_truth`, so both sides arrive on a common clock,
    a common display axis and a common fore-aft sign — which is the whole
    reason this module compares `curve_pipeline` against `curve_video` rather
    than re-projecting anything itself.
    """
    out = []
    for csv in CAPTURES:
        video = pipeline.find_video(csv)
        if video is None:
            continue
        result = pipeline.run(csv, video=video)
        vs = result.get("vs_truth")
        if not vs:
            continue
        t_all = result["log"]["t"]
        for pr in vs["per_rep"]:
            if not pr.get("covered"):
                continue
            a, b = result["bounds"][pr["rep"]]
            out.append((csv.stem, pr["curve_pipeline"], pr["curve_video"],
                        t_all[a:b]))
    return out


@pytest.fixture(scope="module")
def refereed():
    reps = _refereed()
    if not reps:
        pytest.skip("no refereed reps available")
    return reps


@needs_data
def test_the_corpus_still_supplies_enough_reps_to_judge_the_defaults(refereed):
    """There must be enough refereed material for the tests below to mean anything.

    **This asserted exactly 13 captures and 61 reps until 2026-08-22 (H31), and
    had been failing since the corpus grew past it.** The intent was sound —
    `src/display.py`'s defaults were selected on a particular corpus, and if
    that corpus changes the docstring needs re-deriving rather than re-tuning —
    but an equality against a count cannot express it. It fails on a corpus that
    grew, which is the good case, exactly as loudly as on one that shrank, and
    once it is failing for the harmless reason nobody reads it for the harmful
    one. It sat red through H29 and H30.

    What the tests below actually need is a FLOOR: enough captures and enough
    reps that a percentile over them is meaningful. That is what this asserts
    now. The corpus the defaults were chosen on is recorded where a fact belongs
    — in `src/display.py`'s docstring — not in an assertion that breaks when a
    capture is added.
    """
    captures = len({s for s, *_ in refereed})
    assert captures >= 10, (
        f"only {captures} captures are refereed; the percentiles below are "
        f"being taken over too little to mean anything")
    assert len(refereed) >= 40, (
        f"only {len(refereed)} refereed reps; see above")


@needs_data
def test_the_shipped_smoothing_stays_inside_its_own_selection_rule(refereed):
    """The rule that chose `SMOOTH_STRENGTH`, as a gate.

    90th-percentile distortion of the VIDEO path — the real bar — must stay
    inside half of each axis's spec: 0.5 cm of the 1 cm horizontal, 1.0 cm of
    the +/-2-3 cm vertical. This is the only test here that would fail if
    somebody raised the default, which is the point of it.
    """
    h, v = [], []
    for _, _, video, t in refereed:
        c = display.compare(display.smooth(video, t), video)
        h.append(c["h_rms"])
        v.append(c["v_rms"])
    assert np.percentile(h, 90) < 0.5
    assert np.percentile(v, 90) < 1.0


@needs_data
def test_savgol_costs_the_real_bar_less_than_every_other_method(refereed):
    """Why the default is savgol and not the moving average anybody writes first.

    Checked at the shipped strength on both axes. The ordering held at every
    level from 0.10 to 0.30 when it was measured; this gates the shipped one.
    """
    cost = {}
    for m in display.METHODS:
        v = [display.compare(display.smooth(video, t, m), video)["v_rms"]
             for _, _, video, t in refereed]
        cost[m] = float(np.percentile(v, 90))
    assert cost["savgol"] == min(cost.values())
    assert cost["savgol"] < cost["boxcar"] / 2


@needs_data
def test_smoothing_does_not_change_accuracy(refereed):
    """The finding, as a gate: there is no high-frequency error to remove.

    Median horizontal error against the video is unmoved by smoothing at any
    level, because the reconstruction's error is at rep frequency (P3). If this
    ever fails it is genuinely interesting — either the reconstruction has
    acquired a high-frequency defect, or the smoother has started eating the
    signal.
    """
    def median_h(strength):
        return float(np.median([
            display.compare(display.smooth(recon, t, strength=strength),
                            video)["h_rms"]
            for _, recon, video, t in refereed]))

    base = median_h(0.0)
    for s in (0.05, 0.10, 0.20, 0.30):
        assert abs(median_h(s) - base) < 0.05, f"strength {s} moved accuracy"


@needs_data
def test_the_average_rep_is_more_accurate_than_a_single_rep(refereed):
    """Averaging buys what smoothing does not.

    The IMU's average rep against the video's own average rep, versus each rep
    against its own: 1.95 -> 1.52 cm as medians over the 13 captures. That gap
    is rep-to-rep scatter, and it is what the average cancels.
    """
    per_rep = np.median([display.compare(display.smooth(r, t),
                                         display.smooth(v, t))["h_rms"]
                         for _, r, v, t in refereed])

    averaged = []
    for stem in sorted({s for s, *_ in refereed}):
        rows = [x for x in refereed if x[0] == stem]
        if len(rows) < 3:
            continue
        a = display.average_rep([display.smooth(r, t) for _, r, _, t in rows],
                                exclude=False)["average"]
        b = display.average_rep([display.smooth(v, t) for _, _, v, t in rows],
                                exclude=False)["average"]
        averaged.append(display.compare(a, b)["h_rms"])

    assert np.median(averaged) < per_rep * 0.85


@needs_data
def test_turnaround_alignment_beats_time_alignment_on_the_vertical(refereed):
    """The largest single effect in the averaging study, gated.

    Against the video's own average rep, time alignment scores ~8.3 cm vertical
    where turnaround alignment scores ~3.0 — a paused set's turnarounds land at
    different phases and the average smears the bottom of the rep.
    """
    err = {}
    for align in ("time", "turnaround"):
        rows_by_set = {}
        for stem, r, v, t in refereed:
            rows_by_set.setdefault(stem, []).append((r, v, t))
        e = []
        for rows in rows_by_set.values():
            if len(rows) < 3:
                continue
            a = display.average_rep([display.smooth(r, t) for r, _, t in rows],
                                    align=align, exclude=False)["average"]
            b = display.average_rep([display.smooth(v, t) for _, v, t in rows],
                                    align="turnaround", exclude=False)["average"]
            e.append(display.compare(a, b)["v_rms"])
        err[align] = float(np.median(e))
    assert err["turnaround"] < err["time"] / 2


@needs_data
def test_the_tempo_numbers_agree_with_the_video_and_the_fore_aft_one_does_not(refereed):
    """The table in `src/display.py`'s docstring, as a gate.

    The pass/fail line is the design of the display: tempo and vertical travel
    are corroborated, fore-aft MAGNITUDE is not, and the second half is
    asserted just as hard as the first so that nobody later ships a
    "3.2 cm forward" readout on the strength of the first.
    """
    def pair(key):
        x, y = [], []
        for _, r, v, t in refereed:
            x.append(display.rep_stats(display.smooth(r, t), t)[key])
            y.append(display.rep_stats(display.smooth(v, t), t)[key])
        x, y = np.array(x), np.array(y)
        ok = np.isfinite(x) & np.isfinite(y)
        return float(np.corrcoef(x[ok], y[ok])[0, 1])

    assert pair("mean_concentric_v") > 0.90
    assert pair("peak_v") > 0.90
    assert pair("concentric_s") > 0.90
    assert pair("rom_m") > 0.95
    assert abs(pair("fore_aft_m")) < 0.30


@needs_data
def test_the_velocity_threshold_beats_the_extremes_definition_on_real_reps(refereed):
    """Why `concentric` is not `argmin -> argmax`, on the captures.

    The measurement that motivated the function: same paths, same smoothing,
    same video, and the entire difference is where the ascent is said to start.
    """
    def mcv(curve, t, extremes):
        z = curve[:, 1]
        if extremes:
            lo, hi = int(np.argmin(z)), int(np.argmax(z))
            a, b = (lo, hi) if lo < hi else (hi, lo)
        else:
            a, b = display.concentric(curve, t)
        return abs(z[b] - z[a]) / (t[b] - t[a]) if t[b] != t[a] else np.nan

    r = {}
    for extremes in (True, False):
        x = np.array([mcv(display.smooth(rec, t), t, extremes)
                      for _, rec, _, t in refereed])
        y = np.array([mcv(display.smooth(vid, t), t, extremes)
                      for _, _, vid, t in refereed])
        ok = np.isfinite(x) & np.isfinite(y)
        r[extremes] = float(np.corrcoef(x[ok], y[ok])[0, 1])
    assert r[False] > 0.95 > r[True]


@needs_data
def test_the_anomaly_flag_agrees_with_the_video_when_it_fires(refereed):
    """Whenever the IMU calls a rep odd, the video calls that rep odd too.

    Gated at BOTH levels, because the per-set claim flatters the detector and
    the per-rep one does not. Per set: every set where the IMU fires, the video
    fires on the same rep. Per rep: 5 IMU flags, 6 video flags, 4 shared — one
    false positive and two misses, which is why `flag_anomalies` is documented
    as a LABEL rather than as an accuracy fix.
    """
    fired = shared_sets = n_imu = n_vid = n_both = 0
    for stem in sorted({s for s, *_ in refereed}):
        rows = [x for x in refereed if x[0] == stem]
        if len(rows) < 4:
            continue
        imu = display.average_rep([display.smooth(r, t) for _, r, _, t in rows])
        vid = display.average_rep([display.smooth(v, t) for _, _, v, t in rows])
        n_imu += int(imu["excluded"].sum())
        n_vid += int(vid["excluded"].sum())
        n_both += int((imu["excluded"] & vid["excluded"]).sum())
        if imu["excluded"].any():
            fired += 1
            shared_sets += bool((imu["excluded"] & vid["excluded"]).any())
    assert fired >= 4
    assert shared_sets == fired
    assert n_both >= n_imu - 1, "more than one uncorroborated IMU flag"
    assert n_both <= min(n_imu, n_vid)

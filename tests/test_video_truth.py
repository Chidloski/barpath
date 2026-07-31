"""
Gates on the referee itself — the video, and the clock that ties it to the IMU.

Separate from test_real_data.py, which asks whether the PIPELINE is right. This
file asks whether the thing we judge the pipeline against is right, which is a
different question and a prior one: every horizontal number in this project is
measured through `truth.bar_path` and one of two sync routes, so an error here
is invisible everywhere and corrupts everything downstream.

The distinction earned its own file on 2026-07-31. A bench sync landed with a
docstring quoting correlations of 0.96-1.00 and a re-rack check agreeing to a
median of 13 ms. Measured, the correlations were 0.37-0.70 and the check was
wrong by half a second. Nothing caught it because nothing ran it. The gates
below are the ones that would have.

`data/raw/` and `data/video/` are gitignored, so everything here skips cleanly
when the captures are absent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
VIDEO = ROOT / "data" / "video"

DEADLIFTS = [
    ("deadlift_155x6_1_20260728", "deadlift_155x6_1_20260728_122828"),
    ("deadlift_155x6_2_20260728", "deadlift_155x6_2_20260728_123603"),
    ("deadlift_180x3_20260728", "deadlift_180x3_20260728_121739"),
]

# Every bench capture with the rep count from its filename label. All seven sync
# as of C10. Four of them did not under the peak-height threshold C8 shipped;
# that threshold turned out to be measuring what fraction of each clip was
# lifting rather than how well the signals agreed. See bench_sync.
BENCHES = [
    ("bench_90x4_1_20260727", 4),
    ("bench_90x4_2_20260727", 4),
    ("bench_90x4_3_20260727", 4),
    ("bench_92.5x2_20260727", 2),
    ("bench_spoto_90x5_1_20260730", 5),
    ("bench_spoto_90x5_2_20260730", 5),
    ("bench_spoto_90x5_3_20260730", 5),
]


def _cadence(result: dict) -> float:
    starts = [float(result["log"]["t"][a]) for a, _ in result["bounds"]]
    return float(np.median(np.diff(starts))) if len(starts) > 1 else float("nan")


def _has(video: str, csv: str = "") -> bool:
    if not (VIDEO / f"{video}.mov").exists():
        return False
    return not csv or (RAW / f"{csv}.csv").exists()


def _csv_for(stem: str) -> Path | None:
    return next(RAW.glob(f"{stem}_*.csv"), None) if RAW.is_dir() else None


# --------------------------------------------------------- the sync control --
# The measurement that licenses bench sync at all. Ceilings, not targets: the
# peak lands within 3, 14 and 18 ms of an independently known offset, so 50 ms
# leaves headroom without admitting a sync that has actually come loose. Rep
# timing is specified at +/-50 ms, which is the other reason for that number.
SYNC_CONTROL_MS = 50.0


@pytest.mark.parametrize("video,csv", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_correlation_sync_recovers_a_known_offset(video, csv):
    """The bench sync method, checked where the answer is already known.

    `bench_sync` cross-correlates the video's vertical bar velocity against the
    reconstruction's and takes the lag at the peak. On bench there is nothing
    to check that against — no floor impact, no landmark, nothing. On DEADLIFT
    there is: `truth.sync` fits the offset from video landings matched to IMU
    floor impacts, two unrelated sensors seeing the same events to an 11-16 ms
    residual.

    So run the correlation on a deadlift and ask whether it finds that offset.
    It does, to within 18 ms. **This test is the entire licence for trusting a
    bench number**, because the bench validation is transferred from here and
    is not measured on bench. If this regresses, every bench figure in the
    project becomes unfounded — not merely worse, unfounded.

    Note what it does NOT establish: that the transfer is valid. A bench
    capture with a genuine landmark would establish that, and none exists.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline, segment, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    log = result["log"]
    path = truth.bar_path(VIDEO / f"{video}.mov")

    impacts = np.array([float(log["t"][k]) for k in segment.impact_anchors(log)])
    fit = truth.sync(truth.landings(path), impacts)
    true_lag = float(np.median(truth.to_imu_time(path, fit) - path["t"]))

    got = metrics.bench_sync(path, log, result["velocity"][:, 2],
                             _cadence(result))
    err_ms = abs(got["offset"] - true_lag) * 1000.0

    assert err_ms < SYNC_CONTROL_MS, (
        f"{video}: the correlation put the offset {err_ms:.0f} ms from the "
        f"landings/impacts fit. Bench sync is calibrated on this agreement.")


@pytest.mark.parametrize("video,csv", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_peak_height_does_not_say_whether_the_lag_is_right(video, csv):
    """The correlation VALUE is a poor proxy for the lag being right.

    This pins the mistake that cost two thresholds. `SYNC_MIN_CORR = 0.70`
    shipped first, on a docstring claiming bench correlations of 0.96-1.00, and
    rejected all seven bench captures. 0.55 replaced it and admitted three. But
    `deadlift_180x3` scores **0.595** while recovering the true offset to 18 ms,
    so a correct sync can sit at the very bottom of the range, and no height
    threshold separates good from bad.

    Asserting the ceiling as well as the floor is deliberate: if a change ever
    pushes these known-good deadlift correlations near 0.9, the reasoning behind
    the acceptance rule has moved and wants re-deriving.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import metrics, pipeline, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    path = truth.bar_path(VIDEO / f"{video}.mov")
    corr = metrics.bench_sync(path, result["log"], result["velocity"][:, 2],
                              _cadence(result))["corr"]

    assert 0.55 <= corr < 0.90, (
        f"{video}: correlation {corr:.3f} outside the 0.55-0.90 band these "
        f"known-good deadlift syncs occupied when the rule was written")


@pytest.mark.parametrize("video,reps", BENCHES, ids=[b[0] for b in BENCHES])
def test_every_bench_rival_is_a_whole_rep_period_away(video, reps):
    """The acceptance rule, and the measurement it rests on. All seven sync.

    `bench_sync` accepts on the SHAPE of the correlation curve rather than the
    height of its peak, because height conflates agreement with what fraction
    of the clip is lifting — bench clips are 20-30% reps against deadlift's
    50-56%, which is most of why the old threshold refused four of these.

    What actually matters is whether the peak is confusable with anything. It
    is: every bench capture has rivals at 0.73-0.81 of the peak. But **all
    eleven of them, across all seven captures, sit within 5% of exactly one rep
    period** — 0.96 to 1.05 P. So the lag is identified modulo one rep and never
    worse, and both quantities measured through it are invariant to a whole-rep
    shift (horizontal rms, and phase by construction).

    A FRACTIONAL-period rival would be a real failure and is what the rule
    refuses on. No capture in `data/raw/` produces one, so that branch is
    unexercised here — this test pins the measurement, not the guard.
    """
    csv = _csv_for(video)
    if not _has(video) or csv is None:
        pytest.skip(f"{video} not present")
    from src import metrics, pipeline, truth

    result = pipeline.run(csv)
    path = truth.bar_path(VIDEO / f"{video}.mov")
    got = metrics.bench_sync(path, result["log"], result["velocity"][:, 2],
                             _cadence(result))

    assert abs(got["offset"]) < 5.0
    assert got["rivals"], (
        f"{video}: no rival above {metrics.RIVAL_FRAC} of the peak. That is "
        f"better than measured and worth understanding before accepting it")
    for lag, frac, periods in got["rivals"]:
        assert abs(periods - round(periods)) <= metrics.PERIOD_TOL
        assert abs(round(periods)) >= 1


def test_a_bench_single_cannot_be_synced_by_this_route():
    """A cadence needs two reps, so the rule cannot be applied to a single.

    Stated as a test because it is a real limit rather than an oversight, and
    because the capture protocol asks for a bench single — for a different
    reason (C5's singleton rule is predicted to segment onto the unrack). When
    that capture arrives it will land here too, and it should raise rather than
    quietly sync on an unchecked peak.
    """
    from src import metrics

    with pytest.raises(ValueError, match="fewer than two reps"):
        metrics.bench_sync({"t": np.arange(10.0), "height": np.zeros(10)},
                           {"t": np.arange(10.0)}, np.zeros(10), float("nan"))


def _corr_curve(path, log, vz, lags):
    """The correlation `bench_sync` maximises, exposed for inspection."""
    from src import metrics, truth

    t_v = path["t"]
    ok = np.isfinite(path["height"])
    lo, hi = float(t_v[ok][0]), float(t_v[ok][-1])
    grid = np.arange(lo, hi, 1.0 / metrics.SYNC_FS)
    v_video = metrics._band(np.gradient(
        np.interp(grid, t_v[ok], truth._smooth(path["height"], 9)[ok]), grid))
    t_i = np.arange(float(log["t"][0]), float(log["t"][-1]), 1.0 / metrics.SYNC_FS)
    v_imu = metrics._band(np.interp(t_i, log["t"], vz))

    out = []
    for lag in lags:
        g = grid + lag
        m = (g >= t_i[0]) & (g <= t_i[-1])
        if m.sum() < 2 * metrics.SYNC_FS:
            out.append(np.nan)
            continue
        a = v_video[m] - v_video[m].mean()
        b = np.interp(g[m], t_i, v_imu)
        b = b - b.mean()
        out.append(float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)))
    return np.array(out)


def _sidelobe_ratio(c, lags, guard_s=0.4):
    pk = int(np.nanargmax(c))
    far = np.abs(lags - lags[pk]) > guard_s
    loc = [i for i in range(1, len(c) - 1)
           if far[i] and c[i] >= c[i - 1] and c[i] >= c[i + 1]]
    return max(c[i] for i in loc) / c[pk]


@pytest.mark.parametrize("video,csv", DEADLIFTS, ids=[d[0] for d in DEADLIFTS])
def test_the_deadlift_peak_is_well_isolated(video, csv):
    """On deadlift the peak stands clear of its sidelobes. Pin that it does.

    This is the other half of what makes the control meaningful. The peak is in
    the right place AND it is not a coin flip against some other local maximum:
    the best rival more than 0.4 s away reaches 0.51-0.74 of it.

    Bench does worse — see the next test — so this is the reference the bench
    number is read against, and it must not drift.
    """
    if not _has(video, csv):
        pytest.skip(f"{video} or {csv} not present")
    from src import pipeline, truth

    result = pipeline.run(RAW / f"{csv}.csv")
    path = truth.bar_path(VIDEO / f"{video}.mov")
    # 20 ms is plenty: this measures a peak's HEIGHT against its rivals, not
    # its position, and the sidelobes are seconds wide. bench_sync itself
    # sweeps at 1/SYNC_FS because there the lag is the answer.
    lags = np.arange(-5, 5, 0.02)
    c = _corr_curve(path, result["log"], result["velocity"][:, 2], lags)

    assert _sidelobe_ratio(c, lags) < 0.78


@pytest.mark.parametrize("video", [b[0] for b in BENCHES])
def test_bench_sidelobes_sit_at_the_rep_period_and_cost_little(video):
    """Bench's peak is weakly isolated, and it does not matter. Both asserted.

    **Weakly isolated:** the best rival more than 0.4 s from the peak reaches
    ~0.80 of it, against 0.51-0.74 on deadlift where the peak is known correct.
    So bench sits outside the range the method has been shown to work in.

    **Why:** a bench set is periodic. The rival lags are -2.81, +0.85 and
    -3.465 s against a cadence near 2.9 s, so the alternative alignment pairs
    rep n with rep n+1 — and touch-and-go reps really do resemble each other,
    so it really does correlate almost as well. This is the set's structure, not
    noise, and no threshold fixes it.

    **Why it does not matter for what we quote:** scoring at the rival lag
    instead of the peak gives horizontal 3.11 / 3.23 / 2.44 cm against
    3.67 / 2.69 / 2.63 — no worse, and lower on two of three. The bench
    horizontal number survives a sync error of seconds, so it does not rest on
    resolving this. Bench VERTICAL is a different matter and is not quoted
    without the caveat in `bench_sync`.

    If this test starts failing because the ratio DROPPED, that is good news and
    means something isolated the peak — find out what before deleting it.
    """
    csv = _csv_for(video)
    if not _has(video) or csv is None:
        pytest.skip(f"{video} not present")
    from src import pipeline, truth

    result = pipeline.run(csv)
    path = truth.bar_path(VIDEO / f"{video}.mov")
    # 20 ms is plenty: this measures a peak's HEIGHT against its rivals, not
    # its position, and the sidelobes are seconds wide. bench_sync itself
    # sweeps at 1/SYNC_FS because there the lag is the answer.
    lags = np.arange(-5, 5, 0.02)
    c = _corr_curve(path, result["log"], result["velocity"][:, 2], lags)

    assert 0.70 < _sidelobe_ratio(c, lags) < 0.88, (
        f"{video}: the sidelobe structure has changed — re-read whether the "
        f"rep-period argument in bench_sync still holds")


# ------------------------------------------------------------ bench tracking --
@pytest.mark.parametrize("video,reps", BENCHES, ids=[b[0] for b in BENCHES])
def test_bench_tracks_the_plate_and_not_the_gym(video, reps):
    """Bench tracking, asserted on travel and rep count rather than on NCC.

    This replaces `test_bench_tracking_fails_loudly_rather_than_silently`,
    which pinned the old state — automatic seeding does not work on bench — and
    whose own docstring asked for exactly this replacement when a seed was
    wired in. `truth.SEEDS` now carries one hand-placed seed per capture.

    **Why NCC is not the assertion.** The seed was placed by hand, and a hand
    placed until the score looks good proves only that the template kept
    matching something. This project has already been fooled by that once: it
    tracked a motionless background patch for a whole clip at 0.907 median NCC
    and reported 0.0 cm of bar travel. So the gates here are the two quantities
    a stuck or drifting template cannot fake — travel inside the lift's ROM
    band, and a video-derived rep count matching the filename label. NCC is
    checked far below where it sits, only to catch total collapse.

    Auto-seeding remains unsolved and is not a tuning problem: four seeders
    were tried on 2026-07-31 — dark disc, circular-edge radial gradient, dark
    disc weighted by motion energy, and a dark-annulus rim filter — and all four
    preferred the lifter-and-bench silhouette. See truth.SEEDS.
    """
    if not _has(video):
        pytest.skip(f"{video} not present")
    from src import truth

    assert video in truth.SEEDS, f"{video} has no hand-placed seed"

    path = truth.bar_path(VIDEO / f"{video}.mov")
    h = path["height"][np.isfinite(path["height"])]
    travel = float(h.max() - h.min())

    lo, hi = truth.VERTICAL_ROM_M["bench"]
    assert lo <= travel <= hi, (
        f"{video}: whole-clip travel {travel*100:.1f} cm is outside the "
        f"{lo*100:.0f}-{hi*100:.0f} cm bench band — the template is not on "
        f"the plate for the whole clip")
    assert np.nanmedian(path["score"]) > 0.60


@pytest.mark.parametrize("video,reps", BENCHES, ids=[b[0] for b in BENCHES])
def test_bench_video_rep_count_matches_the_label(video, reps):
    """The video's own rep count must match the filename, 7 of 7.

    Independent of the IMU entirely — it counts reversals in the tracked height
    — so it is a real check on the track rather than a self-consistency one. A
    template that slips onto the lifter or the bench reports the wrong number
    here long before travel goes out of band.
    """
    if not _has(video):
        pytest.skip(f"{video} not present")
    from src import truth

    path = truth.bar_path(VIDEO / f"{video}.mov")
    h = truth._smooth(path["height"], 15)

    # A bench rep is one descent and one press: count local minima that clear
    # a third of the set's travel, which no tracker jitter reaches.
    span = h.max() - h.min()
    troughs = [i for i in range(1, len(h) - 1)
               if h[i] < h[i - 1] and h[i] <= h[i + 1] and h[i] < h.min() + span / 3]
    merged = [t for k, t in enumerate(troughs)
              if k == 0 or path["t"][t] - path["t"][troughs[k - 1]] > 0.8]

    assert len(merged) == reps, (
        f"{video}: the video shows {len(merged)} reps against {reps} in the "
        f"filename label")


# ------------------------------------------------------------ template size --
# Measured 2026-07-31 on bench_90x4_1, sweeping `half` with the seed fixed.
# A real bench ROM is ~29 cm; only the last two are one.
TEMPLATE_SWEEP = {48: 16.8, 40: 22.4, 32: 30.9, 24: 31.0}


def test_a_template_larger_than_the_plate_anchors_to_the_gym():
    """The finding most likely to regress silently, pinned as a measurement.

    `track`'s default `half=48` makes a 97x97 px template. A bench plate is
    r~48 px, whose inscribed square has a half-width of 31 — so at 48 the
    template corners hold static ceiling, and the tracker part-anchors to the
    room. It still reports a high NCC while doing it, which is why no quality
    score catches this and why the symptom is TRAVEL:

        half = 48 -> 16.8 cm      half = 32 -> 30.9 cm
        half = 40 -> 22.4 cm      half = 24 -> 31.0 cm

    Against a real bench ROM of ~29 cm. `truth.template_half` exists to pick
    the inscribed half-width from the seed radius for this reason.

    Deadlift deliberately keeps `half=48`: no deadlift is in `SEEDS`, so
    `bar_path` never calls `template_half` for one, and moving it would move
    every A3 number pinned in test_real_data.py. Whether it would help is
    untested and is a lead, not a finding.
    """
    video = "bench_90x4_1_20260727"
    if not _has(video):
        pytest.skip(f"{video} not present")
    from src import truth

    frame, cy, cx, radius = truth.SEEDS[video]
    got = {}
    for half in TEMPLATE_SWEEP:
        path = truth.bar_path(VIDEO / f"{video}.mov", seed_yx=(cy, cx),
                              seed_radius=radius, half=half, check=False)
        h = path["height"][np.isfinite(path["height"])]
        got[half] = float(h.max() - h.min()) * 100

    assert got[48] < got[32], (
        f"a template larger than the plate no longer under-reads travel: "
        f"{got[48]:.1f} cm at half=48 against {got[32]:.1f} at half=32")
    assert got[32] > 28.0 and got[24] > 28.0, (
        f"an inscribed template no longer recovers a bench ROM: {got}")
    assert truth.template_half(radius) <= radius / np.sqrt(2)


# ------------------------------------------------- find_plate, in-frame only --
@pytest.mark.parametrize("video", ["squat_140x4_3_20260730", "squat_160x1_20260730"])
def test_a_disc_hanging_off_the_frame_edge_cannot_win(video):
    """Refuse in a sentence naming the fault, not a numpy broadcast error.

    `find_plate` used `fftconvolve(mode="same")`, which zero-pads, so a disc
    centred near the frame edge is scored against blackness and **wins for
    being half outside the picture** — r=108 centred 12, 16 and 38 px from the
    left edge of a 180 px frame. `track` then sliced with a negative start,
    numpy wrapped it, the template came back empty, and `ncc_map` died on a
    broadcast mismatch. Three of the four 2026-07-30 squat videos failed that
    way.

    What the fix bought is precise, and less than it first appeared. It did NOT
    make these captures trackable: the plate still clips frame at lockout, so
    two of the four still refuse and two report ~12.5 cm of travel for a lift
    whose band is 45-76 cm. It converted a crash into an honest refusal. That
    is worth having and it is not truth — squat still needs a wider shot, not
    code, and `metrics.vs_truth` refuses it.
    """
    if not _has(video):
        pytest.skip(f"{video} not present")
    from src import truth

    with pytest.raises(ValueError) as e:
        truth.bar_path(VIDEO / f"{video}.mov")
    assert "broadcast" not in str(e.value), (
        "the in-frame constraint has regressed: this is the raw numpy error "
        "again, not a message naming the fault")

"""
The pipeline variant for sets too short for the periodic machinery. G3.

WHAT IS ACTUALLY BROKEN, MEASURED BEFORE ANYTHING WAS BUILT
-----------------------------------------------------------
Three captures in `data_v2/` have never been refereed, and they are exactly the
three SINGLES — `bench_117.5x1`, `deadlift_200x1`, `squat_170x1`, one per lift.
It is worth being precise about where they fail, because the obvious guess is
wrong:

**They segment correctly.** `segment.rep_bounds` gets 1/1 on all three, with
windows G1 checked against video. Truncating each of the thirteen multi-rep
captures down to its first rep gives thirteen more singles whose answer is
known from the full capture, and the segmenter gets 1/1 on all thirteen too,
with windows overlapping the full capture's first rep at IoU 0.53-0.99.

**They fail in the SYNC**, and for two different reasons. `metrics.bench_sync`
refuses outright without a cadence — it accepts on the rule "every rival
alignment is a whole rep away", and a capture with one rep has no rep period to
measure that against. The deadlift route never reaches it: `_video_on_imu_clock`
sends deadlift to `capture.sync`, which fits offset AND slope and therefore
needs two landings against two impacts, and a single provides one of each.

So this module replaces the clock, not the segmenter. Steps 0-9 are
`pipeline.run` unchanged.

THE OWNER'S PRIOR, AND WHY IT IS NOT WHAT SHIPPED
-------------------------------------------------
The task came with a proposed rule for singles: *find the part of the recording
with maximum displacement with IMU dwells on either side.* It was implemented
and measured against the sixteen singles above, in three readings, and all three
lose to the segmenter that already exists:

    rule                                        median IoU   IoU >= 0.5
    dwell = stationary_mask, duration-capped        0.00        1/13
    dwell = vertical-velocity turnaround            0.31        3/13
    candidates from _all_lobes, max displacement    0.00        2/13
    `segment.rep_bounds` as it stands               0.70       13/13

The reason is one number: **integration drift produces more apparent
displacement than a rep does.** On `bench_92.5x6_1` the window the rule selects
claims 86.8 cm of vertical travel on a bench press whose true range is 27 cm.
Drift grows with window length, so "maximum displacement" is a criterion that
systematically prefers the longest admissible window rather than the rep, and no
choice of dwell threshold repairs that — the ordering is wrong, not the cut.
The strict-stationarity reading has a second, independent failure: a deadlift
has no pair of stationary runs within a rep's length of each other at all
(the wrist is quiet before the set and after it, and nowhere between), so on all
six deadlift singles the rule returns nothing to rank.

Recorded rather than deleted, because the idea is a reasonable one and the
measurement is the only thing that says otherwise. **Do not re-propose
displacement as a selection rule without first removing the drift** — on a
drift-free position estimate it would very likely work, which is exactly why it
looks right on paper.

What survives of the prior, and it survives load-bearing: the *dwells* are real
and the module uses them. They are just used to check a clock rather than to
choose a window.

WHAT SHIPPED: ONE MECHANISM FOR SINGLES AND DOUBLES
----------------------------------------------------
The prior expected doubles to work like the existing pipeline and singles to
need something else. Measured, that is half right — doubles DO mostly work
through the existing route — but the split is not worth keeping, because the
same correlation handles both and handles doubles BETTER:

    thirteen synthetic doubles        answers   refused   error range
    existing `_video_on_imu_clock`       9         4       0-27 ms
    `short_sync` below                  13         0       2-23 ms

The four refusals are not a deep problem and are worth naming: two are
`bench_sync`'s fractional-rival guard firing on a two-rep set (with one gap
there is barely a cadence to be a multiple of), and two are `capture.landings`,
whose `skip_s=10.0` discards any landing in the first ten seconds — on a short
record that is the landing.

**DEADLIFT DOUBLES ARE NOT VALIDATED END TO END, and the reason is the
instrument rather than the pipeline.** Bench and squat doubles are: all seven
segment 2/2 and sync to 0-15 ms. Of the six deadlift doubles only two segment
2/2 — but a truncated deadlift double is not a fair test of one, because
**a deadlift set has no gap between reps at all.** Its rep windows run impact to
impact and the measured gap between rep 2's end and rep 3's start is 0.00 s on
all six captures, so cutting after rep 2 ends the record exactly at the second
landing, with zero trailing record. A real deadlift double ends with the lifter
releasing the bar and stepping back. Nothing that can be cut from a continuous
four-rep set looks like that, and lengthening the margin does not help — it was
swept from 0.5 to 0.98 of the (zero) gap and the counts do not move.

So the honest state of doubles is: **bench and squat, validated; deadlift,
sync-validated only where segmentation happens to succeed, and awaiting a real
capture.** A deadlift double is the single most useful capture anyone could add
to this corpus.

THE ONE THING THAT CHANGES: THE SWEEP IS BOUNDED BY OVERLAP, NOT BY LAG
-----------------------------------------------------------------------
`bench_sync` widens its sweep until the peak is interior, because on a long set
the true lag can sit 7 s out. Run that on a single and it is a disaster:

    deadlift_200x1, sweep half-width    peak      error vs the floor impact
      6.00 s                          -0.355 s          +11 ms
     11.75 s (the shipping constant)  -10.820 s      -10454 ms
     20.00 s                          -17.455 s      -17089 ms

and the wrong answers score HIGHER (0.490 and 0.642 against the true peak's
0.335). That is not a defect in the search; it is the signal. A single is a flat
record with one event in it, so sliding the two records far apart correlates
flat against flat, on ever less of it, and noise wins. `bench_sync`'s own
docstring makes the argument in the other direction — *the non-rep time is what
breaks the degeneracy* — and this is what happens when you throw that time away.

So the sweep is bounded by requiring the two records to keep overlapping:
a lag is scored only where they still share `MIN_OVERLAP_FRAC` of the shorter
one. That is a statement about what identifies the lag rather than a tuned
window, and it makes the ceiling a property of the two recordings.

Measured over the sixteen singles, the floor is a plateau and not a point:

    MIN_OVERLAP_FRAC   answered   silently wrong
        0.50-0.60          3            0
        0.70               6            1
        0.75              12            1
        0.80-0.95         13            1

Everything from 0.80 up gives the same thirteen answers. Below 0.75 it starts
refusing correct captures. `0.80` is the low edge of the flat region, taken
deliberately rather than the middle: the failure mode this floor exists to stop
gets *worse* as the floor drops, so the conservative edge is the informative
one. The single "silently wrong" entry at every setting is `deadlift_170x4_3`,
and it is not what it looks like — see below.

HOW ACCURATE, AND AGAINST WHAT
------------------------------
Sixteen singles, thirteen of them carrying a known answer from the full capture
they were cut from and one (`deadlift_200x1`) carrying an independent one from
its own floor impact matched to the video's landing:

    lift        n   error against the known offset
    bench       4   +5, +10, +15, +30 ms
    squat       3   -1.7, +1.9, +5.0 ms
    deadlift    6   -1.6, +3.3, +16.5, +27.0, +103.9 ms, and one excluded
    deadlift    1   +10.9 ms   (deadlift_200x1, the real single)

For scale, the multi-rep deadlift sync — the best-validated clock in this
project — runs an 8.4-9.7 ms residual on the same corpus, and `bench_sync`'s
deadlift control recovers a known offset to 3-18 ms. This is the same order.

**The excluded capture is excluded because its REFERENCE is broken, and that is
a finding about the main pipeline rather than about this module.**
`deadlift_170x4_3`'s full-capture sync fits a slope of 0.7715 — a 22.8% clock
drift with a 216 ms residual, where every other deadlift sits at under 0.4% and
about 9 ms. Clocks do not drift 23%, nothing in the pipeline gates on
`drift_pct` or `rms_ms`, and that capture is currently scored through it. Two
independent estimates disagree with it and agree with each other to 25 ms: this
module's correlation says -0.627 s and its own single landing matched to its own
single impact says -0.652 s, against the four-point fit's -1.505 s. Reported to
the owner; deliberately NOT patched here, since `capture.sync` is not this
module's to change and the right fix is a gate, not a special case.

WHAT IT ACCEPTS ON
------------------
Not the height of the peak — `bench_sync` records at length why peak height
mostly measures what fraction of a clip contains lifting, and short sets make
that worse rather than better. Two checks instead, and the first is the one
doing the work.

*Containment.* Applied to the video, the offset must put the video's single
largest excursion INSIDE the IMU's rep window. This is the check a single makes
available that a long set does not: there is one movement in each record and no
periodicity to alias it against, so pairing them is unambiguous. Measured, all
sixteen singles land at phase 0.44-0.88 through their window. It is a coarse
gate — it bounds the gross error at roughly a rep — and it is paired with a
correlation good to tens of milliseconds, which is the right division of labour:
the landmark excludes the big error, the correlation supplies the precision.

*A landmark, where the lift provides one.* A deadlift single has a floor impact
and the video has a landing; they are the same physical event seen by unrelated
sensors, so they give an offset outright. Where both exist they agree with the
correlation to 3-104 ms. This is the deadlift analogue of what G2 did for
paused bench and squat, at n=1: the offset is available, the SLOPE is not, so
drift is assumed rather than measured and `drift_pct` reads NaN to say so.

**`segment.dwell_instants` was tried as the bench and squat landmark and it does
NOT generalise to singles.** It agrees to 19.7-295.7 ms on the synthetic
singles cut from paused captures and misses by -842.6 and +616.2 ms on the two
real ones — because `bench_117.5x1` and `squat_170x1` are not paused lifts, so
there is no dwell in the rep interior for it to find and it returns an arbitrary
instant. G2's landmark is a landmark for PAUSED sets, which is what it was
measured on and what it should stay. Containment is what covers the rest.

WHAT THIS DOES NOT DO, STATED SO IT IS NOT ASSUMED
---------------------------------------------------
It does not measure clock drift. One event fits one number; `slope` is 1.0 by
assumption and `drift_pct` and `rms_ms` are NaN, on the same principle
`bench_sync` follows — a field that cannot be measured reads NaN rather than a
number from somewhere else. The multi-rep deadlifts put drift under 0.4%, which
over a 30 s capture is ~0.1 s, so the assumption is not free and it is the
largest unquantified term here.

It does not make a single's horizontal number trustworthy. It makes the capture
scoreable, which is a precondition for judging it and nothing more. Everything
`vs_truth` says about P2 and P3 applies to these captures exactly as it does to
the rest, and with one rep there is no dispersion at all.

It is not wired into the default path. `metrics.vs_truth` and
`_video_on_imu_clock` take a `sync=` hook that defaults to None, which is the
existing behaviour; `shortset.run` passes this module's. All thirteen multi-rep
captures are gated bit-identical with the hook absent, so nothing that is
currently scored can move.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import capture, metrics, pipeline, segment

# What counts as short. Above this the periodic machinery has a cadence to work
# with and there is no reason to prefer this route — measured, the two agree to
# 0-27 ms on two-rep sets, and the existing one carries far more validation.
SHORT_SET_MAX_REPS = 2

# The fraction of the shorter record that must still overlap for a lag to be
# scored. THE central constant here; see the module docstring for the plateau it
# sits on (0.80-0.95 all give the same thirteen answers) and for what happens
# below it. Taken at the LOW edge of the plateau on purpose: the failure this
# guards against grows as the floor falls, so the conservative edge is the one
# that carries information.
MIN_OVERLAP_FRAC = 0.80

# How far outside its rep window the video's largest excursion may fall before
# the sync is refused, as a fraction of the window. Measured, all sixteen
# singles land at 0.44-0.88, so 0.0-1.0 would already pass every real capture;
# the margin is here because a rep window's edges are a segmentation choice and
# this gate should fail on a WRONG CLOCK rather than on a window trimmed a
# little tight. A whole-rep error moves the peak by ~1.0 and is caught either
# way — see tests/test_shortset.py, which injects exactly that.
CONTAINMENT_TOL = 0.25

# How far the correlation and an independent landmark may disagree. Not a
# fraction of a rep, as in `metrics.LANDMARK_TOL_REPS`, because a single has no
# cadence to take a fraction of. Measured, the impact landmark and the
# correlation agree to 3-104 ms across every deadlift that has both.
LANDMARK_TOL_S = 0.30


def is_short(bounds: list) -> bool:
    """Is this a set this module is for?"""
    return 0 < len(bounds) <= SHORT_SET_MAX_REPS


def video_excursion(path: dict) -> tuple[float, float]:
    """(time, size) of the largest departure from the bar's resting height.

    The one event in a short capture. Measured against the MEDIAN height rather
    than against the mean or an endpoint, because the bar is motionless for most
    of a single's clip — 0-16 s in the rack on `bench_117.5x1`, 0-15 s on the
    floor on `deadlift_200x1`, 0-31 s racked on `squat_170x1` — so the median IS
    the resting height, robustly, and no smoothing or thresholding is needed to
    find it.
    """
    t = np.asarray(path["t"], dtype=float)
    h = np.asarray(path["height"], dtype=float)
    ok = np.isfinite(h)
    if ok.sum() < 10:
        return float("nan"), float("nan")
    dev = np.where(ok, np.abs(h - np.median(h[ok])), 0.0)
    k = int(np.argmax(dev))
    return float(t[k]), float(dev[k])


def containment(path: dict, log: dict, bounds: list, offset: float) -> float:
    """Where the video's excursion lands in the rep window, as a phase.

    0 is the window's start and 1 its end, so a value outside [0, 1] means the
    clock has put the video's only real movement outside the only window the IMU
    found. Returns NaN when either record cannot supply its event.

    This is the check a SHORT set makes available and a long one does not.
    `metrics.bench_sync` is explicit that a whole-rep ambiguity is harmless for
    the two quantities it was weighed against and destroys anything that PAIRS a
    video rep with an IMU window — but with one rep in each record the pairing is
    forced, so the pairing becomes evidence instead of a casualty.
    """
    t_v, _ = video_excursion(path)
    if not np.isfinite(t_v) or not bounds:
        return float("nan")
    t = log["t"]
    # The span of ALL the windows, not the first one. On a single those are the
    # same thing; on a DOUBLE they are not, and using the first window alone
    # refused correct two-rep syncs whenever the larger of the two excursions
    # happened to be the second rep — which is a coin flip. `video_excursion`
    # returns the biggest movement in the record, so the thing it must land
    # inside is the record's whole lifting span.
    lo = float(t[bounds[0][0]])
    hi = float(t[min(bounds[-1][1], len(t) - 1)])
    if hi <= lo:
        return float("nan")
    return float((t_v + offset - lo) / (hi - lo))


def impact_landmark(path: dict, log: dict,
                    impacts: list[int] | None = None) -> float | None:
    """Offset from floor impacts matched to video landings, without a slope.

    `capture.sync` fits offset and slope together and so needs two of each; this
    is the same match with the slope assumed, which is what a single can support.
    Returns None when the two counts disagree — a mismatch means one record saw
    an event the other did not, and pairing them in order would then align the
    wrong pair.

    `skip_s=0.0` deliberately. `capture.landings` defaults to discarding the
    first ten seconds, which is right for a full set filmed from a standing
    start and wrong for a short record, where ten seconds is most of the clip
    and often contains the only landing — it is why two of the thirteen
    synthetic doubles could not sync at all through the existing route.

    **Returns the offset in the `bench_sync` convention: video t + offset = IMU
    t.** That is the opposite sign to `capture.sync`, which fits
    video = slope * imu + offset. Both are documented in their own modules and
    they disagree; anything comparing the two must normalise first, and this
    function exists partly so that only one place has to know.
    """
    if impacts is None:
        impacts = segment.impact_anchors(log)
    landings = capture.landings(path, skip_s=0.0)
    if not len(impacts) or len(landings) != len(impacts):
        return None
    t = log["t"]
    return float(np.mean([float(t[k]) - float(v)
                          for k, v in zip(impacts, landings)]))


def short_sync(path: dict, log: dict, velocity_z: np.ndarray,
               bounds: list, impacts: list[int] | None = None,
               min_overlap_frac: float = MIN_OVERLAP_FRAC) -> dict:
    """Align a short capture's video to the IMU clock. Offset only.

    Same correlation as `metrics.bench_sync` — band-passed vertical bar velocity
    against the reconstruction's — with the cadence precondition removed and the
    sweep bounded by overlap instead of by lag. Read this module's docstring for
    why that swap is the whole point rather than a detail.

    Raises `ValueError` rather than returning a bad offset, on the same
    principle as everything else in this project that syncs: a wrong clock
    produces a confident number nobody can tell is wrong.
    """
    t_v = np.asarray(path["t"], dtype=float)
    ok = np.isfinite(np.asarray(path["height"], dtype=float))
    if ok.sum() < 100:
        raise ValueError("short sync: the video track is too sparse to correlate")

    lo, hi = float(t_v[ok][0]), float(t_v[ok][-1])
    grid = np.arange(lo, hi, 1.0 / metrics.SYNC_FS)
    v_video = metrics._band(np.gradient(
        np.interp(grid, t_v[ok], capture._smooth(path["height"], 9)[ok]), grid))

    t_i = np.arange(float(log["t"][0]), float(log["t"][-1]), 1.0 / metrics.SYNC_FS)
    v_imu = metrics._band(np.interp(t_i, log["t"], velocity_z))

    # The overlap floor, in seconds of the SHORTER record. Taking the shorter one
    # matters: a 20 s clip against a 45 s log can never share 80% of the log, and
    # requiring it would refuse every squat single in the corpus.
    span = min(hi - lo, float(t_i[-1] - t_i[0]))
    need = min_overlap_frac * span

    # Sweep as far as the records can slide while still meeting the floor. This
    # is a property of the two recordings rather than a constant, which is the
    # point — there is no lag window to tune and none to get wrong.
    reach = max(abs(t_i[0] - hi), abs(t_i[-1] - lo))
    lags = np.arange(-reach, reach, 1.0 / metrics.SYNC_FS)
    curve = np.full(len(lags), np.nan)
    for j, lag in enumerate(lags):
        g = grid + lag
        m = (g >= t_i[0]) & (g <= t_i[-1])
        if m.sum() < need * metrics.SYNC_FS:
            continue
        a = v_video[m] - v_video[m].mean()
        b = np.interp(g[m], t_i, v_imu)
        b = b - b.mean()
        curve[j] = a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)

    if not np.isfinite(curve).any():
        raise ValueError(
            f"short sync: no lag lets these two records share "
            f"{min_overlap_frac:.0%} of the shorter one ({span:.1f} s), so "
            f"there is no alignment worth scoring. The clip and the log may not "
            f"cover the same set")

    pk = int(np.nanargmax(curve))
    corr, lag = float(curve[pk]), float(lags[pk])

    rivals = []
    for i in range(1, len(curve) - 1):
        if not np.isfinite(curve[i]) or abs(lags[i] - lag) <= metrics.RIVAL_GUARD_S:
            continue
        if (curve[i] >= curve[i - 1] and curve[i] >= curve[i + 1]
                and curve[i] >= metrics.RIVAL_FRAC * corr):
            rivals.append((float(lags[i]), float(curve[i] / corr)))

    fit = {
        "method": "short set: vertical cross-correlation bounded by overlap",
        "offset": lag,          # video t + offset = IMU t
        "corr": corr,
        "rivals": rivals,
        "slope": 1.0,           # assumed, not fitted. See the module docstring.
        "drift_pct": float("nan"),
        "rms_ms": float("nan"),
        "n": 1,
        "overlap_frac": float(min_overlap_frac),
        "n_reps": len(bounds),
        "lags": lags,           # diagnostic, as in bench_sync: this accepts on
        "curve": curve,         # a shape, so the shape should be inspectable
    }

    # --- the two acceptance checks ------------------------------------------
    phase = containment(path, log, bounds, lag)
    fit["containment_phase"] = phase
    if np.isfinite(phase) and not (-CONTAINMENT_TOL <= phase <= 1.0 + CONTAINMENT_TOL):
        raise ValueError(
            f"short sync refused: the offset {lag:+.3f} s puts the video's "
            f"largest bar movement at phase {phase:+.2f} of the IMU's rep "
            f"window, outside the permitted "
            f"{-CONTAINMENT_TOL:+.2f}..{1 + CONTAINMENT_TOL:+.2f}. Each record "
            f"holds exactly one movement, so they must be the same one; a clock "
            f"that separates them is wrong by about a rep, and every per-rep "
            f"number measured through it would pair the wrong things")

    mark = impact_landmark(path, log, impacts)
    fit["landmark_offset"] = float("nan") if mark is None else mark
    if mark is not None:
        fit["landmark_disagree_s"] = abs(mark - lag)
        if abs(mark - lag) > LANDMARK_TOL_S:
            raise ValueError(
                f"short sync refused: the correlation puts the video "
                f"{lag:+.3f} s from the IMU clock and the floor impact matched "
                f"to the video's landing puts it {mark:+.3f} s, a disagreement "
                f"of {abs(mark - lag) * 1000:.0f} ms against a "
                f"{LANDMARK_TOL_S * 1000:.0f} ms tolerance. These are the same "
                f"physical event seen by unrelated sensors and they should not "
                f"disagree; one of the two detections is on the wrong event")
    else:
        fit["landmark_disagree_s"] = float("nan")

    return fit


def truncate_capture(csv: str | Path, bounds: list, t: np.ndarray, keep: int,
                     dest: str | Path, margin_s: float = 4.0):
    """Cut a capture down to its first `keep` reps. Returns (path, cut time).

    **The corpus cannot test this module without this.** There are three real
    singles, only one of which carries an independent offset, and there are no
    real doubles at all — so the only way to ask "does a short set recover the
    right answer" thirteen more times is to manufacture short sets from the
    multi-rep captures, where the full capture already supplies the answer.

    Two choices in here are load-bearing rather than incidental:

    *Keep the HEAD of the record, not a slice out of the middle.* The pre-set
    quiet window is what `calibrate.gyro_bias` estimates from, and it is also
    what a real single actually looks like — `squat_170x1` stands racked for
    31 of its 45 seconds. A middle slice would test a capture shape that does
    not occur and would fail for a reason that says nothing.

    *Stop half-way into the following gap.* Cutting a fixed `margin_s` after the
    last kept rep leaks the next rep's start in, and the segmenter then counts
    it — which shows up as a segmentation failure and is really a harness bug.
    That happened, and it cost a full round of measurement before it was caught.

    What it does NOT reproduce, so results from it are not oversold: a truncated
    single has no trailing re-rack and no walk-away, and its rep occupies a much
    larger fraction of the record than a real single's does. It is the harder
    case for the overlap floor and the easier case for containment.
    """
    csv, dest = Path(csv), Path(dest)
    if keep > len(bounds):
        return None
    end = float(t[bounds[keep - 1][1]])
    if keep < len(bounds):
        end += min(margin_s, 0.5 * (float(t[bounds[keep][0]]) - end))
    else:
        end += margin_s
    t_cut = min(end, float(t[-1]))
    cut_i = int(np.searchsorted(t, t_cut))

    lines = csv.read_text().splitlines()
    # Renamed so `pipeline.expected_reps` reports the TRUNCATED count; the
    # weight is nonsense on purpose, so nobody mistakes one of these for a
    # capture. Rows are copied verbatim rather than re-encoded — a truncation
    # that also changed the numbers would not be a truncation.
    out = dest / f"{csv.name.split('_')[0]}_999x{keep}_{csv.stem}.csv"
    out.write_text("\n".join([lines[0]] + lines[1:cut_i + 1]) + "\n")
    return out, t_cut


def sync(result: dict, path: dict) -> dict:
    """The `sync=` hook `metrics._video_on_imu_clock` accepts.

    Returns a fit dict for a short set and returns None for anything longer,
    which tells the caller to use its own route. Written this way so that
    turning the variant on cannot change what happens to a capture it is not
    for — the thirteen multi-rep captures take the identical path with the hook
    installed and without it, and `tests/test_shortset.py` pins that.
    """
    if not is_short(result.get("bounds", [])):
        return None
    return short_sync(path, result["log"], result["velocity"][:, 2],
                      result["bounds"], result.get("impacts"))


def run(path: str | Path, video: str | Path | dict | None = None,
        wrist_offset: np.ndarray | str | None = "auto",
        tracker: str | None = None) -> dict:
    """The nine steps, then A3 with a clock a short set can actually supply.

    Steps 0-9 are `pipeline.run` and are not touched — this variant is about the
    referee, because that is where the measurement said the singles fail. On a
    capture of three reps or more this is `pipeline.run` exactly, including the
    `vs_truth` refusals, so it is safe to point at a whole directory.
    """
    result = pipeline.run(path, wrist_offset=wrist_offset)
    result["short_set"] = is_short(result["bounds"])

    if video is None:
        video = pipeline.find_video(path)
    if video is None:
        return result

    try:
        result["vs_truth"] = metrics.vs_truth(result, video, tracker=tracker,
                                              sync=sync)
    except (ValueError, FileNotFoundError) as e:
        result["blocked"].append(f"A3 vs_truth: {e}")
    return result

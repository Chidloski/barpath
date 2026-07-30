"""
A3 — error metrics on real captures.

This module exists because of a specific failure. Milestones 1-6 all passed and
the pipeline was unusable in the gym, and the reason it could happen is that
nothing in the repo measured error. Every stage was judged by whether its own
output looked reasonable, which is exactly the judgement that had already been
fooled once. `tests/test_real_data.py.horizontal_residual` is the closest thing
that existed and its own docstring disclaims it: it tiles 2 s windows and
detrends each, so it conflates real bar movement with error and can only rank
two pipelines against each other.

B2, B3 and B6 are all of the form "change the error model and see whether it
helped". None of them can start without this.

Two metrics, and the difference between them is the whole point.

`dispersion` needs no truth. It measures rep-to-rep spread, which is what
CLAUDE.md says the product is actually about — a path systematically 1.5 cm
forward of truth is fine if it is consistently so.

`vs_truth` needs the video (A2) and measures absolute error against it.

**You need both, and dispersion alone will lie to you.** CLAUDE.md's spec
section spells out why: the "it's common-mode, so it cancels" argument holds
for error that is constant across a set, and fails for error correlated with
the motion. P3 is the second kind — body-frame accel bias projected through a
rotating forearm lands at rep frequency, so it repeats with the rep and the
rep-to-rep comparison preserves it perfectly. A pipeline dominated by P3 scores
*well* on dispersion. Do not report a dispersion number without saying so.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import correct, project, segment, truth

GRID = 100          # samples per rep on the normalised-time grid


# ------------------------------------------------------------- dispersion --
def _resample(rep: np.ndarray, n: int = GRID) -> np.ndarray:
    """One rep onto `n` points of normalised time. See dispersion's caveat."""
    u = np.linspace(0.0, 1.0, len(rep))
    grid = np.linspace(0.0, 1.0, n)
    return np.column_stack([np.interp(grid, u, rep[:, k]) for k in range(3)])


def dispersion(reps: list[np.ndarray], t: np.ndarray | None = None,
               bounds: list[tuple[int, int]] | None = None,
               n: int = GRID) -> dict:
    """Rep-to-rep spread after start alignment, in cm.

    `reps` is what `correct.detrend_set` returns: a list of (M_i, 3) arrays,
    already aligned so each starts at the origin, and of differing lengths.
    Pass `t` and `bounds` as well to get the tempo diagnostic described below.

    What this measures, and what it cannot
    --------------------------------------
    Deviation of each rep from the set's mean rep, at matched phase. This is
    the closest thing to the product: CLAUDE.md says what matters is
    rep-to-rep difference, not absolute truth.

    It is blind to any error that repeats identically every rep. That is not a
    corner case here — it is P3, the dominant suspect for the horizontal
    failure. Body-frame accelerometer bias projected through a rotating forearm
    varies at REP FREQUENCY, so it lands in the mean rep and subtracts out of
    every deviation from it. A pipeline that is wrong by a metre in a way that
    repeats will report excellent dispersion. Read `vs_truth` before believing
    a good number here.

    The judgement this encodes, and what falsifies it
    ------------------------------------------------
    Reps are compared at the same FRACTION of the rep, not at the same bar
    height and not at the same elapsed time. That conflates tempo variation
    with path variation: a rep performed slower traces the same path and still
    registers deviation, because its phase points land elsewhere.

    The alternative is to compare at matched bar height, which is what the
    overlaid plot shows and what a lifter is actually looking at — but it needs
    the concentric and eccentric split apart to stay monotonic, so it is more
    machinery than this warrants until the confound is shown to bite.

    `tempo_corr` is what would falsify the choice. It correlates each rep's
    deviation magnitude against how far that rep's duration sits from the set
    median. If it comes out strongly positive, the metric is largely measuring
    tempo and should move to matched height.

    Returns cm throughout:
        horizontal_rms, horizontal_p95   deviation magnitude in the xy plane
        vertical_rms, vertical_p95       signed z deviation, absolute
        per_axis_rms                     (3,) x, y, z separately
        worst_rep                        index of the rep furthest from the mean
        durations_s, tempo_corr          the falsification diagnostic
    """
    if len(reps) < 2:
        raise ValueError(f"dispersion needs at least 2 reps, got {len(reps)}")

    stack = np.stack([_resample(r, n) for r in reps])       # (K, n, 3)
    dev = stack - stack.mean(axis=0)                        # (K, n, 3)

    horizontal = np.linalg.norm(dev[:, :, :2], axis=2)      # (K, n)
    vertical = np.abs(dev[:, :, 2])

    out = {
        "n_reps": len(reps),
        "horizontal_rms": float(np.sqrt((horizontal ** 2).mean()) * 100),
        "horizontal_p95": float(np.percentile(horizontal, 95) * 100),
        "vertical_rms": float(np.sqrt((vertical ** 2).mean()) * 100),
        "vertical_p95": float(np.percentile(vertical, 95) * 100),
        "per_axis_rms": np.sqrt((dev ** 2).mean(axis=(0, 1))) * 100,
        "worst_rep": int(np.argmax(horizontal.mean(axis=1))),
    }

    if t is not None and bounds is not None:
        durations = np.array([t[min(b, len(t) - 1)] - t[a] for a, b in bounds])
        out["durations_s"] = durations
        spread = horizontal.mean(axis=1)
        d = np.abs(durations[:len(spread)] - np.median(durations))
        # None rather than a number, when a number would not mean anything: a
        # correlation over 3 or 4 reps is noise, and every rep running the same
        # length makes it a divide by zero. A set is 2-6 reps here, so even the
        # values this does report rest on very few points — treat a single
        # capture's tempo_corr as a hint and look across captures.
        if len(d) >= 5 and d.std() > 1e-9 and spread.std() > 1e-9:
            out["tempo_corr"] = float(np.corrcoef(d, spread)[0, 1])
        else:
            out["tempo_corr"] = None

    return out


# ---------------------------------------------------------------- vs truth --
def _video_on_imu_clock(log: dict, video: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Tracked bar path resampled onto the IMU clock.

    Returns (t_imu, fore_aft, height, sync_fit), NaN samples dropped. The sync
    is the same route tests/test_real_data.py uses: the IMU's floor impacts and
    the video's landings are the same physical events seen by unrelated
    sensors, so matching them fits offset AND slope and measures clock drift
    rather than assuming it.
    """
    path = truth.bar_path(video)
    impacts = np.array([float(log["t"][k]) for k in segment.impact_anchors(log)])
    landings = truth.landings(path)

    if len(landings) < 2 or len(impacts) < 2:
        raise ValueError(
            f"cannot sync: {len(landings)} video landings against {len(impacts)} "
            f"IMU impacts, need >=2 of each")

    fit = truth.sync(landings, impacts)
    t_imu = truth.to_imu_time(path, fit)

    ok = np.isfinite(path["x"]) & np.isfinite(path["height"]) & np.isfinite(t_imu)
    return t_imu[ok], path["x"][ok], path["height"][ok], fit


def _close(arr: np.ndarray, t: np.ndarray,
           axes: tuple[int, ...] = (0, 1)) -> np.ndarray:
    """Subtract the endpoint-to-endpoint line, per column. Step 7's operation.

    Routed through correct.detrend_rep rather than reimplemented, so that when
    B3 changes what closure means this follows automatically — the point of
    applying it to the truth as well is to measure what step 7 does, and a
    private copy here would quietly stop measuring the real thing.

    `arr` is the 2-column video path (along-axis, vertical), so vertical is
    column 1 here where it is column 2 in the pipeline. If detrend_set is ever
    called with restricted axes, map them onto that layout here or this stops
    measuring the same operation.
    """
    return correct.detrend_rep(arr, 0, len(arr), t, axes=axes)


def vs_truth(result: dict, video: str | Path) -> dict:
    """Reconstructed rep paths against the video, in cm. Deadlift only.

    `result` is a `pipeline.run` dict. Deadlift only is not caution for its own
    sake — src/README.md's per-lift table puts squat at median NCC ~0.40 with
    the plate leaving frame at lockout, and bench raises without a hand-placed
    seed. Returning a number from either would be inventing the ground truth
    this module exists to supply, so it raises instead.

    Three errors per rep, and the gaps between them are the point
    -------------------------------------------------------------
    `raw` — neither side closed, start alignment only. Dominated by drift
    accumulated since the beginning of the capture: the bar position entering
    rep 5 is already metres out, and subtracting its value at the rep start
    does not remove the velocity error carried in with it. This is not a
    within-rep number and should not be read as one. It is here because it is
    what the integration alone produces, and it is why step 7 exists.

    `pipeline` — the reconstruction closed exactly as the pipeline ships it,
    the video untouched. **This is the honest product error.** It is the only
    one of the three that compares what the pipeline would draw against what
    the bar actually did, and it is the number the ~1 cm spec is about.

    `closed` — step 7's line subtracted from the VIDEO as well, so both sides
    carry the same constraint. Pure shape error, with the closure's cost
    removed from both sides.

    `pipeline` minus `closed` is therefore what the closure assumption costs,
    and `video_closure` measures its premise directly: how far the tracked bar
    is from ending each rep where it started. The owner has confirmed the
    deadlift bar does not land where it was pulled from, so a non-zero
    horizontal closure is real motion that step 7 destroys. That is B3's
    evidence, and the reason the truth is never quietly detrended into
    agreement and reported alone.

    The horizontal axis, and the sign
    ---------------------------------
    The video's fore-aft is a camera axis; the reconstruction's horizontal is
    world x/y with heading unknown until step 8. So the reps are projected onto
    `project.principal_axis`, whose eigenvector sign is arbitrary and currently
    unresolved (B4). Vertical needs none of this.

    The sign is chosen ONCE for the set, from the summed correlation against
    the video, and reported as `axis_flipped`. Once, deliberately: the axis is
    a per-set quantity and step 8 will resolve its sign per set, so letting
    each rep pick its own would measure something the pipeline cannot do — and
    would flatter the result, since a rep reconstructed mirrored would be
    silently corrected instead of counted as the error it is.

    `reps_disagreeing_on_sign` then reports how many reps would individually
    have preferred the other sign. That is not a knob; it is B4 evidence. A
    non-zero count means the reconstruction's fore-aft direction is not even
    self-consistent across one set, so no per-set sign convention can be right
    for all of it.
    """
    log, bounds, reps = result["log"], result["bounds"], result["reps"]
    name = Path(result["path"]).name

    if not name.startswith("deadlift"):
        raise ValueError(
            f"{name}: vs_truth is deadlift-only. Squat tracks at median NCC "
            f"~0.40 with the plate clipping frame at lockout, and bench does "
            f"not seed automatically — neither is truth. See src/README.md.")
    if not reps:
        raise ValueError(f"{name}: no reps to compare")

    t_vid, fore_aft, height, fit = _video_on_imu_clock(log, video)

    axis = np.real(project.principal_axis(reps)[0])
    raw_pos = result["bar_position"]
    t = log["t"]

    # Pass 1: build each rep's three curves, and accumulate the evidence for
    # the SET's axis sign. Nothing is compared yet.
    windows = []
    for k, (a, b) in enumerate(bounds):
        tt = t[a:b]
        if tt[0] < t_vid[0] or tt[-1] > t_vid[-1]:
            windows.append(None)
            continue

        # Truth, on the IMU's own sample times, start-aligned like the reps.
        vid = np.column_stack([np.interp(tt, t_vid, fore_aft),
                               np.interp(tt, t_vid, height)])
        vid = vid - vid[0]

        # Reconstruction. `reps[k]` is already closed and start-aligned by
        # correct.detrend_set; raw_pos is the same window before step 7.
        recon_raw = raw_pos[a:b] - raw_pos[a]
        rec = np.column_stack([recon_raw[:, :2] @ axis, recon_raw[:, 2]])
        rec = rec - rec[0]

        # As the pipeline ships it: step 7 applied to the reconstruction only.
        pipe = np.column_stack([reps[k][:, :2] @ axis, reps[k][:, 2]])
        pipe = pipe - pipe[0]

        agree = float(np.dot(pipe[:, 0] - pipe[:, 0].mean(),
                             vid[:, 0] - vid[:, 0].mean()))
        windows.append({"k": k, "tt": tt, "vid": vid, "rec": rec,
                        "pipe": pipe, "agree": agree})

    live = [w for w in windows if w is not None]
    if not live:
        raise ValueError(f"{name}: no rep window falls inside the video's coverage")

    # One sign for the whole set — see the docstring on why not per rep.
    flip = sum(w["agree"] for w in live) < 0
    disagreeing = sum((w["agree"] < 0) != flip for w in live)

    # Pass 2: apply that one sign, then measure.
    per_rep = []
    for w in windows:
        if w is None:
            per_rep.append({"rep": len(per_rep), "covered": False})
            continue
        k, tt, vid, rec, pipe = w["k"], w["tt"], w["vid"], w["rec"], w["pipe"]
        if flip:
            rec = rec * [-1, 1]
            pipe = pipe * [-1, 1]
        closed_vid = _close(vid, tt)

        def rms(a, b):
            return float(np.sqrt(((a - b) ** 2).mean()) * 100)

        per_rep.append({
            "rep": k,
            "covered": True,
            "raw_h_rms": rms(rec[:, 0], vid[:, 0]),
            "raw_v_rms": rms(rec[:, 1], vid[:, 1]),
            "pipeline_h_rms": rms(pipe[:, 0], vid[:, 0]),
            "pipeline_h_max": float(np.abs(pipe[:, 0] - vid[:, 0]).max() * 100),
            "pipeline_v_rms": rms(pipe[:, 1], vid[:, 1]),
            "pipeline_v_max": float(np.abs(pipe[:, 1] - vid[:, 1]).max() * 100),
            "closed_h_rms": rms(pipe[:, 0], closed_vid[:, 0]),
            "closed_v_rms": rms(pipe[:, 1], closed_vid[:, 1]),
            # B3's premise, measured: how far the real bar is from closing.
            "video_closure_h": float(abs(vid[-1, 0] - vid[0, 0]) * 100),
            "video_closure_v": float(abs(vid[-1, 1] - vid[0, 1]) * 100),
            "video_rom_cm": float((vid[:, 1].max() - vid[:, 1].min()) * 100),
            "video_fore_aft_cm": float((vid[:, 0].max() - vid[:, 0].min()) * 100),
        })

    good = [r for r in per_rep if r["covered"]]

    def med(key):
        return float(np.median([r[key] for r in good]))

    return {
        "capture": name,
        "n_reps": len(bounds),
        "n_compared": len(good),
        "sync_rms_ms": fit["rms_ms"],
        "sync_drift_pct": fit["drift_pct"],
        "axis_flipped": bool(flip),
        "reps_disagreeing_on_sign": int(disagreeing),
        "axis": axis,
        "per_rep": per_rep,
        "raw_h_rms": med("raw_h_rms"),
        "raw_v_rms": med("raw_v_rms"),
        "pipeline_h_rms": med("pipeline_h_rms"),
        "pipeline_h_max": med("pipeline_h_max"),
        "pipeline_v_rms": med("pipeline_v_rms"),
        "pipeline_v_max": med("pipeline_v_max"),
        "closed_h_rms": med("closed_h_rms"),
        "closed_v_rms": med("closed_v_rms"),
        "video_closure_h": med("video_closure_h"),
        "video_closure_v": med("video_closure_v"),
        "video_rom_cm": med("video_rom_cm"),
        "video_fore_aft_cm": med("video_fore_aft_cm"),
        # The referee, checked against the same table as the reconstruction.
        # Non-empty means this capture's video vertical scale is wrong and its
        # vertical numbers — video_rom_cm, pipeline_v_rms, raw_v_rms — carry it.
        # Horizontal and sync are not implicated. See truth.VERTICAL_ROM_M.
        "video_rom_flags": truth.rom_flags(
            truth.lift_of(name), [r["video_rom_cm"] / 100 for r in good]),
    }


# ------------------------------------------------------------------ report --
def summary(disp: dict | None = None, truth_result: dict | None = None) -> str:
    """The metrics, as text for pipeline.summary. Carries its own caveats."""
    lines: list[str] = []

    if disp is not None:
        lines.append(
            f"  dispersion  horizontal {disp['horizontal_rms']:.1f} cm rms "
            f"(p95 {disp['horizontal_p95']:.1f}), vertical "
            f"{disp['vertical_rms']:.1f} cm rms, {disp['n_reps']} reps")
        tc = disp.get("tempo_corr")
        if tc is not None and abs(tc) > 0.7:
            lines.append(
                f"  CAVEAT  dispersion correlates {tc:+.2f} with rep duration — "
                f"it is measuring tempo as much as path. Compare at matched bar "
                f"height instead; see the docstring.")
        lines.append(
            "  CAVEAT  dispersion cannot see error that repeats every rep, "
            "which is what P3 is. A good number here is not a working pipeline.")

    if truth_result is not None:
        r = truth_result
        lines.append(
            f"  vs video    {r['n_compared']}/{r['n_reps']} reps, sync "
            f"{r['sync_rms_ms']:.0f} ms, video ROM {r['video_rom_cm']:.0f} cm / "
            f"fore-aft {r['video_fore_aft_cm']:.1f} cm")
        if r.get("video_rom_flags"):
            lines.append(
                f"    FLAGGED  the VIDEO fails the ROM bound on "
                f"{len(r['video_rom_flags'])}/{r['n_compared']} reps "
                f"({r['video_rom_flags'][0]}). Its vertical scale is wrong on "
                f"this capture, so every vertical number below is measured "
                f"against a bad ruler and must not be quoted unqualified. "
                f"Horizontal and sync are unaffected; see truth.VERTICAL_ROM_M.")
        lines.append(
            f"    AS SHIPPED  horizontal {r['pipeline_h_rms']:.1f} cm rms / "
            f"{r['pipeline_h_max']:.1f} cm max, vertical "
            f"{r['pipeline_v_rms']:.1f} cm rms / {r['pipeline_v_max']:.1f} cm max"
            f"   <- the spec is 1 cm horizontal")
        lines.append(
            f"    no closure  horizontal {r['raw_h_rms']:.0f} cm, vertical "
            f"{r['raw_v_rms']:.0f} cm   (drift since the capture began; why "
            f"step 7 exists)")
        lines.append(
            f"    shape only  horizontal {r['closed_h_rms']:.1f} cm, vertical "
            f"{r['closed_v_rms']:.1f} cm   (step 7 applied to the video too)")
        lines.append(
            f"    the real bar misses closing by {r['video_closure_h']:.1f} cm "
            f"horizontally, {r['video_closure_v']:.1f} cm vertically — step 7 "
            f"forces that to zero, so it is destroying real motion (B3)")
        if r["axis_flipped"]:
            lines.append(
                "  NOTE  the PCA axis pointed backwards and was flipped to "
                "match the video — project.principal_axis does not resolve "
                "its sign (B4), so the drawn path would have been mirrored")
        if r["reps_disagreeing_on_sign"]:
            lines.append(
                f"  NOTE  {r['reps_disagreeing_on_sign']}/{r['n_compared']} reps "
                f"individually favour the OPPOSITE fore-aft sign — the "
                f"reconstruction is not self-consistent across one set, so no "
                f"per-set sign convention can be right for all of it (B4)")

    return "\n".join(lines)

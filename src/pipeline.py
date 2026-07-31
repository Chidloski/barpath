"""
The driver. Runs the nine steps in order on one capture.

This did not exist until now, which is worth stating plainly: every real-data
result in this project had been produced by ad-hoc scripts living outside the
repo (`analysis/README.md` admits as much). "The pipeline" was a set of modules
that had never been executed end to end against a gym capture.

Two consequences of that, both fixed here:

`io.check_log` and `segment.quality_flags` were dead code. Both were written,
both were sound, and neither was called by anything but a test — so the
sampling-irregularity, quaternion-norm and high-g warnings never reached a
human. `check_log` fires on `deadlift_180x3` and nobody had ever been told.

Stages that are not implemented used to be invisible. `correct.apply_offset`,
`project.project_to_plane` and `project.confidence` all raised
`NotImplementedError`, so the pipeline genuinely could not complete. `run`
records that as a blocked stage and returns everything it did manage, rather
than throwing and losing the stages that worked. A partial result you can see
is worth more than an exception.

**As of 2026-07-30 nothing raises, and all nine steps run.** That is a
statement about coverage and about nothing else. `blocked` now empties on every
capture in `data/raw/` that segments at all, and the pipeline is still 5-15x
outside its horizontal spec (P2) with a display axis whose sign it cannot
resolve (B4). A completing pipeline is not a working one; read `confident` and
the vs-video numbers, not the absence of blocked entries.

The result dict is deliberately fat. Every intermediate stays in it, because
the recurring failure in this project has been a stage that looked fine from
its output and was wrong in the middle.

A3's metrics run here too, after the nine steps, though they are not steps —
they judge the steps. `dispersion` always; `vs_truth` when a video is supplied.
Both land in the same dict and both are printed by `summary`, because a number
nobody sees is how this pipeline came to fail while every stage passed.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import (calibrate, correct, integrate, io, metrics, orient, project,
               segment, truth)

# The optional middle token is a lift variant — bench_spoto_90x5. Without it
# `expected_reps` returned None for all three of the 2026-07-30 benches, so the
# rep-count gate silently skipped them and a 6-window segmentation of a 5-rep
# set went unnoticed until the ROM bound caught it.
REP_LABEL = re.compile(r"^(bench|squat|deadlift)(?:_[a-z]+)*_[\d.]+x(\d+)")


def expected_reps(path: str | Path) -> int | None:
    """Rep count encoded in the filename, e.g. deadlift_155x6_2 -> 6.

    Not truth in any deep sense, but it is the only label the captures carry
    and it is what the segmentation gate is written against, so a run that
    disagrees with it should say so.
    """
    m = REP_LABEL.match(Path(path).name)
    return int(m.group(2)) if m else None


def find_video(path: str | Path, video_dir: str | Path | None = None) -> Path | None:
    """The clip filmed alongside a capture, or None.

    Paired by name: the video's stem is a prefix of the CSV's, because the CSV
    carries a capture timestamp the video does not
    (deadlift_155x6_1_20260728.mov -> deadlift_155x6_1_20260728_122828.csv).
    Nothing enforces that convention, so a miss returns None rather than
    guessing at a pairing — comparing a capture against the wrong set's video
    would produce a confident, meaningless number.
    """
    path = Path(path)
    root = Path(video_dir) if video_dir else path.resolve().parents[2] / "data" / "video"
    if not root.is_dir():
        return None
    hits = sorted((v for v in root.glob("*.mov") if path.stem.startswith(v.stem)),
                  key=lambda v: len(v.stem), reverse=True)
    return hits[0] if hits else None


def run(path: str | Path, wrist_offset: np.ndarray | None = None,
        video: str | Path | None = None) -> dict:
    """Run every stage that can run. Never raises on an unimplemented stage.

    `wrist_offset` is `d` from step 6, in body coordinates, and it is off by
    default because nobody has measured it. B2 established that it cannot be
    fitted from the video either — the objective is flat and the fit absorbs
    P3 instead. A tape measure from watch centre to bar centre would switch it
    on; a guess makes things slightly worse.

    `video` turns on A3's metrics. Both are computed outside the nine steps
    because they judge the pipeline rather than being part of it, and both are
    recorded as blocked with a reason rather than raising, on the same
    principle as the stages: a partial result you can see beats an exception.
    """
    result: dict = {"path": str(path), "blocked": [], "notes": []}

    # 0 --- load ------------------------------------------------------------
    log = io.load_log(path)
    result["log"] = log
    result["warnings"] = io.check_log(log)
    result["expected_reps"] = expected_reps(path)

    # 1 --- calibration -----------------------------------------------------
    bias, info = calibrate.gyro_bias(log)
    result["gyro_bias"] = bias
    result["gyro_bias_info"] = info

    # 2-3 --- attitude and world frame --------------------------------------
    quat = orient.correct_attitude(log, bias)
    world = orient.to_world(log["accel"], log["quat"], quat)
    accel_bias = calibrate.accel_bias(world, log)
    world = world - accel_bias
    result["quat"] = quat
    result["accel_bias"] = accel_bias
    result["world_accel"] = world

    # 4 --- integrate -------------------------------------------------------
    velocity, position = integrate.integrate(world, log["dt"])
    result["velocity"] = velocity
    result["position"] = position

    # Two corrections have been tried here and both lost, for the same reason.
    #
    # B7 anchored velocity and vertical position to the floor impacts:
    # horizontal 5.1/9.2/15.4 -> 10.4/7.4/10.2 cm, vertical -> 15.3/18.0/4.5.
    # B6's splice removed the velocity error across the impact window instead,
    # and it WORKED on what it targeted — vertical momentum closure -0.778 ->
    # -0.049 m/s — while leaving horizontal bit-identical (a column-2 correction
    # cannot move a metric that reads columns 0 and 1) and pushing per-rep
    # vertical ROM to 82.6 cm against a 61 cm ceiling.
    #
    # The shared reason: the impact is ONE INSTANT PER REP and step 7's detrend
    # constrains position across the whole rep. A sparse true constraint does
    # not substitute for a dense false one — measured directly, splicing all
    # three axes and then closing vertical only gives 28.5/18.0/61.4 cm.
    #
    # `segment.rest_instants` survives both because it is validated against
    # video and `metrics.momentum_closure` is built on the same idea. Neither
    # correction does. See TASKS.md B7 and B6, analysis/22 and analysis/32.

    # 5 --- segment ---------------------------------------------------------
    impacts = segment.impact_anchors(log)
    bounds = segment.rep_bounds(log, velocity[:, 2])
    result["bounds"] = bounds
    result["quality"] = segment.quality_flags(log, bounds)
    result["impacts"] = impacts

    if result["expected_reps"] is not None and len(bounds) != result["expected_reps"]:
        result["notes"].append(
            f"found {len(bounds)} reps, filename says {result['expected_reps']}")

    # 6 --- wrist-to-bar offset ---------------------------------------------
    if wrist_offset is None:
        result["notes"].append(
            "step 6 off: wrist offset d unmeasured. Worth ~1-2 cm typical, "
            "4-6 cm worst case (B2). Needs a tape measure, not a fit")
        bar = position
    else:
        bar = correct.apply_offset(position, quat, wrist_offset)
    result["bar_position"] = bar

    # 7 --- per-rep detrend --------------------------------------------------
    reps = correct.detrend_set(bar, bounds, log["t"]) if bounds else []
    result["reps"] = reps

    # Vertical ROM against what the lifter can actually move the bar through.
    # The first external check bench and squat have ever had — every other gate
    # in this project needs deadlift floor impacts or video, and bench and squat
    # have neither. It is weak (a bound, not a measurement) and it is one-sided
    # per rep, but it is external, and it catches the two things a rep window
    # can get wrong that a count cannot see: spanning too much, and too little.
    #
    # Worth knowing where this is measured. Before step 7 the same quantity is
    # off by metres — deadlift_155x6_1 runs 100 cm on rep 1 to 1939 cm on rep 6 —
    # so it is the detrend that makes vertical dimensionally sane at all, and
    # this check does not vouch for anything upstream of it.
    result["rep_rom_m"] = [float(r[:, 2].max() - r[:, 2].min()) for r in reps]
    try:
        lift = truth.lift_of(path)
    except ValueError:
        result["notes"].append("no ROM check: cannot tell which lift this is")
    else:
        result["warnings"].extend(truth.rom_flags(lift, result["rep_rom_m"]))

    # 8 --- display axis -----------------------------------------------------
    #
    # `confident` gates plot.py's 4x horizontal stretch and NOTHING else. It
    # asks whether the axis is identifiable, not whether the path along it is
    # right — see project.confidence, which is explicit that no function of a
    # ratio and an excursion can ask the second question. The sign of the axis
    # remains unresolved (B4), so a confident set can still be drawn mirrored.
    if reps:
        axis, ratio, excursion = project.principal_axis(reps)
        result["axis"] = axis
        result["axis_ratio"] = ratio
        result["excursion"] = excursion
        result["planar"] = project.project_to_plane(reps, axis)
        result["confidence_reasons"] = project.confidence_reasons(
            ratio, excursion, n_reps=len(reps))
        result["confident"] = not result["confidence_reasons"]
    else:
        result["blocked"].append("steps 8-9: no reps to project")

    # 9 --- plot -------------------------------------------------------------
    # `planar` is what step 9 consumes; rendering it is run.py's job, because a
    # library function that imports matplotlib to return a dict is a trap.

    # A3 --- metrics. Not a pipeline step; the thing that judges the steps. ---
    if len(reps) >= 2:
        result["dispersion"] = metrics.dispersion(reps, log["t"], bounds)
    elif reps:
        result["notes"].append("dispersion needs >=2 reps")

    if video is not None:
        try:
            result["vs_truth"] = metrics.vs_truth(result, video)
        except (ValueError, FileNotFoundError) as e:
            result["blocked"].append(f"A3 vs_truth: {e}")

    return result


def summary(result: dict) -> str:
    """One capture, as text. Everything a human needs to judge the run."""
    log = result["log"]
    lines = [
        f"{Path(result['path']).name}",
        f"  {len(log['t'])} samples, {log['t'][-1]:.1f} s at {log['fs']:.1f} Hz",
    ]

    for w in result["warnings"]:
        lines.append(f"  WARNING  {w}")

    info = result["gyro_bias_info"]
    deg = 180.0 / np.pi
    lines.append(
        f"  gyro bias measured {np.array2string(info['raw'] * deg, precision=2)} deg/s, "
        f"applied={info['applied']}")

    n = len(result["bounds"])
    want = result["expected_reps"]
    lines.append(f"  reps found {n}" + (f" / {want} expected" if want else ""))
    lines.append(f"  floor impacts {len(result['impacts'])}")

    # The CAVEAT that used to sit here explained why the strap-resonance
    # rejections should not be trusted. #14 removed the flag rather than the
    # caveat: it rejected 33 of 73 real reps and fired hardest on the lift with
    # no floor impact at all. See segment.quality_flags.
    bad = [q for q in result["quality"] if not q["ok"]]
    if bad:
        for q in bad:
            lines.append(f"  REJECT rep at {q['rep']}: clipped")
    elif n:
        lines.append(f"  quality  all {n} reps pass")

    if "axis_ratio" in result:
        lines.append(f"  display axis ratio {result['axis_ratio']:.1f}, "
                     f"excursion {result['excursion'] * 100:.1f} cm")
        # The verdict with its reason, never the verdict alone: "low
        # confidence" is a conclusion and the reason is the evidence for it.
        # And say what confidence does not cover, every time, because the
        # failure this project keeps repeating is a pass mistaken for a proof.
        if result["confident"]:
            lines.append("  confident  axis is identifiable; the 4x stretch is "
                         "allowed. This says NOTHING about accuracy — see "
                         "project.confidence — and the axis SIGN is unresolved "
                         "(B4), so the path may be drawn mirrored")
        else:
            for why in result["confidence_reasons"]:
                lines.append(f"  LOW CONFIDENCE  {why}")

    report = metrics.summary(result.get("dispersion"), result.get("vs_truth"))
    if report:
        lines.append(report)

    for note in result["notes"]:
        lines.append(f"  NOTE  {note}")
    for b in result["blocked"]:
        lines.append(f"  BLOCKED  {b}")

    return "\n".join(lines)

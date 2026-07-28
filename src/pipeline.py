"""
The driver. Runs the nine steps in order on one capture.

This did not exist until now, which is worth stating plainly: every real-data
result in this project had been produced by ad-hoc scripts living outside the
repo (`analysis/README.md` admits as much). "The pipeline" was a set of modules
that had never been executed end to end against a gym capture.

Two consequences of that, both fixed here:

`io.check_log` and `segment.quality_flags` were dead code. Both were written,
both were sound, and neither was called by anything but a test — so the
sampling-irregularity, quaternion-norm and saturation warnings never reached a
human. `check_log` fires on `deadlift_180x3` and nobody had ever been told.

Stages that are not implemented used to be invisible. `correct.apply_offset`,
`project.project_to_plane` and `project.confidence` all raise
`NotImplementedError`, so the pipeline genuinely cannot complete. `run` records
that as a blocked stage and returns everything it did manage, rather than
throwing and losing the eight stages that worked. A partial result you can see
is worth more than an exception.

The result dict is deliberately fat. Every intermediate stays in it, because
the recurring failure in this project has been a stage that looked fine from
its output and was wrong in the middle.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import calibrate, correct, integrate, io, orient, project, segment

REP_LABEL = re.compile(r"^(bench|squat|deadlift)_[\d.]+x(\d+)")


def expected_reps(path: str | Path) -> int | None:
    """Rep count encoded in the filename, e.g. deadlift_155x6_2 -> 6.

    Not truth in any deep sense, but it is the only label the captures carry
    and it is what the segmentation gate is written against, so a run that
    disagrees with it should say so.
    """
    m = REP_LABEL.match(Path(path).name)
    return int(m.group(2)) if m else None


def run(path: str | Path, wrist_offset: np.ndarray | None = None) -> dict:
    """Run every stage that can run. Never raises on an unimplemented stage.

    `wrist_offset` is `d` from step 6, in body coordinates. Leave it None until
    it has been established against video — a guessed lever arm is worth
    8-13 cm of horizontal on real captures, which is the whole error budget.
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

    # 5 --- segment ---------------------------------------------------------
    bounds = segment.rep_bounds(log, velocity[:, 2])
    result["bounds"] = bounds
    result["quality"] = segment.quality_flags(log, bounds)
    result["impacts"] = segment.impact_anchors(log)

    if result["expected_reps"] is not None and len(bounds) != result["expected_reps"]:
        result["notes"].append(
            f"found {len(bounds)} reps, filename says {result['expected_reps']}")

    # 6 --- wrist-to-bar offset ---------------------------------------------
    if wrist_offset is None:
        result["blocked"].append(
            "step 6 apply_offset: no wrist offset supplied. R(t).d varies by "
            "8-13 cm horizontally on real captures, including deadlift, so "
            "omitting it is not a small approximation")
        bar = position
    else:
        try:
            bar = correct.apply_offset(position, quat, wrist_offset)
        except NotImplementedError:
            result["blocked"].append("step 6 apply_offset: not implemented")
            bar = position
    result["bar_position"] = bar

    # 7 --- per-rep detrend --------------------------------------------------
    reps = correct.detrend_set(bar, bounds, log["t"]) if bounds else []
    result["reps"] = reps

    # 8 --- display axis -----------------------------------------------------
    if reps:
        axis, ratio, excursion = project.principal_axis(reps)
        result["axis"] = axis
        result["axis_ratio"] = float(np.real(ratio))
        result["excursion"] = float(np.real(excursion))
        try:
            result["planar"] = project.project_to_plane(reps, axis)
        except NotImplementedError:
            result["blocked"].append("step 8 project_to_plane: not implemented")
        try:
            result["confident"] = project.confidence(result["axis_ratio"],
                                                     result["excursion"])
        except NotImplementedError:
            result["blocked"].append("step 8 confidence: not implemented")

    # 9 --- plot -------------------------------------------------------------
    if "planar" not in result:
        result["blocked"].append("step 9 plot: needs step 8")

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

    bad = [q for q in result["quality"] if not q["ok"]]
    if bad:
        for q in bad:
            flags = [k for k in ("clipped", "strap_resonance") if q[k]]
            lines.append(f"  REJECT rep at {q['rep']}: {', '.join(flags)}")
        if any(q["strap_resonance"] for q in bad):
            lines.append(
                "  CAVEAT  strap_resonance is currently unreliable and these "
                "rejections should not be trusted. It thresholds the FRACTION "
                "of energy above 10 Hz, so a quiet rep fails for having little "
                "signal at all: the rejected bench reps carry 13-18k of "
                "absolute high-frequency energy against 0.9-2.9M in accepted "
                "deadlift reps. Its docstring intends absolute energy.")
    elif n:
        lines.append(f"  quality  all {n} reps pass")

    if "axis_ratio" in result:
        lines.append(f"  display axis ratio {result['axis_ratio']:.1f}, "
                     f"excursion {result['excursion'] * 100:.1f} cm")

    for note in result["notes"]:
        lines.append(f"  NOTE  {note}")
    for b in result["blocked"]:
        lines.append(f"  BLOCKED  {b}")

    return "\n".join(lines)

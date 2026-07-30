#!/usr/bin/env python3
"""Run the pipeline over captures and print what happened.

    python run.py                      # every capture in data/raw
    python run.py data/raw/foo.csv     # one
    python run.py --plot               # also write diagnostics to analysis/
    python run.py --truth              # also measure against the video (A3)
    python run.py --stages             # draw the pipeline stage by stage
    python run.py --rom                # per-rep vertical ROM against the bounds
    python run.py --anchors            # C6: attitude before and after a set
    python run.py --bias               # B6: constant-bias corrections vs the video

--truth is slow: it decodes each clip. It only produces numbers on deadlift,
which is the only lift with trustworthy video truth — the others report why.

--stages writes analysis/21_pipeline_stages.png: one column per lift, one row
per stage, from raw acceleration to the bar path. It ignores any paths given
on the command line and uses one representative capture per lift, because the
point of it is the comparison.

--rom writes analysis/23_rom_bounds.png: every capture's per-rep vertical range
of motion against what the lifter can actually move a bar through. Also slow —
it decodes the deadlift clips to check the video against the same bounds, which
is where it found that two of the three are mis-scaled.

--anchors writes analysis/24_c6_two_anchors.png: Core Motion's attitude error at
the still holds bracketing each set, the per-rep residual that the anchors
cannot see, and where the deadlift's share of it enters. Needs the `phase`
column, so it uses the 2026-07-30 captures onward.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import pipeline  # noqa: E402


STAGE_CAPTURES = [("squat", "squat_130x5"),
                  ("bench", "bench_90x4_1"),
                  ("deadlift", "deadlift_155x6_1")]


def draw_stages() -> int:
    """One representative capture per lift, drawn stage by stage."""
    import matplotlib
    matplotlib.use("Agg")
    from src import plot, truth

    raw = ROOT / "data" / "raw"
    results, truths = {}, {}
    for label, stem in STAGE_CAPTURES:
        path = next(raw.glob(f"{stem}*.csv"), None)
        if path is None:
            print(f"{stem} not in data/raw/ — skipping")
            continue
        video = pipeline.find_video(path, ROOT / "data" / "video")
        # Only deadlift has trustworthy video truth; see src/README.md.
        use = video if label == "deadlift" else None
        results[f"{label}  ({stem})"] = pipeline.run(path, video=use)

        if use is not None:
            from src import segment
            log = results[f"{label}  ({stem})"]["log"]
            tp = truth.bar_path(use)
            fit = truth.sync(truth.landings(tp),
                             [float(log["t"][k]) for k in segment.impact_anchors(log)])
            truths[f"{label}  ({stem})"] = (truth.to_imu_time(tp, fit), tp["height"])

    if not results:
        print("no captures found for the stage diagram")
        return 1

    out = ROOT / "analysis" / "21_pipeline_stages.png"
    plot.plot_stages(results, truths).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_rom() -> int:
    """Per-rep vertical ROM for every capture, against the measured bounds."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import metrics, plot, truth

    raw = ROOT / "data" / "raw"
    recon, video = {}, {}
    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue                      # stationary diagnostics have no reps
        result = pipeline.run(path)
        recon[path.stem] = (lift, result["rep_rom_m"])

        clip = pipeline.find_video(path, ROOT / "data" / "video")
        if clip is None or lift != "deadlift":
            continue                      # only deadlift video is trackable
        m = metrics.vs_truth(result, clip)
        video[path.stem] = [r["video_rom_cm"] / 100 for r in m["per_rep"]
                            if r["covered"]]
        flags = m["video_rom_flags"]
        print(f"{path.stem}: video ROM median "
              f"{np.median(video[path.stem])*100:.1f} cm, "
              f"{len(flags)} rep(s) flagged")

    if not recon:
        print("no captures found for the ROM plot")
        return 1

    out = ROOT / "analysis" / "23_rom_bounds.png"
    plot.plot_rom_bounds(recon, video).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_anchors() -> int:
    """C6 — the two-anchor attitude measurement, and what it cannot see."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import calibrate, io, orient, plot, segment, truth

    raw = ROOT / "data" / "raw"
    anchors, residuals, exclusion, momentum = {}, {}, {}, {}
    lifts: dict[str, tuple[list, list]] = {}

    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue
        result = pipeline.run(path)
        log = result["log"]
        world = orient.to_world(log["accel"], log["quat"], log["quat"])
        stem = path.stem.split("_2026")[0]

        try:
            a = calibrate.anchor_tilt(log, world)
        except ValueError:
            pass                              # pre-2026-07-30, no closing hold
        else:
            anchors[stem] = a
            print(f"{stem:22s} tilt {a['open_deg']:.3f} -> {a['close_deg']:.3f} deg "
                  f"over {a['span_s']:.0f} s  (gyro alone would drift "
                  f"{a['gyro_only_deg']:.2f} deg)")

        # The per-rep mean must be zero: a rep starts and ends at rest.
        rep_h = [float(np.linalg.norm(world[a:b].mean(axis=0)[:2]) / io.G)
                 for a, b in result["bounds"]]
        holds = calibrate.hold_windows(log)
        hold_h = [float(np.linalg.norm(world[w, :2].mean(axis=0)) / io.G)
                  for w in holds.values() if w is not None]
        lifts.setdefault(lift, ([], []))
        lifts[lift][0].extend(hold_h)
        lifts[lift][1].extend(rep_h)

        if lift != "deadlift":
            continue
        imp = segment.impact_anchors(log)
        pads, vals = [], []
        for pad_ms in (0, 50, 100, 250, 500):
            pad = int(pad_ms * log["fs"] / 1000)
            keep = np.ones(len(world), bool)
            for k in imp:
                keep[max(0, k - pad):k + pad + 1] = False
            v = [np.linalg.norm(world[a:b][keep[a:b]].mean(axis=0)[:2])
                 for a, b in result["bounds"] if keep[a:b].sum() > 10]
            pads.append(pad_ms)
            vals.append(float(np.median(v)) / io.G)
        exclusion[stem] = (pads, vals)
        momentum[stem] = [float(np.trapezoid(world[a:b, 2], log["t"][a:b]))
                          for a, b in result["bounds"]]

    if not anchors:
        print("no captures with both C3 holds — need 2026-07-30 or later")
        return 1

    for lift, (hold, rep) in lifts.items():
        print(f"{lift:9s} hold residual median "
              f"{np.median(hold) if hold else float('nan'):.4f} g, "
              f"per-rep median {np.median(rep):.4f} g")

    out = ROOT / "analysis" / "24_c6_two_anchors.png"
    plot.plot_anchors(anchors, lifts, exclusion, momentum).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


B6_VARIANTS = ["shipping", "zero-mean accel\nper rep",
               "zero-mean, no\nposition detrend", "bias from rest-to-rest\nclosure"]


def draw_bias_models() -> int:
    """B6 — measure each constant-bias correction against the video."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import correct, integrate, io, metrics, plot, segment

    raw = ROOT / "data" / "raw"
    variants: dict[str, list] = {k: [] for k in B6_VARIANTS}
    closure, traces = {}, {}

    for path in sorted(raw.glob("deadlift*.csv")):
        video = pipeline.find_video(path, ROOT / "data" / "video")
        if video is None:
            continue
        base = pipeline.run(path, video=video)
        log, t, world = base["log"], base["log"]["t"], base["world_accel"]
        stem = path.stem.split("_2026")[0]

        rest = segment.rest_instants(log)
        segs = [world[a:b].mean(axis=0) for a, b in zip(rest, rest[1:])]
        bias = np.mean(segs, axis=0) if segs else np.zeros(3)

        def build(offset, per_rep_mean, axes):
            reps = []
            for a, b in base["bounds"]:
                acc = world[a:b] - offset
                if per_rep_mean:
                    acc = acc - acc.mean(axis=0)
                _, p = integrate.integrate(acc, log["dt"][a:b])
                if axes:
                    p = correct.detrend_rep(p, 0, len(p), t[a:b], axes=axes)
                reps.append(p)
            return metrics.vs_truth({**base, "reps": reps}, video)

        variants[B6_VARIANTS[0]].append(base["vs_truth"]["pipeline_h_rms"])
        variants[B6_VARIANTS[1]].append(build(0.0, True, (0, 1, 2))["pipeline_h_rms"])
        variants[B6_VARIANTS[2]].append(build(0.0, True, ())["pipeline_h_rms"])
        variants[B6_VARIANTS[3]].append(build(bias, False, (0, 1, 2))["pipeline_h_rms"])

        # The bias the MEASURED error implies, against the one closure estimates.
        T = float(np.median([t[min(b, len(t) - 1)] - t[a] for a, b in base["bounds"]]))
        measured_cm = base["vs_truth"]["pipeline_v_rms"]
        implied = measured_cm / 100 * 8 / T ** 2 / io.G
        closure[stem] = (implied, float(abs(bias[2])) / io.G)

        if len(rest) >= 2:
            a, b = int(rest[0]), int(rest[1])
            imp = [k for k in segment.impact_anchors(log) if a <= k < b]
            traces[stem] = (t[a:b] - t[a],
                            np.concatenate([[0.0], np.cumsum(
                                world[a:b - 1, 2] * log["dt"][a:b - 1])]),
                            float(t[imp[0]] - t[a]) if imp else 0.0)

    if not closure:
        print("no deadlift captures with video for the B6 comparison")
        return 1

    for k, v in variants.items():
        print(f"{k.replace(chr(10), ' '):34s} " + " / ".join(f"{x:6.2f}" for x in v))
    for stem, (implied, estimated) in closure.items():
        print(f"{stem:22s} measured error implies {implied:.4f} g; "
              f"closure estimates {estimated:.4f} g ({estimated/implied:.1f}x)")

    out = ROOT / "analysis" / "25_b6_bias_models.png"
    plot.plot_bias_models(variants, closure, traces).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_plot = "--plot" in argv
    want_truth = "--truth" in argv

    if "--stages" in argv:
        return draw_stages()
    if "--rom" in argv:
        return draw_rom()
    if "--anchors" in argv:
        return draw_anchors()
    if "--bias" in argv:
        return draw_bias_models()

    paths = [Path(a) for a in args] or sorted((ROOT / "data" / "raw").glob("*.csv"))
    if not paths:
        print("no captures found in data/raw/")
        return 1

    blocked: set[str] = set()
    for path in paths:
        video = pipeline.find_video(path, ROOT / "data" / "video") if want_truth else None
        result = pipeline.run(path, video=video)
        print(pipeline.summary(result))
        print()
        blocked.update(result["blocked"])

        if want_plot:
            import matplotlib
            matplotlib.use("Agg")
            from src import plot
            out = ROOT / "analysis" / f"run_{path.stem}.png"
            fig = plot.plot_diagnostics(result["log"], result["position"],
                                        bounds=result["bounds"])
            fig.savefig(out, dpi=110)
            print(f"  wrote {out.relative_to(ROOT)}\n")

    if blocked:
        print("=" * 72)
        print("The pipeline does not complete. Blocked stages, deduplicated:")
        for b in sorted(blocked):
            print(f"  - {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

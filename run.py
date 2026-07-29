#!/usr/bin/env python3
"""Run the pipeline over captures and print what happened.

    python run.py                      # every capture in data/raw
    python run.py data/raw/foo.csv     # one
    python run.py --plot               # also write diagnostics to analysis/
    python run.py --truth              # also measure against the video (A3)
    python run.py --stages             # draw the pipeline stage by stage

--truth is slow: it decodes each clip. It only produces numbers on deadlift,
which is the only lift with trustworthy video truth — the others report why.

--stages writes analysis/21_pipeline_stages.png: one column per lift, one row
per stage, from raw acceleration to the bar path. It ignores any paths given
on the command line and uses one representative capture per lift, because the
point of it is the comparison.
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


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_plot = "--plot" in argv
    want_truth = "--truth" in argv

    if "--stages" in argv:
        return draw_stages()

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

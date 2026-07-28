#!/usr/bin/env python3
"""Run the pipeline over captures and print what happened.

    python run.py                      # every capture in data/raw
    python run.py data/raw/foo.csv     # one
    python run.py --plot               # also write diagnostics to analysis/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import pipeline  # noqa: E402


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_plot = "--plot" in argv

    paths = [Path(a) for a in args] or sorted((ROOT / "data" / "raw").glob("*.csv"))
    if not paths:
        print("no captures found in data/raw/")
        return 1

    blocked: set[str] = set()
    for path in paths:
        result = pipeline.run(path)
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

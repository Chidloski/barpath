"""Track every data_v2 clip, write a review figure each, and a summary sheet."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from run_all import run_one, VIDEO, ROM, lift_of
from review import review_figure

OUT = HERE / "figures"


def main(names):
    OUT.mkdir(exist_ok=True)
    rows = []
    for n in names:
        t0 = time.time()
        try:
            res = run_one(VIDEO / f"{n}.mov")
        except Exception as e:                              # noqa: BLE001
            print(f"{n:36s} ERROR {type(e).__name__}: {e}", flush=True)
            rows.append(dict(name=n, ok=False, err=str(e)))
            continue
        if not res["ok"]:
            print(f"{n:36s} {res['reason']}", flush=True)
            rows.append(dict(name=n, ok=False, err=res["reason"]))
            continue
        review_figure(n, VIDEO / f"{n}.mov", res, OUT / f"{n}.png")
        s, sm = res["score"], res["summary"]
        rows.append(dict(name=n, ok=True, layout=res["layout"], r=res["r_px"],
                         cov=sm["coverage"], slots=s["slots"],
                         rms=sm["median_rms"], jit=s["jitter"],
                         travel=sm["travel_m"], impl=res["implausible"],
                         lift=res["lift"],
                         score=s["score"],
                         runner=res["runner_up"]["score"] if res["runner_up"] else 0.0))
        print(f"{n:36s} {res['layout']:>10} r={res['r_px']:6.1f} "
              f"cov={sm['coverage']:.2f} slots={s['slots']:.0f} "
              f"rms={sm['median_rms']:.2f} travel={sm['travel_m']*100:6.1f}cm "
              f"{'IMPLAUSIBLE' if res['implausible'] else 'ok'}  "
              f"({time.time()-t0:.0f}s)", flush=True)
    np.save(OUT / "rows.npy", np.array(rows, dtype=object))
    summary_sheet(rows)
    return rows


def summary_sheet(rows):
    good = [r for r in rows if r.get("ok")]
    if not good:
        return
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), dpi=120)
    order = sorted(good, key=lambda r: (r["lift"], r["name"]))
    y = np.arange(len(order))
    names = [r["name"] for r in order]
    colour = {"bench": "#0a84ff", "squat": "#ff9f0a", "deadlift": "#30d158"}

    ax = axes[0]
    for i, r in enumerate(order):
        lo, hi = ROM[r["lift"]]
        ax.plot([lo * 100, hi * 100], [i, i], color="#bbb", lw=6, solid_capstyle="butt")
        ax.plot(r["travel"] * 100, i, "o", color=colour[r["lift"]],
                markeredgecolor="#c00" if r["impl"] else "none", markeredgewidth=2)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=6)
    ax.set_xlabel("whole-clip vertical travel (cm)", fontsize=8)
    ax.set_title("travel vs the lift's per-rep ROM band\n(grey bar = truth.VERTICAL_ROM_M)",
                 fontsize=8)
    ax.grid(alpha=0.25, axis="x")
    ax.tick_params(labelsize=7)

    ax = axes[1]
    ax.barh(y, [r["cov"] * 100 for r in order],
            color=[colour[r["lift"]] for r in order])
    ax.set_yticks(y)
    ax.set_yticklabels([])
    ax.set_xlabel("frames tracked (%)", fontsize=8)
    ax.set_xlim(0, 105)
    ax.set_title("coverage", fontsize=8)
    ax.grid(alpha=0.25, axis="x")
    ax.tick_params(labelsize=7)

    ax = axes[2]
    ax.barh(y - 0.2, [r["score"] for r in order], height=0.4,
            color="#0a84ff", label="chosen")
    ax.barh(y + 0.2, [r["runner"] for r in order], height=0.4,
            color="#ccc", label="runner-up")
    ax.set_yticks(y)
    ax.set_yticklabels([])
    ax.set_xlabel("hypothesis score", fontsize=8)
    ax.set_title("how close was the decision?", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.25, axis="x")
    ax.tick_params(labelsize=7)

    fig.suptitle("data_v2 tracking — all clips", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "00_summary.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.stem for p in VIDEO.glob("*.mov"))
    main(names)

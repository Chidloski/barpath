"""H24 — the owner's final cut: cover the LAST rep by ending it before the impact.

H23 ruled that no correction may drop a rep, which closed C29's and H22's
rest-to-rest frame as a shipping candidate: after the final rep the lifter
releases the bar, so no rest exists to close the last window on.

**The owner's proposal dissolves it.** *"Use the rep boundaries for all but the
last rep; for the last rep one could simply cut the rep right before the moment
of impact."* The last window does not need a REST — it needs a moment where the
bar is back at the height it started from, which is what step 7's closure
asserts. Just before the final impact the bar is at the floor and the
reconstruction has not yet been handed the impulse that corrupts it.

Two things follow, and the second is why this is not a patch:

* the final impact ends up OUTSIDE every window, so the last rep correctly
  receives no impulse correction — there is no impulse in it to correct;
* it is therefore not the trap that killed B7, B6, C19 and C28b, all of which
  placed a correction AT a boundary. Here the corrupted samples are simply not
  covered, rather than covered and then fought over.

Run with --cache to re-render from the JSON.
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

from src import correct, metrics, oracle, pipeline

CACHE = Path(__file__).with_suffix(".json")
# Excluded by hand and named every time: straps (H20), a 22.8% clock (G3), a
# miscounted single (H15). `EXTRA` are scored separately for comparability with
# H19 and H22, which both reported an all-ten column.
CLEAN = ["deadlift_150x4_1_20260808_121648", "deadlift_155x5_1_20260815_133343",
         "deadlift_160x4_2_20260808_122319", "deadlift_160x5_2_20260815_134017",
         "deadlift_160x6_1_20260804_104711", "deadlift_160x6_2_20260804_105455",
         "deadlift_185x3_20260804_103456", "deadlift_190x3_20260818_122535"]
EXTRA = ["deadlift_170x4_3_20260808_122936", "deadlift_200x1_20260808_120837"]
CUTS = [0.02, 0.04, 0.08, 0.12, 0.20, 0.30, 0.50]


def compute():
    d = correct.WRIST_OFFSET_M["deadlift"]
    out = {}
    for stem in CLEAN + EXTRA:
        csv = ROOT / "data_v2" / "raw" / f"{stem}.csv"
        video = pipeline.find_video(csv)
        base = pipeline.run(csv, video=video)
        if base.get("vs_truth") is None:
            continue

        def rec(m):
            return {"h": m["pipeline_h_rms"], "bn": m["beats_null"],
                    "null": m["null_h_rms"], "n": m["n_compared"]}

        row = {"label": len(base["bounds"]), "ship": rec(base["vs_truth"]),
               "h22": rec(metrics.vs_truth(
                   oracle.jump_period_windows(base, wrist_offset=d), video))}
        for c in CUTS:
            row[f"cut{c:.2f}"] = rec(metrics.vs_truth(
                oracle.jump_period_windows(base, wrist_offset=d,
                                           final_cut_s=c), video))
        out[stem] = row
        print(f"  {stem[:40]:42} ship {row['ship']['h']:5.2f} "
              f"cut {row['cut0.08']['h']:5.2f} "
              f"({row['cut0.08']['n']}/{row['label']} reps)", flush=True)
    CACHE.write_text(json.dumps(out, indent=1))
    return out


def agg(data, keys, arm):
    h = [data[k][arm]["h"] for k in keys if arm in data[k]]
    b = [data[k][arm]["bn"] for k in keys if arm in data[k]]
    n = sum(data[k][arm]["n"] for k in keys if arm in data[k])
    tot = sum(data[k]["label"] for k in keys)
    nul = [data[k][arm]["null"] / data[k]["ship"]["null"] for k in keys
           if arm in data[k]]
    return (float(np.median(h)), float(np.median(b)), n, tot,
            float(np.median(nul)), h)


def short(k):
    return k.replace("deadlift_", "").split("_2026")[0] + " " + k.split("_2026")[1][:4]


def render(data):
    clean = [k for k in CLEAN if k in data]
    fig = plt.figure(figsize=(15.0, 11.0))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.06], hspace=0.40,
                          wspace=0.24)

    # ---- A: coverage, which is the whole point ---------------------------
    ax = fig.add_subplot(gs[0, 0])
    arms = ["ship", "h22", "cut0.08"]
    names = ["shipping", "H22 period frame", "H24 + final cut"]
    cols = ["#34495e", "#e67e22", "#27ae60"]
    for i, (a, nm, c) in enumerate(zip(arms, names, cols)):
        _, _, n, tot, _, _ = agg(data, clean, a)
        ax.barh(i, n, color=c, height=0.6, zorder=3)
        ax.text(n + 0.4, i, f"{n}/{tot} reps SCORED", va="center", fontsize=10,
                color=c, fontweight="bold")
    ax.set_yticks(range(3))
    ax.set_yticklabels(names, fontsize=10)
    ax.set_xlim(0, 44)
    ax.set_xlabel("reps actually compared against the video (`n_compared`)")
    ax.set_title("A · COVERAGE — the requirement H23 added.\n"
                 "Count reps SCORED, not windows produced: H22 makes 33 windows "
                 "and scores 31.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="x")

    # ---- B: per capture ---------------------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    x = np.arange(len(clean))
    for off, (a, nm, c) in enumerate(zip(arms, names, cols)):
        ax.bar(x + (off - 1) * 0.27, [data[k][a]["h"] for k in clean],
               width=0.26, color=c, label=nm, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels([short(k) for k in clean], rotation=55, ha="right",
                       fontsize=7.5)
    ax.set_ylabel("horizontal rms vs video, cm")
    ax.legend(fontsize=8.5)
    ax.set_title("B · Per capture. The cut also RESCUES the two H22 made worse\n"
                 "(155x5_1 4.73->3.56, 160x4_2 4.16->1.90), because it removes "
                 "the final\nimpact from the last window on EVERY set, not only "
                 "where a rest was missing.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, axis="y")

    # ---- C: the cut width is a plateau ------------------------------------
    ax = fig.add_subplot(gs[1, 0])
    med = [agg(data, clean, f"cut{c:.2f}")[0] for c in CUTS]
    cov = [agg(data, clean, f"cut{c:.2f}")[2] for c in CUTS]
    ax.plot(CUTS, med, marker="o", color="#27ae60", lw=2.4, zorder=3,
            label="H24 final cut")
    ax.axhline(agg(data, clean, "ship")[0], color="#34495e", ls="--", lw=1.6,
               label="shipping")
    ax.axhline(agg(data, clean, "h22")[0], color="#e67e22", ls=":", lw=1.8,
               label="H22 (31 of 36 reps)")
    for c, m, n in zip(CUTS, med, cov):
        ax.annotate(f"{n}r", (c, m), fontsize=7.5, xytext=(0, 7),
                    textcoords="offset points", ha="center")
    ax.set_xscale("log")
    ax.set_xticks(CUTS)
    ax.set_xticklabels([f"{c:g}" for c in CUTS], fontsize=8.5)
    ax.minorticks_off()
    ax.set_xlabel("cut_s — how far before the impact the last window closes, s")
    ax.set_ylabel("median horizontal rms, cm")
    ax.legend(fontsize=8.5)
    ax.set_title("C · Not a tuned constant: flat from 0.02 to 0.30 s.\n"
                 "The bar's fore-aft barely moves in the last fraction of a "
                 "second of descent,\nso where exactly the cut falls does not "
                 "matter.", fontsize=11, loc="left")
    ax.grid(alpha=0.25, which="both")

    # ---- D: the honest scoreboard ----------------------------------------
    ax = fig.add_subplot(gs[1, 1])
    ax.axis("off")
    rows = []
    for a, nm in zip(arms, names):
        h, b, n, tot, nul, _ = agg(data, clean, a)
        rows.append([nm, f"{h:.2f}", f"{b:.2f}", f"{n}/{tot}", f"{nul:.2f}"])
    tbl = ax.table(cellText=rows,
                   colLabels=["arm", "h rms", "beats_null", "reps scored",
                              "null vs ship"],
                   colWidths=[0.30, 0.15, 0.19, 0.19, 0.19],
                   cellLoc="center", loc="upper center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1, 1.9)
    for j in range(5):
        tbl[(0, j)].set_facecolor("#ecf0f1")
        tbl[(0, j)].set_text_props(fontweight="bold")
    for j in range(5):
        tbl[(3, j)].set_facecolor("#eafaf1")
    hs_ship = [data[k]["ship"]["h"] for k in clean]
    hs_cut = [data[k]["cut0.08"]["h"] for k in clean]
    better = sum(1 for a_, b_ in zip(hs_ship, hs_cut) if b_ < a_)
    pv = float(stats.wilcoxon(hs_ship, hs_cut).pvalue)
    ax.text(0.02, 0.34,
            f"Against shipping: better on {better} of {len(clean)}, "
            f"paired Wilcoxon p = {pv:.3f}.\n\n"
            "Read it honestly. `null vs ship` is 1.00, so unlike C29 and H22\n"
            "this is like-for-like — the confound H19 found is gone, not\n"
            "inherited. But `beats_null` is 0.77: still WORSE than drawing no\n"
            "fore-aft motion at all. It satisfies all three requirements for\n"
            "the first time; it is not yet a working horizontal.",
            transform=ax.transAxes, fontsize=9.5, va="top", family="monospace")
    ax.set_title("D · The scoreboard, on the 8 clean deadlifts",
                 fontsize=11, loc="left")

    fig.suptitle("H24 · The owner's final cut — the first deadlift frame to "
                 "cover every rep", fontsize=14, y=0.985)
    out = Path(__file__).with_suffix(".png")
    fig.savefig(out, dpi=125, bbox_inches="tight")
    print(f"wrote {out}")

    print(f"\n{'arm':22}{'h':>7}{'bn':>7}{'reps':>9}{'null':>7}   (8 clean)")
    for a, nm in zip(arms, names):
        h, b, n, tot, nul, _ = agg(data, clean, a)
        print(f"{nm:22}{h:7.2f}{b:7.2f}{f'{n}/{tot}':>9}{nul:7.2f}")
    allk = [k for k in CLEAN + EXTRA if k in data]
    print(f"\n{'arm':22}{'h':>7}{'bn':>7}{'reps':>9}{'null':>7}   (all 10)")
    for a, nm in zip(arms, names):
        h, b, n, tot, nul, _ = agg(data, allk, a)
        print(f"{nm:22}{h:7.2f}{b:7.2f}{f'{n}/{tot}':>9}{nul:7.2f}")


if __name__ == "__main__":
    if "--cache" in sys.argv and CACHE.exists():
        render(json.loads(CACHE.read_text()))
    else:
        render(compute())

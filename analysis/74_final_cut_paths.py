"""H24b — what the final cut does to the BAR PATHS, not to the summary numbers.

H24 reports 2.03 cm against shipping's 2.78 with full rep coverage. A table
cannot show WHERE that comes from, and this project's recurring failure is an
aggregate that passes while the thing fails — so draw the paths.

Every curve is `metrics.vs_truth`'s own per-rep output: `curve_video` and
`curve_pipeline`, already paired, resampled to a common length and aligned. No
new alignment, no new resampling, nothing this figure invents.

**AND DRAWING THEM IS WHAT CAUGHT THE COST H24 DID NOT REPORT.** H24 was scored
on the horizontal alone. The paths show tall, distorted first reps, and the
measurement confirms them: the rest-to-rest frame takes VERTICAL rms from
shipping's 2.88 cm — inside the +/-2-3 cm spec, with 0 of 36 reps outside
`capture.VERTICAL_ROM_M` — to 4.03 (H22) and 5.15 (with the cut), with 9 of 31
and 6 of 36 reps out of band. Reps of 70-79 cm on a lift whose range is 40-61.

**The cost is INHERITED from the frame, not caused by the cut**, which is why
this figure separates them: the first rep's ROM is identical under H22 and under
the cut (78.3/78.3, 75.2/75.2, 79.2/79.2), so it belongs to H22's pre-pull
anchor. The cut in fact REDUCES the out-of-band fraction, 29% to 17%.

This is the project's oldest failure shape and it caught the author of H24: an
aggregate improved while the thing got worse on an axis nobody looked at.
"""
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

from src import correct, metrics, oracle, pipeline

CLEAN = ["deadlift_150x4_1_20260808_121648", "deadlift_155x5_1_20260815_133343",
         "deadlift_160x4_2_20260808_122319", "deadlift_160x5_2_20260815_134017",
         "deadlift_160x6_1_20260804_104711", "deadlift_160x6_2_20260804_105455",
         "deadlift_185x3_20260804_103456", "deadlift_190x3_20260818_122535"]
C_VID, C_SHIP, C_CUT = "#111111", "#3498db", "#27ae60"


def curves(vs):
    """Per-rep (video, pipeline) pairs, in cm, each aligned to its own start."""
    out = []
    for r in vs.get("per_rep") or []:
        if not r.get("covered"):
            continue
        v = np.asarray(r["curve_video"], float) * 100.0
        p = np.asarray(r["curve_pipeline"], float) * 100.0
        if v.ndim != 2 or len(v) < 4:
            continue
        out.append((v - v[0], p - p[0]))       # step 9: align by start point
    return out


BAND = (40.0, 61.0)      # capture.VERTICAL_ROM_M for deadlift, cm


def draw(ax, pairs, colour, which=1):
    """Every rep thin, the arm's MEAN bold. Out-of-band reps get a red halo."""
    curves, n_bad = [], 0
    for _, p in pairs:
        rom = float(np.ptp(p[:, 1]))
        if not BAND[0] <= rom <= BAND[1]:
            n_bad += 1
            ax.plot(p[:, 0], p[:, 1], color="#e74c3c", lw=2.6, alpha=0.30,
                    zorder=1)
        ax.plot(p[:, 0], p[:, 1], color=colour, lw=0.8, alpha=0.40, zorder=2)
        curves.append(np.column_stack([
            np.interp(np.linspace(0, 1, 120), np.linspace(0, 1, len(p)), p[:, k])
            for k in (0, 1)]))
    if curves:
        m = np.mean(curves, axis=0)
        ax.plot(m[:, 0], m[:, 1], color=colour, lw=2.6, zorder=4 + which)
    return n_bad


def main():
    d = correct.WRIST_OFFSET_M["deadlift"]
    stats = []
    fig = plt.figure(figsize=(17.0, 15.0))
    gs = fig.add_gridspec(3, 4, height_ratios=[1.0, 1.0, 0.72], hspace=0.34,
                          wspace=0.26)
    axes = [fig.add_subplot(gs[r, c]) for r in (0, 1) for c in range(4)]
    for ax, stem in zip(axes, CLEAN):
        csv = ROOT / "data_v2" / "raw" / f"{stem}.csv"
        video = pipeline.find_video(csv)
        base = pipeline.run(csv, video=video)
        cut = oracle.jump_period_windows(base, wrist_offset=d, final_cut_s=0.08)
        v_ship = base["vs_truth"]
        v_cut = metrics.vs_truth(cut, video)

        p_ship, p_cut = curves(v_ship), curves(v_cut)
        vids = [np.column_stack([
            np.interp(np.linspace(0, 1, 120), np.linspace(0, 1, len(v)), v[:, k])
            for k in (0, 1)]) for v, _ in p_ship]
        for v, _ in p_ship:
            ax.plot(v[:, 0], v[:, 1], color=C_VID, lw=0.8, alpha=0.35, zorder=3)
        if vids:
            mv = np.mean(vids, axis=0)
            ax.plot(mv[:, 0], mv[:, 1], color=C_VID, lw=2.6, zorder=6)
        b_ship = draw(ax, p_ship, C_SHIP, which=1)
        b_cut = draw(ax, p_cut, C_CUT, which=2)
        stats.append((stem, v_ship, v_cut, b_ship, b_cut))

        ax.plot([], [], color=C_VID, lw=2.2, label="video (the bar)")
        ax.plot([], [], color=C_SHIP, lw=2.2,
                label=f"ship  h {v_ship['pipeline_h_rms']:.2f}  v {v_ship['pipeline_v_rms']:.2f}")
        ax.plot([], [], color=C_CUT, lw=2.2,
                label=f"cut   h {v_cut['pipeline_h_rms']:.2f}  v {v_cut['pipeline_v_rms']:.2f}")
        if b_cut:
            ax.plot([], [], color="#e74c3c", lw=2.6, alpha=0.4,
                    label=f"{b_cut} rep(s) outside 40-61 cm")
        name = stem.replace("deadlift_", "").split("_2026")[0]
        date = stem.split("_2026")[1][:4]
        ax.set_title(f"{name}   {date}", fontsize=10, loc="left")
        ax.legend(fontsize=6.8, loc="lower right", framealpha=0.9)
        ax.grid(alpha=0.25)
        ax.set_xlabel("fore-aft, cm", fontsize=9)
        ax.set_ylabel("height, cm", fontsize=9)
        ax.tick_params(labelsize=8)
        print(f"  {name:12} ship {v_ship['pipeline_h_rms']:5.2f} "
              f"cut {v_cut['pipeline_h_rms']:5.2f} "
              f"({v_ship['n_compared']}->{v_cut['n_compared']} reps)", flush=True)

    # ---- summary row: the trade, on both axes -----------------------------
    names = [s_[0].replace("deadlift_", "").split("_2026")[0] for s_ in stats]
    x = np.arange(len(stats))
    axh = fig.add_subplot(gs[2, :2])
    axh.bar(x - 0.19, [s_[1]["pipeline_h_rms"] for s_ in stats], 0.38,
            color=C_SHIP, label="shipping", zorder=3)
    axh.bar(x + 0.19, [s_[2]["pipeline_h_rms"] for s_ in stats], 0.38,
            color=C_CUT, label="final cut", zorder=3)
    axh.set_xticks(x); axh.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    axh.set_ylabel("horizontal rms, cm"); axh.legend(fontsize=8)
    axh.axhline(1.0, color="#7f8c8d", ls="--", lw=1.2)
    axh.text(-0.4, 1.15, "1 cm spec", fontsize=7.5, color="#7f8c8d")
    axh.set_title("HORIZONTAL — better on 7 of 8, median 2.78 -> 2.03 cm",
                  fontsize=10.5, loc="left")
    axh.grid(alpha=0.25, axis="y")

    axv = fig.add_subplot(gs[2, 2:])
    axv.bar(x - 0.19, [s_[1]["pipeline_v_rms"] for s_ in stats], 0.38,
            color=C_SHIP, zorder=3)
    axv.bar(x + 0.19, [s_[2]["pipeline_v_rms"] for s_ in stats], 0.38,
            color=C_CUT, zorder=3)
    axv.axhspan(0, 3.0, color="#27ae60", alpha=0.12, zorder=0)
    axv.text(-0.4, 3.2, "+/-2-3 cm spec", fontsize=7.5, color="#1e8449")
    axv.set_xticks(x); axv.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    axv.set_ylabel("vertical rms, cm")
    axv.set_title("VERTICAL — the cost H24 did not report: 2.88 -> 5.15 cm,\n"
                  "and 0 of 36 reps out of the ROM band becomes 6 of 36",
                  fontsize=10.5, loc="left")
    axv.grid(alpha=0.25, axis="y")

    fig.suptitle("H24b · Deadlift bar paths under the final cut — thin = every "
                 "rep, bold = the arm's mean, RED halo = a rep outside the "
                 "40-61 cm ROM band\n"
                 "aligned by start point (step 9). The horizontal axis spans a "
                 "few cm against half a metre of lift, so it is magnified — and "
                 "it is the axis the project exists to draw.",
                 fontsize=12.5, y=0.985)
    out = Path(__file__).with_suffix(".png")
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

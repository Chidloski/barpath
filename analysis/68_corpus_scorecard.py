"""H17 — every set in the corpus, on one page (2026-08-17).

Renders `analysis/68_corpus_scorecard.png`. Run from the repo root:

    python analysis/68_corpus_scorecard.py            # recompute, ~4 min
    python analysis/68_corpus_scorecard.py --cache    # reuse the last sweep

All 29 captures, scored the way the pipeline ships: step 6 on, H14's tape scale,
B4's derived sign. The three singles that `pipeline.run` cannot sync go through
`shortset.run`, which is how G3 scored them; the two 2026-08-13 spoto benches
are not scored at all, because their footage does not track.

**Panel B is the one that is new, and it needs no video.** Mean concentric
velocity against bar load, one point per set, taken from REP 1 so that
within-set fatigue cannot confound it. The load-velocity relationship is the
most robust fact in strength training — heavier bar, slower bar — and it is an
external check the IMU can be held to without a camera, a tracker or a sync.
Bench and deadlift reproduce it at r = -0.92 and -0.91.

The contrast with panel A is the finding. Deadlift has the BEST velocity channel
in the corpus and the WORST horizontal position channel: 1 of 10 sets beat a
flat vertical line, against bench's 6 of 7 and squat's 9 of 10. Same sensor,
same captures, same nine steps. So P2's deadlift failure is specific to fore-aft
POSITION, and is not the sensor, the attitude or the vertical integration —
which is what P6 and C11 concluded from the momentum side, reached here from a
direction that never touches the video.

Panel C is the same IMPACT/SMOOTH split `FINDINGS.md` draws from invented fore-aft,
measured instead on a real quantity: deadlift MCV barely decays within a set
(median -2.4%) where bench sheds -26%. That is also WHY panel B's deadlift fit
needed no fatigue control while bench's improved from -0.77 to -0.92 under one.
"""
import json
import re
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

CACHE = Path(__file__).with_suffix(".json")
LIFT_C = {"bench": "#1b6ca8", "squat": "#c2571a", "deadlift": "#2e7d32"}
LIFTS = ("bench", "squat", "deadlift")

# The one capture excluded from every velocity statistic below. It is the
# labelled single the segmenter gives TWO windows, so its second "rep" is the
# bar being dropped; its MCV is not a rep's MCV. See P1 and TASKS.md H15.
MISCOUNT_SINGLE = "deadlift_210x1_20260815_132206"


# --------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------

def sweep() -> list[dict]:
    """Score every capture. Read-only over `src/` and `data_v2/`."""
    from src import capture, display, pipeline, shortset, tracked

    rows = []
    for csv in sorted((ROOT / "data_v2" / "raw").glob("*.csv")):
        stem = csv.stem
        m = re.match(r"^([a-z_]+?)_([\d.]+)x(\d+)", stem)
        d = re.search(r"_(\d{8})_\d+$", stem)
        row = {"stem": stem, "date": d.group(1) if d else None,
               "load_kg": float(m.group(2)) if m else None,
               "label_reps": int(m.group(3)) if m else None,
               "lift": capture.lift_of(csv)}
        print(f"  {stem}", flush=True)

        video = pipeline.find_video(csv)
        if video is not None:
            try:
                rev = tracked.review(video)
                row["vid_travel_cm"] = float(rev["travel_cm"])
                row["vid_implausible"] = bool(rev["implausible"])
            except Exception as e:
                row["vid_error"] = f"{type(e).__name__}: {e}"

        res = pipeline.run(csv, video=video)
        row["imu_reps"] = len(res["bounds"])
        row["rep_rom_cm"] = [100 * v for v in res["rep_rom_m"]]
        lo, hi = capture.VERTICAL_ROM_M[row["lift"]]
        row["rom_out_of_band"] = sum(
            1 for v in row["rep_rom_cm"] if not (100 * lo <= v <= 100 * hi))

        # per-rep display numbers, off the same planar curves the plot draws
        t = res["log"]["t"]
        stats = []
        for curve, (a, b) in zip(res["planar"], res["bounds"]):
            curve = np.asarray(curve, float)
            if curve.ndim != 2 or len(curve) < 8:
                continue
            stats.append(display.rep_stats(curve, t[a:b][:len(curve)]))
        mcv = [s["mean_concentric_v"] for s in stats
               if np.isfinite(s["mean_concentric_v"])]
        row["mcv"] = mcv
        row["mcv_first"] = mcv[0] if mcv else None
        row["mcv_median"] = float(np.median(mcv)) if mcv else None
        row["mcv_drop_pct"] = (100 * (mcv[-1] - mcv[0]) / mcv[0]
                               if len(mcv) > 1 else None)

        vs = res.get("vs_truth")
        if vs is None and row["label_reps"] == 1:
            vs = shortset.run(csv, video=video).get("vs_truth")
            row["scored_via"] = "shortset"
        if vs:
            for k in ("pipeline_h_rms", "pipeline_v_rms", "null_h_rms",
                      "beats_null", "reps_disagreeing_on_sign",
                      "sign_agrees_with_geometry"):
                v = vs.get(k)
                row[k] = (float(v) if isinstance(v, (int, float, np.floating))
                          and not isinstance(v, bool) else v)
        rows.append(row)
    return rows


def load(use_cache: bool) -> list[dict]:
    if use_cache and CACHE.is_file():
        return json.loads(CACHE.read_text())
    rows = sweep()
    CACHE.write_text(json.dumps(rows, indent=1))
    return rows


# --------------------------------------------------------------------------
# the panels
# --------------------------------------------------------------------------

def panel_a(ax, rows):
    """beats_null per set, grouped by lift. The headline."""
    y, seen = 0, []
    for lift in LIFTS:
        got = sorted((r for r in rows if r["lift"] == lift
                      and r.get("beats_null") is not None),
                     key=lambda r: r["beats_null"])
        for r in got:
            bn = r["beats_null"]
            ax.barh(y, bn, color=LIFT_C[lift],
                    alpha=1.0 if bn >= 1.0 else 0.35,
                    edgecolor=LIFT_C[lift], linewidth=1.0)
            lab = r["stem"].split("_2026")[0]
            if r["stem"] == MISCOUNT_SINGLE:
                lab += "  (miscounted)"
            ax.text(-0.05, y, lab, ha="right", va="center", fontsize=6.0)
            y += 1
        seen.append((lift, y))
        y += 0.8
    ax.axvline(1.0, color="k", lw=1.2, zorder=5)
    ax.set_xlim(0, 3.6)
    ax.set_ylim(-1, y)
    ax.set_xlabel("beats_null  (>1 = better than drawing no fore-aft at all)")
    ax.set_yticks([])
    prev = -0.6
    for lift, top in seen:
        n = sum(1 for r in rows if r["lift"] == lift
                and r.get("beats_null") is not None)
        w = sum(1 for r in rows if r["lift"] == lift
                and (r.get("beats_null") or 0) >= 1.0)
        ax.text(3.5, (prev + top - 1) / 2, f"{lift}\n{w}/{n} beat",
                ha="right", va="center", fontsize=7.5, color=LIFT_C[lift],
                weight="bold")
        prev = top
    ax.set_title("A  the horizontal, per set: lift is the discriminator",
                 fontsize=9, loc="left")


def panel_b(ax, rows):
    """Load against rep-1 MCV. No video anywhere in this panel."""
    txt = []
    for lift in LIFTS:
        pts = [(r["load_kg"], r["mcv_first"]) for r in rows
               if r["lift"] == lift and r.get("mcv_first")
               and r["stem"] != MISCOUNT_SINGLE]
        L = np.array([p[0] for p in pts])
        V = np.array([p[1] for p in pts])
        ax.scatter(L, V, s=34, color=LIFT_C[lift], label=lift, zorder=3)
        r_, p_ = pearsonr(L, V)
        b, a = np.polyfit(L, V, 1)
        xs = np.linspace(L.min(), L.max(), 20)
        ax.plot(xs, a + b * xs, color=LIFT_C[lift], lw=1.4, alpha=0.7)
        txt.append(f"{lift}: r={r_:+.2f} (p={p_:.3f})")
    ax.set_xlabel("bar load (kg)")
    ax.set_ylabel("mean concentric velocity, REP 1 (m/s)")
    ax.legend(fontsize=7, loc="upper right")
    ax.text(0.02, 0.03, "\n".join(txt), transform=ax.transAxes, fontsize=7,
            va="bottom", family="monospace")
    ax.set_title("B  heavier bar, slower bar — checked WITHOUT the video",
                 fontsize=9, loc="left")


def panel_c(ax, rows):
    """Within-set MCV decay, the IMPACT/SMOOTH split on a real quantity."""
    data, labels, colours = [], [], []
    for lift in LIFTS:
        d = [r["mcv_drop_pct"] for r in rows if r["lift"] == lift
             and r.get("mcv_drop_pct") is not None
             and r["stem"] != MISCOUNT_SINGLE]
        data.append(d)
        labels.append(f"{lift}\nn={len(d)}")
        colours.append(LIFT_C[lift])
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True,
                    widths=0.55)
    for patch, c in zip(bp["boxes"], colours):
        patch.set_facecolor(c)
        patch.set_alpha(0.35)
    for i, (d, c) in enumerate(zip(data, colours), start=1):
        ax.scatter(np.full(len(d), i) + np.random.uniform(-.09, .09, len(d)),
                   d, s=18, color=c, zorder=3)
    ax.axhline(0, color="k", lw=0.8, ls=":")
    ax.set_ylabel("MCV change, first rep to last (%)")
    ax.set_title("C  fatigue within a set — deadlift barely decays",
                 fontsize=9, loc="left")


def panel_d(ax, rows):
    """Counting and extent, every capture. Where the corpus is still red."""
    y = 0
    for lift in LIFTS:
        for r in sorted((x for x in rows if x["lift"] == lift),
                        key=lambda x: (x["date"] or "", x["stem"])):
            ok_count = r["imu_reps"] == r["label_reps"]
            ok_rom = r["rom_out_of_band"] == 0
            ok_vid = not r.get("vid_implausible", False)
            for i, ok in enumerate((ok_count, ok_rom, ok_vid)):
                ax.add_patch(plt.Rectangle(
                    (i, y - .40), .86, .8,
                    facecolor=LIFT_C[lift] if ok else "#ffffff",
                    edgecolor=LIFT_C[lift] if ok else "#c62828",
                    alpha=1.0 if ok else 1.0, lw=1.4, hatch=None if ok else "//"))
            ax.text(-0.12, y, r["stem"].split("_2026")[0] + "  " +
                    (r["date"] or "")[4:], ha="right", va="center", fontsize=5.6)
            y += 1
        y += 0.6
    ax.set_xlim(-3.4, 3.0)
    ax.set_ylim(-1, y)
    ax.set_xticks([0.43, 1.43, 2.43])
    ax.set_xticklabels(["rep\ncount", "per-rep\nROM band", "video\ntracks"],
                       fontsize=7)
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.add_patch(plt.Rectangle((0, y - .3), .5, .5, facecolor="#666666"))
    ax.text(0.62, y - .05, "passes", fontsize=6.5, va="center")
    ax.add_patch(plt.Rectangle((1.5, y - .3), .5, .5, facecolor="#ffffff",
                               edgecolor="#c62828", lw=1.4, hatch="//"))
    ax.text(2.12, y - .05, "fails", fontsize=6.5, va="center")
    ax.set_title("D  what is still red: 7 cells over 6 captures, 23 of 29 clean",
                 fontsize=9, loc="left")


def panel_e(ax, rows):
    """Horizontal rms against the 1 cm spec."""
    for lift in LIFTS:
        pts = [(r["pipeline_h_rms"], r["null_h_rms"]) for r in rows
               if r["lift"] == lift and r.get("pipeline_h_rms")]
        ax.scatter([p[1] for p in pts], [p[0] for p in pts], s=34,
                   color=LIFT_C[lift], label=lift, zorder=3)
    lim = 22
    ax.plot([0, lim], [0, lim], color="k", lw=1.0,
            label="= the flat-line null")
    ax.axhline(1.0, color="#c62828", lw=1.2, ls="--", label="1 cm spec")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(0.4, lim)
    ax.set_ylim(0.4, 45)
    ax.set_xlabel("null_h_rms — error of drawing a straight line (cm)")
    ax.set_ylabel("pipeline_h_rms (cm)")
    ax.legend(fontsize=6.5, loc="upper left")
    ax.set_title("E  nothing is inside the 1 cm spec", fontsize=9, loc="left")


def main(argv) -> int:
    rows = load("--cache" in argv)
    scored = [r for r in rows if r.get("beats_null") is not None]
    print(f"{len(rows)} sets, {len(scored)} scored, "
          f"{sum(r['label_reps'] for r in rows)} labelled reps")

    fig = plt.figure(figsize=(15.5, 16.5))
    gs = fig.add_gridspec(3, 3, height_ratios=[1.45, 0.95, 1.60],
                          hspace=0.30, wspace=0.30,
                          left=0.13, right=0.975, top=0.945, bottom=0.030)
    panel_a(fig.add_subplot(gs[0, :2]), rows)
    panel_d(fig.add_subplot(gs[0, 2]), rows)
    panel_b(fig.add_subplot(gs[1, 0]), rows)
    panel_c(fig.add_subplot(gs[1, 1]), rows)
    panel_e(fig.add_subplot(gs[1, 2]), rows)

    ax = fig.add_subplot(gs[2, :])
    ax.axis("off")
    ax.text(0.0, 1.0, TABLE(rows), va="top", ha="left", fontsize=6.4,
            family="monospace", transform=ax.transAxes)

    fig.suptitle("H17 — all 29 sets of the corpus, as the pipeline ships "
                 "(step 6 on, H14 scale, B4 sign)",
                 fontsize=12, weight="bold", x=0.013, ha="left", y=0.982)
    out = ROOT / "analysis" / "68_corpus_scorecard.png"
    fig.savefig(out, dpi=104)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def TABLE(rows) -> str:
    head = (f"{'capture':32}{'date':>9}{'reps':>7}{'ROM med':>9}{'h rms':>8}"
            f"{'null':>7}{'beats':>7}{'v rms':>8}{'MCV1':>7}{'MCV drop':>10}")
    out = [head, "-" * len(head)]
    for lift in LIFTS:
        for r in sorted((x for x in rows if x["lift"] == lift),
                        key=lambda x: (x["date"] or "", x["stem"])):
            def f(k, w=8, p=2):
                v = r.get(k)
                return " " * w if v is None else f"{v:{w}.{p}f}"
            reps = f"{r['imu_reps']}/{r['label_reps']}"
            if r["imu_reps"] != r["label_reps"]:
                reps += "*"
            rom = np.median(r["rep_rom_cm"]) if r["rep_rom_cm"] else np.nan
            drop = r.get("mcv_drop_pct")
            out.append(
                f"{r['stem'].split('_2026')[0][:31]:32}{r['date'] or '':>9}"
                f"{reps:>7}{rom:>9.1f}{f('pipeline_h_rms')}{f('null_h_rms',7)}"
                f"{f('beats_null',7)}{f('pipeline_v_rms')}"
                f"{f('mcv_first',7,3)}"
                f"{'' if drop is None else format(drop,'+9.1f')+'%':>10}")
        out.append("")
    out.append("* = rep count disagrees with the label (P1, still open).  "
               "blank score = footage does not track.  "
               "MCV drop = rep 1 to last rep.")
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

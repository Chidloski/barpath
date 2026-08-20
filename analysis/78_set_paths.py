"""H28 — every set's bar path, pipeline against video: the set average and each rep.

**What this draws, and why both halves are here.** For every scoreable capture
in `data_v2/raw` there is one ROW: the leftmost panel is the set's AVERAGE rep,
reconstruction against video, and the panels to its right are the individual
reps, same comparison, one per panel. The average is what a product would draw;
the reps are what it is hiding. Reading them side by side is the point — a
tidy average over four scattered reps and a tidy average over four tight ones
look identical in the left-hand panel and mean completely different things.

Nothing here is a new measurement. Every curve is `metrics.vs_truth`'s own
per-rep output (`curve_video`, `curve_pipeline`), already paired, resampled and
aligned by the scoring path; this module chooses no correspondence of its own.

**The average uses TURNAROUND alignment, which is H13's result and not a
preference.** `display.average_rep` resamples each rep about its own turnaround
rather than on a uniform time grid, and H13 measured that this is where the
whole of the averaging gain lives — vertical 8.30 cm to 3.00. Averaging on a
time grid would draw a smeared curve and understate the pipeline.

**The odd rep is LABELLED, not dropped** (`exclude=False`). H13 measured that
excluding the anomalous rep makes the average WORSE, 1.52 -> 1.70 cm, because
the odd rep is usually a real one: on every set where the IMU flags a rep the
video flags that rep too. A display that silently deletes a rep will one day
delete a good one.

**Read the horizontal axis with the spec in mind.** Fore-aft excursion is a few
centimetres against half a metre of lift, so every panel is drawn on its own
axes and the horizontal is magnified relative to the vertical — that is step 9's
4x stretch and it is why ~1 cm is the target. It also means a horizontal
disagreement that looks alarming here is a centimetre or two on the bar.

Two things are marked rather than silently handled:

* `deadlift_160x6_1_20260818` is the one STRAPPED capture in the corpus (H20).
  The watch was not rigidly indexed to the wrist and it invents 3-4x the
  fore-aft travel the bar had. It is drawn, and it is labelled, because hiding
  it would misrepresent the corpus and dropping it silently would misrepresent
  the median.
* A set whose `beats_null` is below 1.0 is losing to drawing NO fore-aft motion
  at all — a straight vertical line. That is most deadlifts. The row label says
  so, because a path that looks plausible and loses to a flat line is the exact
  failure this project keeps rediscovering.

Six captures have no `.mov` on disk any more but every one has a committed
tracked path in `data_v2/tracked/`, so they score identically; this script
resolves the clip by NAME from the cache rather than requiring the file. That
is the cache doing what C31 built it for.

    python analysis/78_set_paths.py

Writes `analysis/78_set_paths_<lift>.png`, one per lift.
"""
import sys
import warnings
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src import capture, display, pipeline, shortset

RAW = ROOT / "data_v2" / "raw"
VIDEO = ROOT / "data_v2" / "video"
TRACKED = ROOT / "data_v2" / "tracked"

STRAPPED = "deadlift_160x6_1_20260818"        # H20: the watch could move
C_VID, C_PIPE, C_ODD = "#111111", "#2980b9", "#e67e22"


def clip_for(csv: Path) -> Path | None:
    """The clip's path, whether or not the file is still on disk.

    `pipeline.find_video` requires the `.mov` to exist. Six captures no longer
    have one locally and all six have a COMMITTED tracked path, which is the
    only thing scoring needs, so pair against the cache instead and hand back
    the name the cache is keyed by.
    """
    v = pipeline.find_video(csv)
    if v is not None:
        return v
    hits = sorted((c for c in TRACKED.glob("*.csv") if csv.stem.startswith(c.stem)),
                  key=lambda c: len(c.stem), reverse=True)
    return VIDEO / f"{hits[0].stem}.mov" if hits else None


def collect() -> list[dict]:
    rows = []
    for csv in sorted(RAW.glob("*.csv")):
        video = clip_for(csv)
        if video is None:
            print(f"  {csv.stem:44} no clip — skipped", flush=True)
            continue
        try:
            # `shortset.run` and NOT `pipeline.run`: on three reps or more it is
            # `pipeline.run` exactly, and on a one- or two-rep set it supplies
            # the clock a short set can actually support (G3). Using the plain
            # pipeline here refuses every single in the corpus.
            res = shortset.run(csv, video=video)
            vs = res.get("vs_truth")
            if vs is None:
                raise ValueError("; ".join(res.get("blocked") or ["no vs_truth"]))
        except Exception as exc:
            print(f"  {csv.stem:44} not scoreable — {type(exc).__name__}: "
                  f"{str(exc)[:60]}", flush=True)
            continue

        reps = [r for r in (vs.get("per_rep") or []) if r.get("covered")]
        pairs = []
        for r in reps:
            v = np.asarray(r["curve_video"], float) * 100.0
            p = np.asarray(r["curve_pipeline"], float) * 100.0
            if v.ndim == 2 and len(v) >= 8:
                pairs.append((v, p, r))
        if not pairs:
            print(f"  {csv.stem:44} no covered reps — skipped", flush=True)
            continue

        rows.append({"stem": csv.stem, "lift": capture.lift_of(csv.stem),
                     "vs": vs, "pairs": pairs})
        print(f"  {csv.stem:44} {len(pairs)} reps  h {vs['pipeline_h_rms']:5.2f} "
              f"v {vs['pipeline_v_rms']:5.2f}  bn {vs['beats_null']:.2f}", flush=True)
    return rows


def averaged(pairs):
    """Set-average video and pipeline curves, plus the odd-rep mask.

    Both sides go through the SAME averager so the comparison is like for like:
    a difference in the left-hand panel is the reconstruction, never the
    averaging. `exclude=False` per H13 — the flag is a label.

    The odd-rep mask is computed from the PIPELINE grid, not the video's, on
    purpose: it is what a product could actually flag, having only the watch.
    H13 measured that this is a fair thing to show — 5 IMU flags against 6
    video flags, and on every set where the IMU fires the video fires on that
    rep too.
    """
    vids = [v for v, _, _ in pairs]
    pipes = [p for _, p, _ in pairs]
    av = display.average_rep(vids, method="median", align="turnaround",
                             exclude=False)
    ap = display.average_rep(pipes, method="median", align="turnaround",
                             exclude=False)
    odd = display.flag_anomalies(ap["grid"]) if len(pipes) >= 3 \
        else np.zeros(len(pipes), dtype=bool)
    return av["average"], ap["average"], odd


def draw_pair(ax, v, p, title, odd=False):
    v = v - v[0]
    p = p - p[0]                                   # step 9: align by start
    ax.plot(v[:, 0], v[:, 1], color=C_VID, lw=1.9, zorder=3, label="video")
    ax.plot(p[:, 0], p[:, 1], color=C_ODD if odd else C_PIPE, lw=1.9, zorder=4,
            label="pipeline")
    ax.set_title(title, fontsize=8.0, loc="left",
                 color=C_ODD if odd else "#2c3e50")
    ax.grid(alpha=0.22)
    ax.tick_params(labelsize=6.5)


def render(lift: str, rows: list[dict]) -> Path:
    ncol = 1 + max(len(r["pairs"]) for r in rows)
    nrow = len(rows)
    fig, axes = plt.subplots(nrow, ncol, figsize=(2.35 * ncol, 2.5 * nrow),
                             squeeze=False)

    for i, row in enumerate(rows):
        vs, pairs = row["vs"], row["pairs"]
        av, ap, odd = averaged(pairs)

        ax = axes[i][0]
        draw_pair(ax, av, ap, f"AVERAGE of {len(pairs)} "
                  f"rep{'' if len(pairs) == 1 else 's'}")
        ax.set_facecolor("#f4f6f7")
        ax.legend(fontsize=6.0, loc="lower right", framealpha=0.9)

        # the row's identity, and the two warnings that must not be silent
        bn = vs["beats_null"]
        flags = []
        if bn < 1.0:
            flags.append(f"LOSES to a flat line ({bn:.2f})")
        if STRAPPED in row["stem"]:
            flags.append("STRAPPED — H20, do not referee")
        label = (f"{row['stem'].replace('_' + row['stem'].split('_')[-1], '')}\n"
                 f"h {vs['pipeline_h_rms']:.2f} cm   v {vs['pipeline_v_rms']:.2f} cm"
                 f"   beats_null {bn:.2f}")
        if flags:
            label += "\n" + "  ·  ".join(flags)
        ax.text(-0.26, 0.5, label, transform=ax.transAxes, fontsize=7.4,
                va="center", ha="right", linespacing=1.5,
                color="#c0392b" if flags else "#2c3e50")

        for j in range(1, ncol):
            ax = axes[i][j]
            if j - 1 >= len(pairs):
                ax.axis("off")
                continue
            v, p, r = pairs[j - 1]
            draw_pair(ax, v, p,
                      f"rep {j}   h {r['pipeline_h_rms']:.2f}  "
                      f"v {r['pipeline_v_rms']:.2f}", odd=bool(odd[j - 1]))
            if i == nrow - 1:
                ax.set_xlabel("fore-aft, cm", fontsize=7.5)
                if j == 1:
                    ax.set_ylabel("height, cm", fontsize=7.5)

    fig.suptitle(
        f"H28 · {lift.upper()} — every set, reconstruction against video. "
        f"Left panel is the set AVERAGE, the rest are its reps.\n"
        "Black is the bar as the video saw it; blue is the reconstruction; "
        "ORANGE marks the rep the display would flag as the odd one (labelled, "
        "never dropped — H13).\n"
        "Each panel is on its own axes and the fore-aft axis is magnified "
        "against the vertical, which is step 9's 4x stretch and why the spec "
        "is ~1 cm. Reps aligned by start point; the average by TURNAROUND (H13).",
        fontsize=11.0, y=1.0 - 0.004 * (12.0 / max(nrow, 1)))
    fig.tight_layout(rect=(0.13, 0, 1, 0.985))
    out = ROOT / "analysis" / f"78_set_paths_{lift}.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    print("scoring every capture in data_v2/raw ...", flush=True)
    rows = collect()
    if not rows:
        print("nothing scoreable")
        return 1
    by_lift = defaultdict(list)
    for r in rows:
        by_lift[r["lift"]].append(r)

    print()
    for lift in sorted(by_lift):
        out = render(lift, by_lift[lift])
        print(f"wrote {out.relative_to(ROOT)}  ({len(by_lift[lift])} sets)")

    n_sets = len(rows)
    n_reps = sum(len(r["pairs"]) for r in rows)
    lost = [r["stem"] for r in rows if r["vs"]["beats_null"] < 1.0]
    print(f"\n{n_sets} sets, {n_reps} reps drawn")
    print(f"{len(lost)} of {n_sets} sets lose to the flat-line null:")
    for s in lost:
        print(f"   {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

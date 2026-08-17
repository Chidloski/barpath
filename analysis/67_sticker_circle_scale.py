"""H14 — the sticker circle, measured with a tape (2026-08-17).

Renders `analysis/67_sticker_circle_scale.png`. Run from the repo root:

    python analysis/67_sticker_circle_scale.py

Panel A is the geometry the owner measured and is the whole argument: a 2.0 cm
sticker placed with its outer edge on the rim puts its CENTRE 1.0 cm inboard, so
the circle the tracker fits is the plate diameter less 2.0 cm — a constant
absolute inset, which is why no single FRACTION of the plate could ever be right
for two plate sizes at once.

Panels B-D are the consequence on all sixteen `data_v2` captures, before against
after. B is the check that is independent of the tape: the video's per-rep
vertical ROM over the IMU's, which sat below 1.0 on 16 of 16 captures and had no
per-lift explanation.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TMP = Path("/Users/sam/.claude/jobs/874a041a/tmp")
LIFT_C = {"bench": "#1b6ca8", "squat": "#c2571a", "deadlift": "#2e7d32"}


def _load(name):
    return {r["capture"]: r for r in json.loads((TMP / name).read_text())}


def _ratio(r):
    v = r.get("video_rom_cm")
    if v is None or "imu_rom_lo_cm" not in r:
        return None
    v = float(np.mean(v)) if isinstance(v, list) else float(v)
    return v / ((r["imu_rom_lo_cm"] + r["imu_rom_hi_cm"]) / 2.0)


def main() -> int:
    before, after = _load("before.json"), _load("after.json")
    stems = [s for s in sorted(before) if s in after]

    fig = plt.figure(figsize=(15.5, 9.5))
    gs = fig.add_gridspec(2, 3, hspace=0.34, wspace=0.26,
                          left=0.06, right=0.985, top=0.90, bottom=0.09)

    # --- A: the geometry ------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    plate_d, sticker_d = 0.425, 0.020
    R = plate_d / 2
    ax.add_patch(plt.Circle((0, 0), R, fc="#3a3a3a", ec="k", lw=1.4))
    meas = R - sticker_d / 2
    # What SHIPPED, which is not 0.858 x this plate: vtrack multiplied the
    # BUMPER's 0.445 by 0.858 on deadlift and 0.45 on bench and squat.
    old = 0.445 * 0.858 / 2
    for k in range(8):
        a = np.pi / 2 + k * np.pi / 4
        ax.add_patch(plt.Circle((meas * np.cos(a), meas * np.sin(a)),
                                sticker_d / 2, fc="white", ec="#888", lw=0.8))
        ax.add_patch(plt.Circle((meas * np.cos(a), meas * np.sin(a)),
                                0.013 / 2, fc="#dfe8f5", ec="none"))
    ax.add_patch(plt.Circle((0, 0), meas, fc="none", ec="#0b8043", lw=2.2))
    ax.add_patch(plt.Circle((0, 0), old, fc="none", ec="#c62828", lw=2.2,
                            ls="--"))
    ax.annotate("", xy=(0, R), xytext=(0, meas),
                arrowprops=dict(arrowstyle="<->", color="#0b8043", lw=1.4))
    ax.text(0.028, (R + meas) / 2 + 0.004, "1.0 cm = sticker radius",
            fontsize=8, color="#0b8043", va="bottom")
    ax.plot([], [], color="#0b8043", lw=2.2,
            label=f"MEASURED circle  {100*2*meas:.1f} cm\n(plate − 2 cm)")
    ax.plot([], [], color="#c62828", lw=2.2, ls="--",
            label=f"as SHIPPED  0.445 × 0.858\n= {100*2*old:.1f} cm (deadlift)")
    ax.set_xlim(-0.25, 0.25); ax.set_ylim(-0.25, 0.25)
    ax.set_aspect("equal"); ax.axis("off")
    ax.legend(loc="lower center", fontsize=7.5, frameon=False,
              bbox_to_anchor=(0.5, -0.14))
    ax.set_title("A. the geometry, on a 425 mm notched plate\n"
                 "sticker 2.0 cm overall, edge against the rim",
                 fontsize=9.5, loc="left")

    # --- B: video/IMU ROM ratio -----------------------------------------
    ax = fig.add_subplot(gs[0, 1:])
    xs = np.arange(len(stems))
    for i, s in enumerate(stems):
        rb, ra = _ratio(before[s]), _ratio(after[s])
        c = LIFT_C[before[s]["lift"]]
        if rb is None or ra is None:
            continue
        ax.plot([i, i], [rb, ra], color=c, lw=1.0, alpha=0.5)
        ax.plot(i, rb, "o", mfc="none", mec=c, ms=6)
        ax.plot(i, ra, "o", color=c, ms=6)
    ax.axhline(1.0, color="k", lw=1.0, ls=":")
    ax.set_xticks(xs)
    ax.set_xticklabels([s.rsplit("_", 2)[0] for s in stems], rotation=42,
                       ha="right", fontsize=6.5)
    ax.set_ylabel("video ROM / IMU ROM")
    ax.set_title("B. the check the tape does not touch — hollow = before, "
                 "filled = after.\nThe video read LOW on 16 of 16, median 0.93 "
                 "on all three lifts.", fontsize=9.5, loc="left")

    # --- C and D: what it does to the scored numbers ---------------------
    panels = ((fig.add_subplot(gs[1, 0]), "beats_null",
               "beats_null", "C. beats_null — ABOVE the line is BETTER.\n"
               "Median 1.25 -> 1.26, moved on 9 of 16."),
              (fig.add_subplot(gs[1, 1]), "pipeline_h_rms",
               "horizontal rms, cm", "D. horizontal — below the line is better.\n"
               "Median 2.17 -> 2.26 cm. The scale barely reaches it."),
              (fig.add_subplot(gs[1, 2]), "pipeline_v_rms",
               "vertical rms, cm", "E. VERTICAL — below the line is better.\n"
               "Median 3.92 -> 2.71 cm, better on 14 of 16."))
    for ax, key, lab, title in panels:
        for s in stems:
            b, a = before[s].get(key), after[s].get(key)
            if b is None or a is None:
                continue
            ax.plot(b, a, "o", color=LIFT_C[before[s]["lift"]], ms=7,
                    alpha=0.85)
        lim = ax.get_xlim() + ax.get_ylim()
        m = max(lim) * 1.05
        ax.plot([0, m], [0, m], "k:", lw=1.0)
        ax.set_xlim(0, m); ax.set_ylim(0, m)
        ax.set_xlabel(f"before — {lab}", fontsize=8)
        ax.set_ylabel(f"after — {lab}", fontsize=8)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9, loc="left")

    handles = [plt.Line2D([], [], color=c, marker="o", ls="", label=k)
               for k, c in LIFT_C.items()]
    fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False,
               fontsize=9)
    fig.suptitle("H14 — the sticker circle, measured with a tape rather than "
                 "fitted.  Scale +4.9% bench, +6.1% deadlift, +11.4% squat.",
                 fontsize=12, x=0.06, ha="left")
    out = ROOT / "analysis" / "67_sticker_circle_scale.png"
    fig.savefig(out, dpi=125)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

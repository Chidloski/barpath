"""Per-clip review figure: overlays you can LOOK at, plus the trajectory.

C31's protocol, and the reason it exists: six squat clips fed travel figures of
0.2 to 24.7 cm into scored comparisons from behind 96-100% coverage and healthy
residuals. Every summary statistic said fine. What caught it was a picture of
the path and a plausibility check against the lift's own range of motion. So a
figure here always shows the CONSTELLATION on real frames — not just a curve —
because a curve from furniture looks perfectly reasonable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from viz import frame_at


def review_figure(name, video, res, out):
    trk, sm = res["trk"], res["summary"]
    ok_idx = [i for i, t in enumerate(trk) if t is not None]
    if not ok_idx:
        return None
    # Four frames spread over the clip, preferring ones that tracked.
    picks = [ok_idx[int(f * (len(ok_idx) - 1))] for f in (0.1, 0.37, 0.63, 0.9)]

    fig = plt.figure(figsize=(15, 8.5), dpi=110)
    gs = fig.add_gridspec(2, 4, height_ratios=[2.1, 1.0], hspace=0.18,
                          wspace=0.12)

    for k, fi in enumerate(picks):
        ax = fig.add_subplot(gs[0, k])
        img = frame_at(video, fi)
        ax.imshow(img)
        t = trk[fi]
        th = np.linspace(0, 2 * np.pi, 180)
        ax.plot(t["cx"] + t["r"] * np.cos(th), t["cy"] + t["r"] * np.sin(th),
                color="#ff2d55", lw=1.3)
        ax.scatter(t["pts"][:, 1], t["pts"][:, 0], s=70, facecolors="none",
                   edgecolors="#00e5ff", lw=1.4)
        ax.plot([t["cx"]], [t["cy"]], "+", color="#ff2d55", ms=11, mew=1.6)
        # The path so far, so a hop is visible as a straight jump.
        ax.plot(sm["x_px"][:fi + 1], sm["y_px"][:fi + 1], color="#ffd60a",
                lw=1.0, alpha=0.85)
        ax.set_title(f"frame {fi} — {len(t['slots'])} markers", fontsize=8)
        ax.axis("off")

    axh = fig.add_subplot(gs[1, :2])
    axh.plot(sm["t"], sm["height_m"] * 100, color="#0a84ff", lw=1.2)
    axh.set_xlabel("time (s)", fontsize=8)
    axh.set_ylabel("height above lowest (cm)", fontsize=8)
    axh.grid(alpha=0.25)
    axh.tick_params(labelsize=7)
    axh.set_title(f"vertical — whole-clip travel {sm['travel_m']*100:.1f} cm",
                  fontsize=8)

    axx = fig.add_subplot(gs[1, 2])
    axx.plot(sm["fore_aft_m"] * 100, sm["height_m"] * 100, color="#30d158",
             lw=1.0)
    axx.set_xlabel("fore-aft (cm)", fontsize=8)
    axx.set_ylabel("height above lowest (cm)", fontsize=8)
    axx.grid(alpha=0.25)
    axx.tick_params(labelsize=7)
    axx.set_title("bar path", fontsize=8)

    axt = fig.add_subplot(gs[1, 3])
    axt.axis("off")
    s = res["score"]
    ru = res.get("runner_up")
    lines = [
        f"layout      {res['layout']}",
        f"radius      {res['r_px']:.1f} px",
        f"coverage    {sm['coverage']*100:.1f} %",
        f"markers     {s['slots']:.0f} median",
        f"fit rms     {sm['median_rms']:.2f} px",
        f"jitter      {s['jitter']:.2f} px/frame",
        f"travel      {sm['travel_m']*100:.1f} cm",
        f"scale       {sm['m_per_px']*1000:.2f} mm/px",
        "",
        f"score       {s['score']:.2f}",
        f"runner-up   {ru['score']:.2f}" if ru else "runner-up   -",
        "",
        "VERDICT     " + ("IMPLAUSIBLE" if res["implausible"] else "ok"),
    ]
    axt.text(0.0, 1.0, "\n".join(lines), va="top", ha="left", fontsize=8,
             family="monospace",
             color="#c00" if res["implausible"] else "#111")

    fig.suptitle(name, fontsize=11, y=0.97)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out

"""
Step 9 — rendering, plus diagnostic plots.

Display rules that follow from the spec:

  * Horizontal axis stretched ~4x. Half a metre of lift against a few
    centimetres of drift plots as a vertical line otherwise.
  * Reps overlaid, aligned by START POINT ONLY, rep 1 emphasised as the
    reference. Between-rep divergence is the product.
  * NO CENTIMETRE LABELS ON THE HORIZONTAL AXIS. Shape and difference are
    defensible; absolute horizontal distance is not something this system
    knows. The moment you print "2.3 cm forward" you have made a claim you
    cannot support.
  * Low-confidence sets are drawn WITHOUT the stretch. Stretching noise is
    how you invent faults.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

STRETCH = 4.0


def plot_paths(paths, confident: bool = True, title: str = "",
               ax=None, speeds=None):
    """Overlay rep paths. `paths` is a list of (M, 2) arrays: (along, up)."""
    if ax is None:
        _, ax = plt.subplots(figsize=(4.5, 7))

    for i, p in enumerate(paths):
        first = i == 0
        if speeds is not None:
            seg = np.stack([p[:-1], p[1:]], axis=1)
            lc = LineCollection(seg, cmap="viridis", linewidths=2.5 if first else 1.6)
            lc.set_array(speeds[i][:-1])
            lc.set_alpha(1.0 if first else 0.75)
            ax.add_collection(lc)
        else:
            ax.plot(p[:, 0], p[:, 1],
                    lw=2.5 if first else 1.4,
                    color="0.15" if first else None,
                    alpha=1.0 if first else 0.8,
                    label=f"rep {i+1}", zorder=3 if first else 2)

    ax.set_aspect(1.0 / STRETCH if confident else 1.0)
    ax.set_xticks([])                      # deliberate: no horizontal scale
    ax.set_ylabel("vertical (m)")
    ax.set_title(title + ("" if confident else "  [low confidence]"))
    ax.grid(alpha=0.25, axis="y")
    if speeds is None:
        ax.legend(fontsize=8, frameon=False)
    ax.autoscale_view()
    return ax


def plot_diagnostics(log: dict, position=None, mask=None, bounds=None):
    """Four-panel debugging view. Use this constantly while developing."""
    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True)
    t = log["t"]

    axes[0].plot(t, log["accel"], lw=0.7)
    axes[0].set_ylabel("accel (m/s²)")

    axes[1].plot(t, log["gyro"], lw=0.7)
    axes[1].set_ylabel("gyro (rad/s)")

    if position is not None:
        axes[2].plot(t, position[:, 2], lw=1.0, label="vertical")
        axes[2].plot(t, position[:, 0], lw=1.0, label="horizontal 1")
        axes[2].plot(t, position[:, 1], lw=1.0, label="horizontal 2")
        axes[2].legend(fontsize=8, frameon=False)
    axes[2].set_ylabel("position (m)")

    if mask is not None:
        axes[3].fill_between(t, 0, mask.astype(float), step="mid", alpha=0.4)
    if bounds is not None:
        for a, b in bounds:
            axes[3].axvline(t[a], color="k", lw=0.8)
            axes[3].axvline(t[min(b, len(t) - 1)], color="k", lw=0.8, ls=":")
    axes[3].set_ylabel("stationary")
    axes[3].set_xlabel("time (s)")

    fig.tight_layout()
    return fig


def plot_truth_comparison(recovered, truth, title=""):
    """Recovered against known truth, per axis.

    This used to say truth was "only possible on synthetic data". Not since
    A2 — src/truth.py tracks the plate from footage and gives an external
    horizontal reference on deadlift, which is what src/metrics.py compares
    against. Both sources work here: pass a synthetic pos_true, or a video path
    resampled onto the IMU clock.
    """
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    names = ["forward", "lateral", "vertical"]
    for k in range(3):
        axes[k].plot(truth[:, k], lw=2, color="0.7", label="truth")
        axes[k].plot(recovered[:, k], lw=1, color="crimson", label="recovered")
        err = np.abs(recovered[:, k] - truth[:, k]).max() * 100
        axes[k].set_title(f"{names[k]}  (max err {err:.2f} cm)")
        axes[k].legend(fontsize=8, frameon=False)
    fig.suptitle(title)
    fig.tight_layout()
    return fig

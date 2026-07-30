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


def plot_stages(results: dict, truth_paths: dict | None = None):
    """One column per lift, one row per stage. The pipeline, end to end.

    `results` maps a label to a `pipeline.run` dict; `truth_paths` optionally
    maps the same labels to `(t_imu, height)` from `truth.py`. Everything comes
    out of the result dict rather than being recomputed — that dict is
    deliberately fat so that a reader can see every intermediate, and this is
    the thing it was fat for.

    Written for someone learning what each stage does, so it is annotated
    rather than left to be inferred. The rows are chosen to make three points a
    table of numbers does not:

      row 0  the watch's axes tumble with the wrist; nothing is "up" yet
      row 2  reps are perfectly obvious in velocity, and so is the drift
      row 3  two integrations turn a small bias into METRES on a 60 cm lift
      row 4  what step 7 buys back, and on deadlift what it costs

    Vertical throughout, because it is the axis a reader can check against
    their own intuition about a lift. The horizontal axis — the one the spec is
    actually about — only appears at row 5, where it is the product.
    """
    labels = list(results)
    rows = [
        ("0  io.load_log", "body accel (m/s²)"),
        ("1-3  orient.to_world", "world vertical accel"),
        ("4  integrate", "vertical velocity (m/s)"),
        ("4  integrate", "vertical position (m)"),
        ("7  correct.detrend_set", "per-rep vertical (cm)"),
        ("8-9  project + plot", "height (cm)"),
    ]
    fig, axes = plt.subplots(len(rows), len(labels),
                             figsize=(5.0 * len(labels), 2.6 * len(rows)),
                             gridspec_kw={"height_ratios": [1, 1, 1, 1, 1, 1.7]})

    for col, label in enumerate(labels):
        r = results[label]
        log, bounds, reps = r["log"], r["bounds"], r["reps"]
        t = log["t"]
        truth_t = truth_h = None
        if truth_paths and label in truth_paths:
            truth_t, truth_h = truth_paths[label]

        # --- row 0: what the watch reports --------------------------------
        ax = axes[0, col]
        for k, name in enumerate("xyz"):
            ax.plot(t, log["accel"][:, k], lw=0.6, label=f"a{name}")
        ax.legend(fontsize=7, frameon=False, ncol=3)
        ax.set_title(f"{label}\n", fontsize=11, fontweight="bold")
        _pause(ax, r)

        # --- row 1: world frame, and the bias that gets removed -----------
        ax = axes[1, col]
        ax.plot(t, r["world_accel"][:, 2], lw=0.6, color="0.3")
        ax.axhline(0, color="0.7", lw=0.8)
        ax.axhline(-r["accel_bias"][2], color="crimson", lw=1.2, ls="--",
                   label=f"accel_bias {r['accel_bias'][2]:+.2f} m/s²")
        ax.legend(fontsize=7, frameon=False)
        _pause(ax, r)

        # --- row 2: velocity, where reps are obvious ----------------------
        ax = axes[2, col]
        ax.plot(t, r["velocity"][:, 2], lw=0.8, color="0.2")
        ax.axhline(0, color="0.7", lw=0.8)
        for a, b in bounds:
            ax.axvspan(t[a], t[min(b, len(t) - 1)], color="seagreen", alpha=0.16)
        ax.text(0.02, 0.9, f"{len(bounds)} reps found (green)", fontsize=8,
                transform=ax.transAxes, color="seagreen")

        # --- row 3: the runaway -------------------------------------------
        ax = axes[3, col]
        ax.plot(t, r["position"][:, 2], lw=1.0, color="crimson",
                label="reconstructed")
        span = float(np.ptp(r["position"][:, 2]))
        note = f"spans {span:.1f} m\n(the lift is ~0.6 m)"
        if truth_t is not None:
            ax.plot(truth_t, truth_h, lw=1.6, color="k", label="video truth")
            note += (f"\n\nthe black line IS the real bar,\n"
                     f"0-0.7 m. It looks flat because\n"
                     f"the red trace is {span/0.7:.0f}x its size.")
        ax.text(0.02, 0.96, note, fontsize=8, transform=ax.transAxes,
                color="crimson", va="top",
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5))
        ax.legend(fontsize=7, frameon=False, loc="lower left")

        # --- row 4: what the detrend recovers ------------------------------
        ax = axes[4, col]
        for i, rep in enumerate(reps):
            ax.plot(np.linspace(0, 1, len(rep)), rep[:, 2] * 100,
                    lw=1.6 if i == 0 else 1.0, alpha=1.0 if i == 0 else 0.7)
        ax.axhline(0, color="0.7", lw=0.8)
        ax.set_xlabel("fraction of rep")
        if "vs_truth" in r:
            ax.text(0.02, 0.88,
                    f"vs video: {r['vs_truth']['pipeline_v_rms']:.1f} cm rms",
                    fontsize=8, transform=ax.transAxes)

        # --- row 5: the product --------------------------------------------
        ax = axes[5, col]
        axis = np.real(r["axis"]) if "axis" in r else np.array([1.0, 0.0])
        for i, rep in enumerate(reps):
            along = (rep[:, :2] @ axis) * 100
            ax.plot(along - along[0], rep[:, 2] * 100,
                    lw=2.0 if i == 0 else 1.2, alpha=1.0 if i == 0 else 0.75)
        ax.set_aspect(1.0 / STRETCH)
        ax.set_xticks([])                    # deliberate: no horizontal scale
        ax.set_xlabel("fore-aft (stretched 4x, unlabelled by design)",
                      fontsize=8)
        if "vs_truth" in r:
            ax.text(0.02, 0.03,
                    f"horizontal error {r['vs_truth']['pipeline_h_rms']:.1f} cm rms "
                    f"— spec is 1 cm", fontsize=8, transform=ax.transAxes,
                    color="crimson")

        for row in (2, 3):
            axes[row, col].set_xlabel("time (s)")
        axes[4, col].set_xlabel("fraction of rep")

    # Stage and quantity share one label, so the two cannot collide when the
    # last row's aspect ratio narrows its axes.
    for row, (stage, ylab) in enumerate(rows):
        axes[row, 0].set_ylabel(f"step {stage}\n{ylab}", fontsize=9)

    fig.suptitle("The pipeline, stage by stage — one column per lift\n"
                 "Vertical axis throughout until the last row, because it is "
                 "the one you can check against what a lift feels like.",
                 fontsize=12)
    fig.tight_layout(rect=(0.015, 0, 1, 0.965))
    return fig


def _pause(ax, result):
    """Shade the pre-set calibration hold — where every bias estimate is made."""
    win = result.get("gyro_bias_info", {}).get("window")
    if win:
        t = result["log"]["t"]
        ax.axvspan(t[win[0]], t[win[1] - 1], color="steelblue", alpha=0.35)


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


def plot_rom_bounds(reconstructed: dict, video: dict | None = None):
    """Per-rep vertical ROM against what the lifter can actually move through.

    `reconstructed` maps capture stem -> (lift, [rom_m per rep]); `video` maps
    the same stems -> [rom_m per rep] measured from the footage.

    Two rows because they say opposite things. The reconstruction sits inside
    every band, which is the first external check bench and squat have passed.
    The video — the referee those bounds were meant to validate the pipeline
    against — does not: three deadlifts by one lifter spread across 19 cm.

    Bands are drawn with the measured ceiling solid and the inferred floor
    dashed, because they are not the same kind of claim.
    """
    from . import truth

    have_video = bool(video)
    fig, axes = plt.subplots(2 if have_video else 1, 1,
                             figsize=(12, 8 if have_video else 4.5))
    axes = np.atleast_1d(axes)

    def panel(ax, data, title):
        x = 0
        for stem, (lift, roms) in data.items():
            lo, hi = truth.VERTICAL_ROM_M[lift]
            xs = np.arange(x, x + len(roms))
            l, r = xs[0] - 0.5, xs[-1] + 0.5
            # Shade only this capture's span — the bands differ by lift, so one
            # axhspan across the whole axis would draw the squat band under the
            # bench points.
            ax.fill_between([l, r], lo * 100, hi * 100, color="0.92", zorder=0)
            ax.hlines(hi * 100, l, r, color="0.35", lw=1.4)
            ax.hlines(lo * 100, l, r, color="0.35", lw=1.0, ls="--")
            out = [(v < lo or v > hi) for v in roms]
            ax.scatter(xs, np.array(roms) * 100, s=42, zorder=3,
                       c=["#c0392b" if o else "#2c7fb8" for o in out])
            ax.plot(xs, np.array(roms) * 100, lw=0.8, color="0.6", zorder=2)
            ax.text(xs.mean(), 0.02, stem.split("_2026")[0], rotation=90,
                    ha="center", va="bottom", fontsize=7, color="0.3",
                    transform=ax.get_xaxis_transform())
            x += len(roms) + 1
        ax.set_xlim(-1, x)
        ax.set_xticks([])
        ax.set_ylabel("vertical ROM, cm")
        ax.set_title(title, fontsize=10, loc="left")

    panel(axes[0], reconstructed,
          "Reconstruction, per rep, after step 7. Band = measured ceiling "
          "(solid) and inferred floor (dashed). Red = outside.")
    if have_video:
        vid = {k: (truth.lift_of(k), v) for k, v in video.items()}
        panel(axes[1], vid,
              "The same bounds applied to the VIDEO ground truth. One lifter, "
              "one lift, 19 cm of spread — the referee's vertical scale is "
              "wrong per capture.")
    fig.tight_layout()
    return fig

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

What "confident" means here, because it is narrower than the word
--------------------------------------------------------------------
`project.confidence` decides the flag, and it can only test whether the
DISPLAY AXIS is identifiable. It cannot test whether the path drawn along that
axis is right, and on real captures the path is 5-15x outside spec (P2) with
its fore-aft sign resolved only since 2026-08-16 (B4). So a stretched plot is
not a certified plot;
it is one whose axis is not obviously meaningless. Every function here that
draws a bar path therefore says on its face what external evidence exists for
that lift, and nothing here reads the absence of a low-confidence label as an
endorsement.

Everything that draws a path goes through `project.project_to_plane`. Both
`plot_stages` and `plot_scorecard` used to project by hand — `rep[:, :2] @
axis` — which is how step 8 came to be the only stage in the pipeline that had
never run while its output was on screen in two figures.
"""

from __future__ import annotations

import textwrap

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

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
    maps the same labels to `(t_imu, height)` from `capture.py`. Everything comes
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
        _draw_planar(ax, r)
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


def _draw_planar(ax, result, lw_first=2.0, lw_rest=1.2):
    """Step 8's output, drawn under step 9's rules. In cm.

    One place, so that the stretch and the no-label rule cannot drift apart
    between figures — they did, and worse, both figures projected by hand and
    stretched unconditionally, so `project.project_to_plane` and
    `project.confidence` sat unimplemented while their results were on screen.
    """
    from . import project

    reps = result["reps"]
    planar = result.get("planar")
    if planar is None:
        # No axis at all (no reps): fall back to world x so the panel is not
        # blank, and label it, rather than pretending it is a projection.
        planar = project.project_to_plane(reps, np.array([1.0, 0.0])) if reps else []

    for i, p in enumerate(planar):
        ax.plot(p[:, 0] * 100, p[:, 1] * 100,
                lw=lw_first if i == 0 else lw_rest,
                alpha=1.0 if i == 0 else 0.75)

    # The display rule, honoured rather than assumed. Default False when the
    # flag is missing: refusing to stretch costs a reader nothing, and
    # stretching an unvetted axis is the failure the rule exists to prevent.
    confident = bool(result.get("confident", False))
    ax.set_aspect(1.0 / STRETCH if confident else 1.0)
    ax.set_xticks([])                        # deliberate: no horizontal scale

    label = ("fore-aft (stretched 4x, unlabelled by design)" if confident else
             "fore-aft, NOT stretched — low confidence (unlabelled by design)")
    # The reason goes under the panel, not inside it. A low-confidence panel is
    # narrow by construction — that is what withholding the stretch does — so
    # there is no interior room, and a verdict without its reason is the kind
    # of unexplained claim this project is trying to stop making.
    for why in result.get("confidence_reasons", []):
        label += "\n" + textwrap.fill(why, 46)
    ax.set_xlabel(label, fontsize=8)
    return ax


def _pause(ax, result):
    """Shade the pre-set calibration hold — where every bias estimate is made."""
    win = result.get("gyro_bias_info", {}).get("window")
    if win:
        t = result["log"]["t"]
        ax.axvspan(t[win[0]], t[win[1] - 1], color="steelblue", alpha=0.35)


def plot_truth_comparison(recovered, truth, title=""):
    """Recovered against known truth, per axis.

    This used to say truth was "only possible on synthetic data". Not since
    A2 — src/capture.py tracks the plate from footage and gives an external
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
    from . import capture

    have_video = bool(video)
    fig, axes = plt.subplots(2 if have_video else 1, 1,
                             figsize=(12, 8 if have_video else 4.5))
    axes = np.atleast_1d(axes)

    def panel(ax, data, title):
        x = 0
        for stem, (lift, roms) in data.items():
            lo, hi = capture.VERTICAL_ROM_M[lift]
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
        vid = {k: (capture.lift_of(k), v) for k, v in video.items()}
        panel(axes[1], vid,
              "The same bounds applied to the VIDEO ground capture. One lifter, "
              "one lift, 19 cm of spread — the referee's vertical scale is "
              "wrong per capture.")
    fig.tight_layout()
    return fig


def plot_anchors(anchors: dict, residuals: dict, exclusion: dict, momentum: dict):
    """C6 — what the two anchors measured, and what they cannot see.

    `anchors` maps stem -> calibrate.anchor_tilt result.
    `residuals` maps lift -> (hold values, per-rep values) in g.
    `exclusion` maps stem -> (pad_ms list, residual in g list).
    `momentum` maps stem -> per-rep vertical velocity closure, m/s.
    """
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))

    # 1 --- the answer: attitude before and after a set -----------------------
    ax = axes[0, 0]
    names = list(anchors)
    x = np.arange(len(names))
    ax.bar(x - 0.2, [anchors[k]["open_deg"] for k in names], 0.38,
           label="opening hold", color="#2c7fb8")
    ax.bar(x + 0.2, [anchors[k]["close_deg"] for k in names], 0.38,
           label="closing hold", color="#c0392b")
    ax.plot(x, [anchors[k]["gyro_only_deg"] for k in names], "k^--", ms=6,
            lw=0.9, label="gyro-only drift over the set")
    ax.axhline(2.0, color="0.4", ls=":", lw=1.4)
    ax.text(-0.4, 1.93, "P4 inferred a 2 deg attitude error. It is 15x smaller, "
            "and the inference used the wrong projection.",
            ha="left", va="top", fontsize=8, color="0.35")
    ax.set_ylim(0, 2.3)
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("_", "\n", 1) for n in names], fontsize=7)
    ax.set_ylabel("attitude error, degrees")
    ax.set_title("Core Motion survives a set: 0.05 -> 0.14 deg across 40-55 s",
                 fontsize=10, loc="left")
    ax.legend(fontsize=8)

    # 2 --- where the residual actually is ------------------------------------
    ax = axes[0, 1]
    for i, (lift, (hold, rep)) in enumerate(residuals.items()):
        ax.scatter(np.full(len(hold), i - 0.15), hold, s=34, color="#2c7fb8",
                   label="still hold" if i == 0 else None)
        ax.scatter(np.full(len(rep), i + 0.15), rep, s=34, color="#c0392b",
                   label="per rep" if i == 0 else None)
    ax.axhline(0.0025, color="0.4", ls="--", lw=1.2)
    ax.text(len(residuals) - 0.5, 0.0027, "0.0025 g accel bias, measured on a table",
            ha="right", va="bottom", fontsize=8, color="0.35")
    ax.set_yscale("log")
    ax.set_xticks(range(len(residuals)))
    ax.set_xticklabels(list(residuals))
    ax.set_ylabel("mean horizontal residual, g")
    ax.set_title("Bench and squat sit at the sensor's own noise floor; "
                 "deadlift does not", fontsize=10, loc="left")
    ax.legend(fontsize=8)

    # 3 --- the deadlift residual is the impact -------------------------------
    ax = axes[1, 0]
    for stem, (pads, vals) in exclusion.items():
        ax.plot(pads, vals, "o-", ms=5, lw=1.2, label=stem)
    ax.set_xlabel("samples excluded around each floor impact, +/- ms")
    ax.set_ylabel("per-rep horizontal residual, g")
    ax.set_title("Removing 6% of samples removes 75% of it: the impact is "
                 "where it enters", fontsize=10, loc="left")
    ax.legend(fontsize=8)

    # 4 --- vertical momentum does not close ----------------------------------
    ax = axes[1, 1]
    for i, (stem, dv) in enumerate(momentum.items()):
        ax.scatter(np.arange(1, len(dv) + 1) + i * 0.12, dv, s=42, label=stem)
    ax.axhline(0.0, color="0.3", lw=1.2)
    ax.set_xlabel("rep")
    ax.set_ylabel("vertical velocity change over the rep, m/s")
    ax.set_title("Impact to impact the bar starts and ends at rest, so this "
                 "must be zero", fontsize=10, loc="left")
    ax.legend(fontsize=8)

    fig.tight_layout()
    return fig


def plot_momentum_closure(groups: dict, traces: dict):
    """C11 — the deficit is the impact, not the lift.

    `groups` maps a label to a list of (duration_s, dv) per interval.
    `traces` maps a label to (t_rel, cumulative dv, impact_t or None) for one
    representative interval of each kind.

    The middle group is the one to read carefully, and it is the reason the
    left panel is worth anything: those are deadlift PULLS, floor to lockout,
    55-66 cm of loaded bar travel from the same captures as the red group.
    They close. So the red group's deficit is not the lift, the load, or the
    capture — it is the only thing the two do not share, the landing.

    The middle panel answers the obvious confound: the closing intervals could
    have closed by being short. They are not shorter.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    colours = {"bench, lifting": "#2c7fb8", "deadlift, pull only": "#2ca25f",
               "deadlift, impact inside": "#c0392b"}

    # 1 --- every interval, grouped ------------------------------------------
    ax = axes[0]
    rng = np.random.default_rng(0)
    for i, (label, rows) in enumerate(groups.items()):
        dv = np.array([d for _, d in rows])
        ax.scatter(i + rng.uniform(-0.16, 0.16, len(dv)), dv, s=34,
                   color=colours.get(label, "0.4"), alpha=0.85,
                   edgecolor="none")
        ax.plot([i - 0.28, i + 0.28], [np.median(dv)] * 2, "k-", lw=2.0)
    ax.axhline(0.0, color="0.3", lw=1.2)
    ax.axhspan(-0.11, 0.11, color="0.87", zorder=0)
    ax.set_ylim(-1.55, 0.42)
    ax.text(-0.42, 0.20, "+/-0.11 m/s — the sensor's own floor, 0.0019 g",
            ha="left", va="center", fontsize=8, color="0.35")
    ax.text(1.0, -0.30, "floor to lockout: 55-66 cm of\nreal pulling, and it "
            "closes.\nSame captures as the red group.", ha="center", va="top",
            fontsize=7.5, color="0.4")
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([k.replace(", ", ",\n") for k in groups], fontsize=8)
    ax.set_ylabel("vertical impulse between two still moments, m/s")
    ax.set_title("Must be zero. Only the impact-spanning intervals are not.",
                 fontsize=10, loc="left")

    # 2 --- the confound: are the closing intervals just short? ---------------
    ax = axes[1]
    for label, rows in groups.items():
        ax.scatter([d for d, _ in rows], [abs(v) for _, v in rows], s=34,
                   color=colours.get(label, "0.4"), alpha=0.85,
                   edgecolor="none", label=label)
    ax.set_yscale("log")
    ax.set_xlabel("interval duration, s")
    ax.set_ylabel("|vertical impulse|, m/s")
    ax.set_title("Not an artefact of length: the closing intervals are no "
                 "shorter", fontsize=10, loc="left")
    ax.legend(fontsize=8, loc="upper left")

    # 3 --- where it enters ---------------------------------------------------
    ax = axes[2]
    for label, (t_rel, cum, t_impact) in traces.items():
        ax.plot(t_rel, cum, lw=1.6, color=colours.get(label, "0.4"),
                label=label)
        if t_impact is not None:
            ax.axvline(t_impact, color=colours.get(label, "0.4"), ls=":", lw=1.2)
    ax.axhline(0.0, color="0.3", lw=1.2)
    ax.set_xlabel("time through the interval, s")
    ax.set_ylabel("cumulative vertical impulse = velocity, m/s")
    ax.set_title("The impact (dotted) does not bring the velocity back to zero",
                 fontsize=10, loc="left")
    ax.legend(fontsize=8, loc="lower left")

    fig.tight_layout()
    return fig


def plot_vs_truth_paths(results: dict, stretch: bool = True):
    """The reconstruction drawn on top of the video's bar path, per capture.

    `results` maps stem -> a `metrics.vs_truth` dict. Every capture with video
    gets a panel; reps are overlaid, the video in grey and the pipeline in
    colour, each rep start-aligned exactly as step 9 aligns them.

    This is the figure that says what the error NUMBERS mean. "0.64 cm rms" and
    "15.44 cm rms" are abstractions until you see that one is a bar path with a
    wobble and the other does not resemble the movement at all.

    The horizontal axis IS labelled here, which `plot_paths` refuses to do and
    is right to refuse. The difference is that this panel shows the truth beside
    the claim, so the reader can see how far the claim can be trusted; a
    product plot shows only the claim.
    """
    stems = list(results)
    cols = min(5, len(stems))
    rows = -(-len(stems) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.5 * cols, 5.4 * rows),
                             squeeze=False)
    flat = axes.ravel()

    for ax, stem in zip(flat, stems):
        m = results[stem]
        good = [r for r in m["per_rep"] if r.get("covered")]
        for i, r in enumerate(good):
            vid, pipe = r["curve_video"] * 100, r["curve_pipeline"] * 100
            ax.plot(vid[:, 0], vid[:, 1], color="0.55", lw=2.0,
                    label="video (truth)" if i == 0 else None, zorder=2)
            ax.plot(pipe[:, 0], pipe[:, 1], lw=1.3, alpha=0.9,
                    label="pipeline" if i == 0 else None, zorder=3)
        if stretch:
            ax.set_aspect(1.0 / STRETCH)
        beats = m["beats_null"]
        verdict = "beats" if beats > 1 else "LOSES TO"
        ax.set_title(f"{stem}\n{m['pipeline_h_rms']:.2f} cm rms   "
                     f"{verdict} flat line ({beats:.2f}x)",
                     fontsize=8, color="0.15")
        ax.set_xlabel("fore-aft (cm)", fontsize=8)
        ax.set_ylabel("vertical (cm)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=6, frameon=False, loc="best")
    for ax in flat[len(stems):]:
        ax.axis("off")

    fig.suptitle(
        "The reconstruction (colour) against the video (grey), every capture "
        "that has capture. Reps start-aligned, fore-aft stretched 4x as step 9 "
        "draws it.\nSquat is absent because vs_truth refuses it. Bench "
        "distances carry ~4% from a hand-placed seed; read metrics.bench_sync "
        "before quoting them.", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return fig


def plot_splice_rejected(closure: dict, h_rms: dict, rom_trace: tuple,
                         rom_bound: float):
    """B6 — the impact splice does what it claims and loses anyway.

    `closure` maps stem -> (shipping dv list, spliced dv list), m/s.
    `h_rms` maps stem -> {variant label: horizontal rms in cm}.
    `rom_trace` is (stem, shipping per-rep vertical, spliced per-rep vertical).
    `rom_bound` is the deadlift ROM ceiling in cm.

    Three panels because the result needs all three to be honest: the splice
    works, it does not help the axis the spec is about, and it breaks a bound
    it was never aimed at. Any one of them alone misrepresents it.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))

    # 1 --- it does exactly what it was built to do ---------------------------
    ax = axes[0]
    for i, (stem, (ship, spl)) in enumerate(closure.items()):
        ax.scatter(np.full(len(ship), i - 0.16), ship, s=40, color="#c0392b",
                   label="shipping" if i == 0 else None, edgecolor="none")
        ax.scatter(np.full(len(spl), i + 0.16), spl, s=40, color="#2ca25f",
                   label="with the splice" if i == 0 else None, edgecolor="none")
    ax.axhline(0.0, color="0.3", lw=1.2)
    ax.set_xticks(range(len(closure)))
    ax.set_xticklabels([s.replace("_", "\n", 1) for s in closure], fontsize=7)
    ax.set_ylabel("vertical impulse across a landing, m/s")
    ax.set_title("It works: the momentum deficit is gone", fontsize=10, loc="left")
    ax.legend(fontsize=8)

    # 2 --- and it does not help the axis the spec is about -------------------
    ax = axes[1]
    labels = list(next(iter(h_rms.values())))
    x = np.arange(len(h_rms))
    w = 0.8 / len(labels)
    for j, lab in enumerate(labels):
        ax.bar(x + j * w - 0.4 + w / 2, [h_rms[s][lab] for s in h_rms], w,
               label=lab, color=["0.35", "#2c7fb8", "#e08214", "#8073ac"][j])
    ax.axhline(1.0, color="crimson", ls="--", lw=1.2)
    ax.text(len(h_rms) - 0.5, 1.15, "the 1 cm spec", ha="right", fontsize=8,
            color="crimson")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n", 1) for s in h_rms], fontsize=7)
    ax.set_ylabel("horizontal rms vs video, cm")
    ax.set_title("No variant beats shipping. Vertical-only is identical.",
                 fontsize=10, loc="left")
    ax.legend(fontsize=7)

    # 3 --- and it breaks a bound it was not aimed at -------------------------
    ax = axes[2]
    stem, ship_reps, spl_reps = rom_trace
    for i, rep in enumerate(ship_reps):
        ax.plot(np.linspace(0, 1, len(rep)), rep - rep.min(), color="0.45",
                lw=1.0, label="shipping" if i == 0 else None)
    for i, rep in enumerate(spl_reps):
        ax.plot(np.linspace(0, 1, len(rep)), rep - rep.min(), color="#c0392b",
                lw=1.2, label="with the splice" if i == 0 else None)
    ax.axhline(rom_bound, color="crimson", ls="--", lw=1.4)
    ax.text(0.02, rom_bound + 1.5, f"{rom_bound:.0f} cm — what this lifter can "
            f"actually move a bar through", fontsize=8, color="crimson")
    ax.set_xlabel("normalised time through the rep")
    ax.set_ylabel("vertical travel, cm")
    ax.set_title(f"Why it still loses: ~1/2*e*T of position injected at each "
                 f"landing\n({stem}, and a linear detrend cannot remove a "
                 f"quadratic)", fontsize=9, loc="left")
    ax.legend(fontsize=8)

    fig.tight_layout()
    return fig


def plot_bias_models(variants: dict, closure: dict, traces: dict):
    """B6 — why every constant-bias correction makes it worse.

    `variants` maps a label to a list of per-capture horizontal rms in cm.
    `closure` maps stem -> (implied bias from the measured error, closure-based
    estimate), both in g. `traces` maps stem -> (t, cumulative dv, impact time)
    for one representative rest-to-rest interval.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))

    ax = axes[0]
    labels = list(variants)
    x = np.arange(len(labels))
    for i in range(3):
        ax.bar(x + (i - 1) * 0.26, [variants[k][i] for k in labels], 0.25,
               label=f"capture {i+1}")
    ax.axhline(1.0, color="0.3", ls="--", lw=1.2)
    ax.text(len(labels) - 0.4, 1.4, "the 1 cm spec", ha="right", fontsize=8,
            color="0.35")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=20, ha="right")
    ax.set_ylabel("horizontal rms vs video, cm")
    ax.set_title("Every closure-derived bias correction is worse than none",
                 fontsize=10, loc="left")
    ax.legend(fontsize=8)

    ax = axes[1]
    T = 3.4
    b = np.linspace(0, 0.03, 200)
    ax.plot(b, b * 9.80665 * T ** 2 / 8 * 100, lw=1.8, color="0.25")
    ax.axhline(1.0, color="0.3", ls="--", lw=1.2)
    for stem, (implied, estimated) in closure.items():
        ax.scatter([implied], [implied * 9.80665 * T ** 2 / 8 * 100], s=48,
                   marker="o", zorder=3)
        ax.scatter([estimated], [estimated * 9.80665 * T ** 2 / 8 * 100], s=60,
                   marker="x", zorder=3)
    ax.set_xlabel("constant acceleration bias, g")
    ax.set_ylabel("position error left after a linear detrend, cm")
    ax.set_title("o = bias implied by the MEASURED error\n"
                 "x = bias the closure constraint estimates. 3-7x too big.",
                 fontsize=10, loc="left")

    ax = axes[2]
    for stem, (tt, dv, t_imp) in traces.items():
        ln, = ax.plot(tt, dv, lw=1.4, label=stem)
        ax.axvline(t_imp, color=ln.get_color(), ls=":", lw=1.0)
    ax.axhline(0.0, color="0.3", lw=1.0)
    ax.set_xlabel("time through a rest-to-rest interval, s")
    ax.set_ylabel("cumulative vertical velocity, m/s")
    ax.set_title("The bar is at rest at both ends, so this must return to 0.\n"
                 "Dotted = the floor impact.", fontsize=10, loc="left")
    ax.legend(fontsize=8)

    fig.tight_layout()
    return fig


def plot_scorecard(results: dict, truths: dict, roms: dict):
    """How well the pipeline currently performs, per lift, on what evidence.

    `results` maps "lift (stem)" -> `pipeline.run` dict for one representative
    capture; `truths` maps the same key -> `vs_truth` where a video exists;
    `roms` maps lift -> list of every per-rep vertical ROM in that lift, in m.

    Written as a scorecard rather than a diagnostic, because the recurring
    failure in this project is a number that looks good in isolation. So each
    row carries what it is allowed to conclude, and the bottom row is entirely
    about what is NOT known — which is most of it.
    """
    from . import capture as truth_mod

    labels = list(results)
    fig, axes = plt.subplots(3, len(labels), figsize=(5.0 * len(labels), 11.5),
                             gridspec_kw={"height_ratios": [2.0, 1.0, 1.0]})

    for col, label in enumerate(labels):
        r = results[label]
        lift = label.split()[0]

        # --- row 0: the product, as step 9 draws it ------------------------
        ax = axes[0, col]
        _draw_planar(ax, r, lw_first=2.2)
        ax.set_title(label, fontsize=11, fontweight="bold")
        if col == 0:
            ax.set_ylabel("what the pipeline would show you\nheight (cm)",
                          fontsize=9)
        # The trap this project keeps falling into: a lift draws a clean,
        # plausible bar path and nothing can check it, while deadlift draws an
        # obvious mess and has truth to be measured against. Plausibility is not
        # evidence, and it is exactly how a broken pipeline convinces somebody
        # it works (CLAUDE.md, the deadlift-first rule). Since C8 the unchecked
        # set is squat plus the four bench captures whose sync does not resolve,
        # rather than bench-and-squat wholesale — `truths` decides, so this
        # follows automatically.
        if label not in truths:
            ax.text(0.5, 0.02, "looks plausible. that is not evidence —\n"
                               "nothing external checks this lift",
                    ha="center", va="bottom", fontsize=8, color="crimson",
                    transform=ax.transAxes)

        # --- row 1: error against video, per rep ---------------------------
        ax = axes[1, col]
        t = truths.get(label)
        if t is None:
            ax.text(0.5, 0.5, "NO VIDEO TRUTH\n\nsquat tracks at ~0.40 NCC and\n"
                              "clips frame at lockout; a bench\nlands here only "
                              "if its sync\ndoes not resolve.\nNothing external "
                              "measures\nthis capture's error.",
                    ha="center", va="center", fontsize=9, color="crimson",
                    transform=ax.transAxes)
            ax.set_xticks([]); ax.set_yticks([])
        else:
            n = np.arange(1, len(t["per_rep"]) + 1)
            ax.bar(n - 0.2, [p["pipeline_h_rms"] for p in t["per_rep"]], 0.38,
                   label="horizontal", color="#c0392b")
            ax.bar(n + 0.2, [p["pipeline_v_rms"] for p in t["per_rep"]], 0.38,
                   label="vertical", color="#2c7fb8")
            ax.axhline(1.0, color="#c0392b", ls="--", lw=1.2)
            ax.axhline(3.0, color="#2c7fb8", ls="--", lw=1.2)
            ax.set_xlabel("rep", fontsize=8)
            ax.legend(fontsize=7, loc="upper right")
            note = "dashed = spec (1 cm / 3 cm)"
            if t.get("video_rom_flags"):
                note += "\ntruth FLAGGED: video scale wrong on this capture"
            ax.text(0.02, 0.02, note, fontsize=7, transform=ax.transAxes,
                    va="bottom", color="0.35")
        if col == 0:
            ax.set_ylabel("error vs video\nper rep, cm rms", fontsize=9)

        # --- row 2: what IS checkable on every lift ------------------------
        ax = axes[2, col]
        vals = np.array(roms.get(lift, [])) * 100
        lo, hi = truth_mod.VERTICAL_ROM_M[lift]
        ax.axhspan(lo * 100, hi * 100, color="0.92")
        ax.axhline(hi * 100, color="0.35", lw=1.4)
        ax.axhline(lo * 100, color="0.35", lw=1.0, ls="--")
        if len(vals):
            ax.scatter(np.arange(len(vals)), vals, s=26,
                       c=["#c0392b" if (v < lo * 100 or v > hi * 100) else "#2c7fb8"
                          for v in vals])
        ax.set_xticks([])
        ax.set_xlabel(f"every rep of every {lift} capture", fontsize=8)
        if col == 0:
            ax.set_ylabel("vertical ROM, cm\n(the only check bench/squat have)",
                          fontsize=9)

    fig.suptitle(
        "How the pipeline is performing — one column per lift\n"
        "Row 1 is the product. Row 2 is how wrong it is, where anything can "
        "say so. Row 3 is the only external check that covers all three.",
        fontsize=12)
    fig.tight_layout(rect=(0.015, 0, 1, 0.955))
    return fig


def plot_b3_oracle(rows: list[dict], rom_trace: tuple, rom_bound: float,
                   spec_cm: float = 1.0):
    """B3 — where a per-rep detrend can reach, and where it cannot. C19.

    `rows` is one dict per scoreable capture with the keys `b3_oracle` emits:
    capture, null, h_ship/h_lin/h_quad, h_est, rom_ship/rom.
    `rom_trace` is (stem, shipping per-rep vertical cm, order=2 per-rep cm).
    `rom_bound` is the deadlift ROM ceiling in cm.

    Three panels, for the same reason the splice figure needs three: the
    result is a ceiling, a rejection and a mechanism, and any one alone
    misrepresents it. Panel 1 is the finding worth keeping — an ORACLE, so it
    is what no estimator can beat, not what one achieved.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.0))
    stems = [r["capture"] for r in rows]
    x = np.arange(len(rows))

    # 1 --- the ceiling, per capture, and it splits by lift --------------------
    ax = axes[0]
    for off, key, colour, label in [(-0.26, "h_ship", "#7f8c8d", "shipping"),
                                    (0.00, "h_lin", "#2980b9", "oracle: best line"),
                                    (0.26, "h_quad", "#8e44ad", "oracle: + quadratic")]:
        ax.bar(x + off, [r[key] for r in rows], width=0.25, color=colour,
               label=label, edgecolor="none")
    ax.scatter(x, [r["null"] for r in rows], s=44, marker="_", color="#c0392b",
               linewidths=2.2, label="null model (a flat line)", zorder=5)
    ax.axhline(spec_cm, color="#16a085", lw=1.4, ls="--", label=f"{spec_cm:g} cm spec")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n", 1) for s in stems], fontsize=6.5,
                       rotation=30, ha="right")
    ax.set_ylabel("per-rep horizontal rms, cm  (log)")
    ax.set_title("What NO per-rep detrend can beat\n"
                 "bench reaches spec; on deadlift no LINE beats the flat line",
                 fontsize=9)
    ax.legend(fontsize=6.5, frameon=False)

    # 2 --- and the buildable version breaks a bound it was not aimed at -------
    ax = axes[1]
    ax.bar(x - 0.16, [r["rom_ship"] for r in rows], width=0.32, color="#7f8c8d",
           label="shipping", edgecolor="none")
    ax.bar(x + 0.16, [r["rom"] for r in rows], width=0.32, color="#c0392b",
           label="order=2 (velocity closure)", edgecolor="none")
    ax.axhline(rom_bound, color="#16a085", lw=1.4, ls="--",
               label=f"deadlift ROM ceiling, {rom_bound:.0f} cm")
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n", 1) for s in stems], fontsize=6.5,
                       rotation=30, ha="right")
    ax.set_ylabel("median per-rep vertical travel, cm")
    ax.set_title("The buildable quadratic, measured and rejected\n"
                 "deadlift goes past what a lifter can move a bar through",
                 fontsize=9)
    ax.legend(fontsize=6.5, frameon=False)

    # 3 --- the mechanism -----------------------------------------------------
    ax = axes[2]
    stem, ship, quad = rom_trace
    for i, p in enumerate(ship):
        ax.plot(np.linspace(0, 1, len(p)), p, color="#7f8c8d", lw=1.1,
                label="shipping" if i == 0 else None)
    for i, p in enumerate(quad):
        ax.plot(np.linspace(0, 1, len(p)), p, color="#c0392b", lw=1.1,
                label="order=2" if i == 0 else None)
    ax.axhline(rom_bound, color="#16a085", lw=1.4, ls="--")
    ax.set_xlabel("normalised rep time")
    ax.set_ylabel("vertical position, cm")
    ax.set_title(f"{stem}: why\nthe landing's error is local; the quadratic "
                 "is not", fontsize=9)
    ax.legend(fontsize=6.5, frameon=False)

    fig.suptitle(
        "B3 — the per-rep detrend has real headroom, and it is not in the "
        "polynomial order (C19)", fontsize=12)
    fig.text(0.5, 0.005,
             "Panel 1 is an ORACLE: the best line and the best line-plus-quadratic "
             "fitted AGAINST the video, so it bounds every estimator rather than "
             "being one. It is forbidden in the pipeline and is the point here.",
             ha="center", fontsize=7.5, color="0.35")
    fig.tight_layout(rect=(0.01, 0.03, 1, 0.93))
    return fig


def _circumcircle(p: np.ndarray) -> tuple[np.ndarray, float]:
    """Centre and radius of the circle through three (y, x) points.

    The tracker's `circumradius` is the MEAN distance from the centroid, which
    is not a circumradius unless the triangle is equilateral — so a circle
    drawn with it does not pass through the markers. For a figure whose whole
    job is to show which object is being tracked, that difference is the
    difference between a legible panel and a misleading one.
    """
    (y1, x1), (y2, x2), (y3, x3) = p
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:                      # collinear: fall back on the centroid
        c = p.mean(axis=0)
        return c, float(np.hypot(*(p - c).T).mean())
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    c = np.array([uy, ux])
    return c, float(np.hypot(uy - y1, ux - x1))


def plot_marker_seeding(shipped: dict, handseeded: dict, gates: list[dict],
                        frames: dict):
    """C21 — why the marker tracker fails on the 2026-08-03 paired captures.

    `shipped` and `handseeded` are `markers.track` outputs on `bench_95x2`.
    `gates` is one dict per gate with `name`, `old`, `new`, `limit` and `unit`.
    `frames` describes one illustrative frame: `image`, and `true_rim` /
    `shipped_rim`, each (3, 2) marker positions in (y, x).

    **Each constellation is drawn as the circle through its own three markers**
    — `_circumcircle`, not the centroid and mean radius the tracker carries as
    `circumradius`. Two earlier versions of this panel got this wrong and both
    were caught by the owner. The first drew fixed-size markers, so the plate
    appeared far smaller than it is. The second drew a circle of the mean
    radius about the centroid, which visibly misses the markers: on
    `bench_95x2` frame 450 the three stickers sit at 89.8, 89.8 and 102.9 px
    from the centroid, so no circle centred there passes through all three.

    That spread is not a drawing artefact and it is worth reading off the
    figure. The module's load-bearing assumption is that three equally spaced
    points on a circle project, under weak perspective, to a triangle whose
    centroid is the projected centre. A 13 px spread in vertex radius is that
    assumption's error term made visible — `calibration_report` measures it as
    `spacing_bias`. The circumcircle passes through the markers by
    construction, so it shows where the plate is without asserting anything
    about that bias.

    Three panels because the finding has three parts and any one alone
    misleads. The first is the failure as it actually looks — not "noisy", but
    a confident lock on a piece of furniture. The second is the control that
    localises it: the same tracker, same clip, correct seed. The third is why
    it was always going to happen, which is that all three admission gates were
    sitting at zero margin on the captures they were tuned against.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.0))

    # 1 --- the failure: a confident lock on the bench -------------------------
    ax = axes[0]
    ax.imshow(frames["image"], cmap="gray")
    # Shipped first so the plate's markers draw on top: the two constellations
    # SHARE a vertex — the seeder's triple is one real sticker plus two things
    # that are not stickers, one of them outside the frame — and the shared
    # cross would otherwise be hidden under the wrong one.
    for key, colour, style, marker, size, label in (
            ("shipped_rim", "#c0392b", "--", "x", 11,
             "what the shipped seeder locked onto"),
            ("true_rim", "#f1c40f", "-", "+", 15,
             "the plate, by its 3 stickers")):
        rim = np.asarray(frames[key], float)
        centre, radius = _circumcircle(rim)
        ax.add_patch(plt.Circle(centre[::-1], radius, fill=False,
                                color=colour, lw=2.0, ls=style))
        ax.plot(rim[:, 1], rim[:, 0], marker, color=colour, ms=size, mew=2.2,
                label=label)
    if "zoom" in frames:                      # (y0, y1, x0, x1)
        y0, y1, x0, x1 = frames["zoom"]
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.02),
              frameon=False)
    ax.set_title("bench_95x2, frame 450: the seeder's triple is ONE real\n"
                 "sticker plus two things that are not — and reports 3 markers",
                 fontsize=9)

    # 2 --- the control: same tracker, correct seed ----------------------------
    ax = axes[1]
    for trk, colour, label in ((shipped, "#c0392b", "shipped seeder"),
                               (handseeded, "#2980b9", "hand-seeded on the plate")):
        y = np.asarray(trk["centre"])[:, 0]
        ax.plot(y, lw=1.0, color=colour, label=label)
    ax.invert_yaxis()
    ax.set_xlabel("frame")
    ax.set_ylabel("tracked centre, y (px)   [down is up]")
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("`track` is not what is broken\n"
                 "hand-seeded: 100% coverage, 0.11 px median residual;\n"
                 "the shipped seed follows the bar 60 px displaced, then breaks up",
                 fontsize=8.5)

    # 3 --- the gates, and the margin they never had ---------------------------
    ax = axes[2]
    x = np.arange(len(gates))
    ax.bar(x - 0.19, [g["old"] / g["limit"] for g in gates], width=0.36,
           color="#7f8c8d", label="old footage (worked)", edgecolor="none")
    ax.bar(x + 0.19, [g["new"] / g["limit"] for g in gates], width=0.36,
           color="#c0392b", label="2026-08-03 (failed)", edgecolor="none")
    ax.axhline(1.0, color="#16a085", lw=1.6, ls="--", label="the gate")
    ax.set_xticks(x)
    ax.set_xticklabels([textwrap.fill(g["name"], 16) for g in gates], fontsize=7)
    ax.set_ylabel("value / gate   (>1 is rejected)")
    ax.legend(fontsize=7, frameon=False)
    ax.set_title("Every gate was already at zero margin\n"
                 "the new captures crossed all three at once", fontsize=9)

    fig.suptitle("C21 — the marker seeder, and where it actually fails",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def plot_overview(results: dict, spec_cm: float = 1.0):
    """Stages, the bar path, and the bar path against the video — one figure.

    `results` maps a label to a `pipeline.run` dict that was given a video, so
    each carries `vs_truth`. One column per capture, six rows.

    This is `analysis/21` and `analysis/27` and a truth overlay in one place,
    and the reason to have it as one figure rather than three is the bottom two
    rows. Everything above them is the reconstruction talking about itself;
    those two are the only rows where something outside the IMU gets a vote,
    and reading them next to the drift that produced them is the point.

    **Put a `data_v2` bench in the columns.** The two referees then sit side by
    side on the same lift: `capture.py` matching a dark plate template, and
    `markers.py` tracking stickers. They are not the same quality of evidence
    and the figure should not let anyone forget it — the marker column is the
    one where the referee tracks 100% of frames rather than losing the bar at
    the top of travel.
    """
    labels = list(results)
    rows = [
        ("1-3  orient.to_world", "world vertical\naccel (m/s²)"),
        ("4  integrate", "vertical\nvelocity (m/s)"),
        ("4  integrate", "vertical\nposition (m)"),
        ("7  correct.detrend", "per-rep\nvertical (cm)"),
        ("8-9  project + plot", "bar path\nheight (cm)"),
        ("judge  metrics.vs_truth", "vs video\nheight (cm)"),
    ]
    fig, axes = plt.subplots(len(rows), len(labels),
                             figsize=(5.0 * len(labels), 2.7 * len(rows)),
                             gridspec_kw={"height_ratios": [1, 1, 1, 1, 1.7, 1.7]},
                             squeeze=False)

    for col, label in enumerate(labels):
        r = results[label]
        log, bounds, reps = r["log"], r["bounds"], r["reps"]
        t = log["t"]
        vt = r.get("vs_truth")

        ax = axes[0, col]
        ax.plot(t, r["world_accel"][:, 2], lw=0.6, color="0.3")
        ax.axhline(0, color="0.7", lw=0.8)
        ax.set_title(f"{label}\n", fontsize=11, fontweight="bold")

        ax = axes[1, col]
        ax.plot(t, r["velocity"][:, 2], lw=0.8, color="0.2")
        ax.axhline(0, color="0.7", lw=0.8)
        for a, b in bounds:
            ax.axvspan(t[a], t[min(b, len(t) - 1)], color="seagreen", alpha=0.16)
        ax.text(0.02, 0.88, f"{len(bounds)} reps (green)", fontsize=8,
                transform=ax.transAxes, color="seagreen")

        ax = axes[2, col]
        ax.plot(t, r["position"][:, 2], lw=1.0, color="crimson")
        span = float(np.ptp(r["position"][:, 2]))
        ax.text(0.02, 0.96, f"spans {span:.1f} m\nthe lift is ~0.3-0.6 m",
                fontsize=8, transform=ax.transAxes, color="crimson", va="top",
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=1.5))
        ax.set_xlabel("time (s)")

        ax = axes[3, col]
        for i, rep in enumerate(reps):
            ax.plot(np.linspace(0, 1, len(rep)), rep[:, 2] * 100,
                    lw=1.6 if i == 0 else 1.0, alpha=1.0 if i == 0 else 0.7)
        ax.axhline(0, color="0.7", lw=0.8)
        ax.set_xlabel("fraction of rep")

        # --- the product, drawn under step 9's rules ----------------------
        ax = axes[4, col]
        _draw_planar(ax, r)

        # --- the only row where something outside the IMU votes -----------
        ax = axes[5, col]
        if vt is None:
            ax.text(0.5, 0.5, "no video", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="0.5")
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        good = [p for p in vt["per_rep"] if p.get("covered")]
        for i, p in enumerate(good):
            vid, pipe = p["curve_video"] * 100, p["curve_pipeline"] * 100
            ax.plot(vid[:, 0], vid[:, 1], color="0.55", lw=2.0, zorder=2,
                    label="video (the referee)" if i == 0 else None)
            ax.plot(pipe[:, 0], pipe[:, 1], lw=1.3, alpha=0.9, zorder=3,
                    label="pipeline" if i == 0 else None)
        ax.set_aspect(1.0 / STRETCH)
        ax.set_xlabel("fore-aft (cm)")
        ax.legend(fontsize=7, frameon=False, loc="lower right")

        beats = vt["beats_null"]
        verdict = "beats" if beats > 1 else "LOSES TO"
        ax.text(0.02, 0.98,
                f"tracker: {vt['video_tracker']}\n"
                f"horizontal {vt['pipeline_h_rms']:.2f} cm rms  "
                f"(spec {spec_cm:g})\n"
                f"{verdict} the flat-line null by {beats:.2f}x\n"
                f"reps disagreeing on sign: "
                f"{vt['reps_disagreeing_on_sign']}/{vt['n_compared']}",
                fontsize=8, transform=ax.transAxes, va="top",
                color="crimson" if beats <= 1 else "#1e6b3a",
                bbox=dict(fc="white", ec="none", alpha=0.8, pad=2.0))

    for row, (stage, ylab) in enumerate(rows):
        axes[row, 0].set_ylabel(f"step {stage}\n{ylab}", fontsize=9)

    fig.suptitle(
        "One capture per column: the pipeline, the bar path it produces,\n"
        "and what the video says about it\n"
        "Rows 1-4 are the reconstruction talking about itself. Only the last row "
        "has an outside vote,\nand the right-hand column is the first capture "
        "refereed by markers rather than a plate template.",
        fontsize=11)
    fig.tight_layout(rect=(0.02, 0, 1, 0.94))
    return fig


def plot_v2_video_rom(data: dict):
    """Per-rep vertical ROM on the four paired benches, three ways. C24.

    `data` maps capture stem -> dict with `t_vid`, `height` (metres, on the IMU
    clock), `bounds`, `t`, `imu_rom_cm`, `window_rom_cm` and `touches` (indices
    into `t_vid` of the chest touches the VIDEO found by itself).

    Three measurements of one quantity, and the gaps between them are the point
    ---------------------------------------------------------------------------
    `imu` is the reconstruction after step 7. `window` is the video's vertical
    range inside the IMU's rep window — what `metrics.vs_truth` reports, so it
    inherits the sync. `own` is the video's own trough-to-shoulder range, found
    by peak detection on the height trace with **no IMU input and no sync at
    all**, which is what makes it able to referee the other two.

    It says two things that C23's whole-clip comparison could not.

    The two instruments disagree by ~20% on every rep of every capture. `own`
    runs 23.3-26.7 cm over all 14 reps; the reconstruction says 28.4-30.7.
    **Do not read that as the IMU reading high** — this figure cannot assign it.
    `markers.calibration_report` declares a spacing bias of 7.3-11.2 cm on these
    same four clips, which is larger than the ~5 cm being argued over, so the
    marker path is not currently clean enough to convict the reconstruction.
    What the figure does settle is that the agreement C23 reported is not
    evidence of agreement: it compared the video's WHOLE-CLIP travel against
    per-rep IMU ROM and got -1.6%, and the whole-clip range includes the
    un-rack, where the bar is held ~3 cm above lockout — about the size of the
    per-rep gap. A whole-clip range and a per-rep range are not the same
    quantity and should not have been compared.

    **Two of the four were drawn synced a full rep out, and C25 fixed it.**
    As first drawn, `bench_92.5x4_2` and `_3` had an IMU window 0 holding no
    video touch while the video's last rep fell outside every window, and this
    docstring read it as `bench_sync`'s known whole-rep ambiguity finally being
    caught. It was not that. It was `max_lag_s`, then 5.0 s, excluding those
    two captures' true correlation peaks at -6.37 and -7.08 s, so the sweep
    returned a sidelobe one rep late. Widened, all **14 windows hold exactly
    one touch at 0.53-0.69 through**, which reproduces C9's 0.567-0.648 on a
    different dataset and tracker. See `metrics.bench_sync`.

    Keep the shape of that mistake. The figure showed a real defect in the
    right place and this docstring assigned it to the wrong stage, because a
    whole-rep sync error and a whole-rep segmentation error produce the
    identical picture — the owner read the same panel as the segmenter dropping
    a rep, which is the other way to be wrong about it. Nothing drawn here can
    separate them; only an anchor outside the periodicity can.

    A red window is one containing no touch, and there should now be none —
    if one appears, the sync is out again. The dashed line is the video's
    whole-clip travel, drawn to show how much of it the un-rack contributes.

    The `own` and `imu` bars never depended on the sync, so the ~20%
    disagreement above is exactly as it was; the `window` bars for the two
    captures did, and were 2.4 and 1.4 cm of a ~25 cm rep — window 0 was
    measuring the un-rack.
    """
    names = list(data)
    fig, axes = plt.subplots(2, len(names), figsize=(4.6 * len(names), 8.6),
                             squeeze=False)

    for j, name in enumerate(names):
        c = data[name]
        h = (np.asarray(c["height"]) - np.min(c["height"])) * 100
        t_vid, t = np.asarray(c["t_vid"]), np.asarray(c["t"])
        touches = list(c["touches"])

        ax = axes[0][j]
        ax.plot(t_vid, h, lw=1.1, color="0.25", zorder=2)
        for k, (a, b) in enumerate(c["bounds"]):
            t0, t1 = t[a], t[b - 1]
            has = any(t0 <= t_vid[i] <= t1 for i in touches)
            ax.axvspan(t0, t1, color="#7fbf7f" if has else "#d98880",
                       alpha=0.45, zorder=0)
            ax.text((t0 + t1) / 2, 0.97, str(k), ha="center", va="top",
                    fontsize=8, color="0.2",
                    transform=ax.get_xaxis_transform())
        ax.plot(t_vid[touches], h[touches], "v", ms=7, color="#c0392b",
                zorder=3, label="touch, found by the video alone")
        ax.set_xlabel("time on the IMU clock, s", fontsize=9)
        ax.set_title(name, fontsize=10)
        if j == 0:
            ax.set_ylabel("video bar height, cm")
            ax.legend(fontsize=7, loc="lower left")

        ax = axes[1][j]
        imu, win, own = c["imu_rom_cm"], c["window_rom_cm"], c["own_rom_cm"]
        x = np.arange(len(imu))
        ax.bar(x - 0.26, imu, 0.26, color="#2c7fb8", label="IMU, after step 7")
        ax.bar(x, win, 0.26, color="#e08214", label="video, in the IMU window")
        padded = (list(own) + [np.nan] * len(imu))[:len(imu)]
        ax.bar(x + 0.26, padded, 0.26,
               color="#5e3c99", label="video, its own extents")
        ax.axhline(c["whole_clip_cm"], ls="--", lw=1.2, color="0.3",
                   label="video, whole clip")
        ax.set_xticks(x)
        ax.set_xlabel("rep", fontsize=9)
        ax.set_ylim(0, max(40, c["whole_clip_cm"] + 9))
        if j == 0:
            ax.set_ylabel("vertical ROM, cm")
            ax.legend(fontsize=7, loc="upper left", framealpha=0.9)

    fig.suptitle(
        "Per-rep vertical ROM on the four paired benches — the first captures "
        "refereed by markers\n"
        "The purple bar uses no IMU and no sync. It disagrees with the "
        "reconstruction by ~20% on all 14 reps — unassigned, since the tracker "
        "declares a 7.3-11.2 cm spacing bound on these same clips.\n"
        "Red window = the IMU found a rep where the video shows no chest touch; "
        "there are none. All 14 windows hold one touch, at 0.53-0.69 through.",
        fontsize=11)
    fig.tight_layout(rect=(0.01, 0, 1, 0.92))
    return fig


def plot_v2_deadlift_conic(data: dict):
    """The 8-sticker deadlifts: conic marker referee against the pipeline. C27.

    `data` maps capture stem -> dict with `t_vid`, `height` (m, IMU clock),
    `bounds`, `t`, `per_rep` (from `metrics.vs_truth`), `h_rms`, `null_h_rms`,
    `beats_null`, `imu_rom_cm`, `n_rim`, `coverage`, `resid_px` and
    `decile_markers` (median markers matched per decile of travel, floor first).

    Four rows, and the third is the one to read
    --------------------------------------------
    Row 1 puts both instruments' VERTICAL on one clock. They should lie on top
    of each other; where they do not, one of them is wrong and the shading says
    which reps the IMU thinks it is in.

    Row 2 is per-rep vertical ROM, pipeline against video. This is the axis the
    reconstruction has always been decent on, and it is here as the control:
    agreement here is necessary, not sufficient, and `capture.VERTICAL_ROM_M`
    admits both instruments even when they disagree by 20% (C24).

    Row 3 is HORIZONTAL, per rep, video against pipeline, with the flat-line
    null drawn as well. **This is the project's actual question** — the display
    stretches this axis 4x, the spec is ~1 cm, and `beats_null` below 1.0 means
    the reconstruction is worse than drawing no fore-aft motion at all. A
    reconstruction can pass row 2 and fail this completely; six of the ten
    captures scored before this one did exactly that.

    Row 4 is the referee's own health, which C12 is the reason for. It plots
    markers matched against decile of travel. The plate TEMPLATE loses the bar
    at lockout — 166/166 frames below `capture.GOOD_SCORE` — so every deadlift
    number in P2 is measured through a referee that fails exactly where the
    measurement is taken. The conic tracker's failure is at the FLOOR instead,
    which is the opposite end and matters for a different reason: ROM is
    top-minus-bottom, so a bad bottom inflates it.
    """
    stems = list(data)
    n = len(stems)
    fig, axes = plt.subplots(4, n, figsize=(5.2 * n, 15.5), squeeze=False)

    for col, stem in enumerate(stems):
        d = data[stem]
        t_vid = np.asarray(d["t_vid"])
        hv = np.asarray(d["height"]) * 100.0

        # --- row 1: both instruments' vertical, one clock -------------------
        ax = axes[0][col]
        for k, (a, b) in enumerate(d["bounds"]):
            ax.axvspan(d["t"][a], d["t"][b - 1], color="0.88", zorder=0,
                       label="IMU rep window" if k == 0 else None)
        ax.plot(t_vid, hv - np.nanmin(hv), lw=1.1, color="tab:blue",
                label="video (conic markers)")
        for k, r in enumerate(d["per_rep"]):
            if not r.get("covered"):
                continue
            c = np.asarray(r["curve_pipeline"])
            tt = np.linspace(d["t"][d["bounds"][k][0]], d["t"][d["bounds"][k][1] - 1],
                             len(c))
            ax.plot(tt, (c[:, 1] - c[:, 1].min()) * 100, lw=1.1, color="tab:red",
                    label="reconstruction" if k == 0 else None)
        ax.set_title(f"{stem}\nn_rim {d['n_rim']}   coverage {d['coverage']*100:.1f}%"
                     f"   residual {d['resid_px']:.2f} px", fontsize=9)
        ax.set_ylabel("height above lowest, cm", fontsize=8)
        ax.legend(fontsize=6.5, loc="upper right")

        # --- row 2: per-rep vertical ROM ------------------------------------
        ax = axes[1][col]
        vid_rom = [r["video_rom_cm"] for r in d["per_rep"] if r.get("covered")]
        imu_rom = d["imu_rom_cm"]
        x = np.arange(len(vid_rom))
        ax.bar(x - 0.2, imu_rom[:len(vid_rom)], 0.4, label="reconstruction",
               color="tab:red", alpha=.8)
        ax.bar(x + 0.2, vid_rom, 0.4, label="video", color="tab:blue", alpha=.8)
        ax.axhspan(53, 61, color="tab:green", alpha=.12, zorder=0,
                   label="VERTICAL_ROM_M band")
        ax.set_ylabel("per-rep vertical ROM, cm", fontsize=8)
        ax.set_xlabel("rep", fontsize=8)
        ax.legend(fontsize=6.5)

        # --- row 3: HORIZONTAL, the actual question -------------------------
        ax = axes[2][col]
        for k, r in enumerate(d["per_rep"]):
            if not r.get("covered"):
                continue
            v = np.asarray(r["curve_video"]) * 100
            p = np.asarray(r["curve_pipeline"]) * 100
            ax.plot(v[:, 0] - v[0, 0], v[:, 1] - v[:, 1].min(), lw=1.0,
                    color="tab:blue", alpha=.75,
                    label="video" if k == 0 else None)
            ax.plot(p[:, 0] - p[0, 0], p[:, 1] - p[:, 1].min(), lw=1.0,
                    color="tab:red", alpha=.75,
                    label="reconstruction" if k == 0 else None)
        ax.axvline(0.0, color="0.4", ls="--", lw=1.0, label="flat-line null")
        beats = d["beats_null"]
        verdict = "BEATS null" if beats >= 1.0 else "WORSE than null"
        ax.set_title(f"horizontal  h_rms {d['h_rms']:.2f} cm   null "
                     f"{d['null_h_rms']:.2f}   beats_null {beats:.2f}  ({verdict})",
                     fontsize=8.5,
                     color="tab:green" if beats >= 1.0 else "tab:red")
        ax.set_xlabel("fore-aft, cm (spec ~1 cm)", fontsize=8)
        ax.set_ylabel("height, cm", fontsize=8)
        ax.legend(fontsize=6.5)

        # --- row 4: where the referee is strong ----------------------------
        ax = axes[3][col]
        dm = np.asarray(d["decile_markers"], dtype=float)
        ax.bar(np.arange(len(dm)), dm, color="tab:purple", alpha=.75)
        ax.axhline(d["n_rim"], color="0.3", ls="--", lw=1.0,
                   label=f"all {d['n_rim']} found")
        ax.set_xlabel("decile of travel   (0 = floor, 9 = lockout)", fontsize=8)
        ax.set_ylabel("markers matched (median)", fontsize=8)
        ax.legend(fontsize=6.5)

    for ax in axes.ravel():
        ax.tick_params(labelsize=7)
        ax.grid(alpha=.25)

    fig.suptitle(
        "The first 8-sticker captures: conic marker referee vs the reconstruction (C27)\n"
        "Row 3 is the question this project exists to answer; row 4 says where "
        "the referee can be believed",
        fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    return fig


def plot_squat_pause_segmentation(data: dict):
    """The paused-squat short-count, and why the cadence constant could not move.

    C31a, 2026-08-06. Three panels of band-passed vertical velocity — the
    signal `segment.rep_bounds` actually works on — for the two paused squats
    that counted 3 of 4 and the one that counted 4 of 4, then a fourth panel
    showing the tolerance each capture admits under each rule.

    The figure exists to make one thing visible: the dropped rep is a REAL rep,
    sitting in the cluster with its siblings, and it is discarded purely
    because the gap before it is longer than the others. `squat_pause_140x4_3`
    drops its LAST rep and `squat_pause_140x4_2` its FIRST, which is why the
    fourth panel matters — the mechanism is the gap ratio, not a position in
    the set.

    Panel 4 is the negative result and the reason a re-tune was not the fix.
    Under the shipping rule `bench_spoto_90x5_1` counts correctly only below
    1.572 and `squat_pause_140x4_3` only above 1.576, so the two grey bars
    never overlap and no constant satisfies both. The green bars do overlap,
    over 1.460-1.528.

    `data` comes from `run.draw_paused_squat`; see it for the shape.
    """
    CHOSE, DROP, REJ = "#2f7d4f", "#c0392b", "#9aa4ad"
    D = data
    names = [k for k in D if not k.startswith("_")]
    fig = plt.figure(figsize=(15.5, 15.0))
    gs = fig.add_gridspec(4, 1, height_ratios=[1, 1, 1, 1.35], hspace=0.58,
                          left=0.138, right=0.982, top=0.898, bottom=0.075)

    for row, name in enumerate(names):
        c = D[name]; ax = fig.add_subplot(gs[row])
        t, vb = c["t"], c["vb"]
        old, new, exp = c["old"], c["new"], c["exp"]
        lo = min(t[old[0][0]], t[new[0][0]]) - 6.5
        hi = max(t[old[-1][1] - 1], t[new[-1][1] - 1]) + 6.5
        m = (t >= lo) & (t <= hi)
        span = vb[m].max() - vb[m].min()
        ymin, ymax = vb[m].min() - 0.34 * span, vb[m].max() + 0.46 * span
        ax.set_ylim(ymin, ymax); ax.set_xlim(lo, hi)
        ax.axhline(0, color="#ccd2d8", lw=0.8, zorder=1)

        for (a, b) in new:
            recovered = not any(abs(t[a] - t[oa]) < 0.6 for oa, ob in old)
            ax.axvspan(t[a], t[b - 1], zorder=2,
                       facecolor=DROP if recovered else CHOSE,
                       alpha=0.26 if recovered else 0.15,
                       hatch="///" if recovered else None,
                       edgecolor=DROP if recovered else "none", lw=0.0)
            if recovered:
                ax.text((t[a] + t[b - 1]) / 2, ymax - 0.04 * span,
                        "REP DROPPED\nby the shipping rule", ha="center",
                        va="top", fontsize=11, fontweight="bold", color=DROP,
                        zorder=9)

        cl = set(np.round(c["cluster"], 3))
        for (a, b, pk, ar) in c["lobes"]:
            inc = round(float(t[pk]), 3) in cl
            if not inc:
                ax.axvspan(t[a], t[b - 1], facecolor=REJ, alpha=0.17, zorder=2)
            ax.plot(t[pk], vb[pk], "v", ms=9.5 if inc else 7,
                    color=CHOSE if inc else REJ, mec="white", mew=0.9, zorder=8)

        ax.plot(t[m], vb[m], color="#1f2d3a", lw=1.3, zorder=6)

        ct = np.array(c["cluster"]); gaps = np.diff(ct)
        ytxt = ymin + 0.13 * span
        for i, g in enumerate(gaps):
            ax.annotate("", xy=(ct[i], ytxt), xytext=(ct[i + 1], ytxt),
                        arrowprops=dict(arrowstyle="<->", color="#34495e", lw=1.2),
                        zorder=9)
            ax.text((ct[i] + ct[i + 1]) / 2, ytxt, f" {g:.2f} s ", ha="center",
                    va="center", fontsize=10.5, color="#1f2d3a", zorder=10,
                    bbox=dict(fc="white", ec="none", pad=1.4))
        steps = [max(gaps[i + 1] / gaps[i], gaps[i] / gaps[i + 1])
                 for i in range(len(gaps) - 1)]
        short = len(old) != exp
        ax.set_title(
            f"{name}     shipping rule {len(old)}/{exp}"
            f"{'  ✗ SHORT' if short else '  ✓'}"
            f"          C31a rule {len(new)}/{exp}  ✓",
            fontsize=12.5, loc="left", pad=17,
            color=DROP if short else "#1f2d3a", fontweight="bold")
        ax.text(0, 1.015, f"gaps {', '.join(f'{g:.2f}' for g in gaps)} s"
                f"          global spread max/min = {gaps.max()/gaps.min():.3f}"
                f"          worst ADJACENT step = {max(steps):.3f}",
                transform=ax.transAxes, fontsize=10.5, color="#4a5866")
        ax.set_ylabel("band-passed\nvertical velocity (m/s)", fontsize=10)
        ax.set_xlabel("time (s)", fontsize=10, labelpad=1)
        ax.tick_params(labelsize=9)
        for s in ("top", "right"): ax.spines[s].set_visible(False)

    # ---------------- panel 4 --------------------------------------------
    ax = fig.add_subplot(gs[3])
    old_i, new_i = D["_tol"]["old"], D["_tol"]["new"]
    X0, X1 = 1.36, 1.66
    # captures that actually bind anywhere near the decision
    def binds(k):
        return any(X0 < e < X1 for src in (old_i, new_i)
                   for e in src[k][:2] if e is not None)
    show = sorted([k for k in old_i if binds(k)],
                  key=lambda k: -(old_i[k][0] or 0))
    ypos = np.arange(len(show))[::-1]
    for y, k in zip(ypos, show):
        for dy, src, col in ((0.20, old_i, "#8f9aa5"), (-0.20, new_i, CHOSE)):
            lo_, hi_, _ = src[k]
            if lo_ is None: continue
            ax.plot([max(lo_, X0 - 0.02), min(hi_, X1 + 0.02)], [y + dy] * 2,
                    lw=11, color=col, solid_capstyle="butt", alpha=0.93,
                    zorder=4)
            if lo_ > X0:
                ax.plot([lo_], [y + dy], "|", color="white", ms=11, mew=2.2,
                        zorder=5)
    ax.set_yticks(ypos)
    ax.set_yticklabels([k.rsplit("_2026", 1)[0] for k in show], fontsize=10)

    B = "bench_spoto_90x5_1_20260730_125107.csv"
    S = "squat_pause_140x4_3_20260806_113817.csv"
    ob_hi, os_lo = old_i[B][1], old_i[S][0]
    nb_hi, ns_lo = new_i[B][1], new_i[S][0]
    ax.axvspan(ns_lo, nb_hi, color=CHOSE, alpha=0.12, zorder=0)
    ax.axvline(1.50, color="#1f2d3a", ls="--", lw=1.4, zorder=6)

    ymax_ = len(show) - 0.30
    ax.set_ylim(-1.05, ymax_ + 0.95)
    ax.set_xlim(X0, X1)

    # the gap where NEITHER binding capture is satisfied
    ax.axvspan(ob_hi, os_lo, color=DROP, alpha=0.30, zorder=1)
    ax.annotate(f"NO tolerance counts both\nbench ends {ob_hi:.3f}, squat starts {os_lo:.3f}",
                xy=((ob_hi + os_lo) / 2, ymax_ + 0.10),
                xytext=(X1 - 0.005, ymax_ + 0.72), ha="right", va="center",
                fontsize=10.5, color=DROP, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color=DROP, lw=1.6,
                                connectionstyle="arc3,rad=0.18"))
    ax.annotate("", xy=(ns_lo, ymax_ + 0.22), xytext=(nb_hi, ymax_ + 0.22),
                arrowprops=dict(arrowstyle="<->", color=CHOSE, lw=1.8))
    ax.text((ns_lo + nb_hi) / 2, ymax_ + 0.46,
            f"C31a plateau {ns_lo:.3f} \u2013 {nb_hi:.3f}  (4.74% wide)",
            ha="center", va="center", fontsize=10.5, color=CHOSE,
            fontweight="bold")
    ax.text(1.50, -0.92, "ships 1.50", fontsize=10.5, ha="center", va="bottom",
            fontweight="bold", color="#1f2d3a",
            bbox=dict(fc="white", ec="none", pad=1.5))
    ax.set_xlabel("cadence tolerance — bar spans every value at which that capture counts "
                  "correctly", fontsize=10.5)
    ax.set_title("Why the constant could not be re-tuned. Captures not shown admit every "
                 "value in this range under both rules.",
                 fontsize=12.5, loc="left", pad=40, fontweight="bold")
    ax.tick_params(labelsize=9.5)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.legend(handles=[Patch(fc="#8f9aa5", label="shipping rule — run's global spread, max/min"),
                       Patch(fc=CHOSE, label="C31a rule — worst step between ADJACENT gaps")],
              loc="upper left", fontsize=10, frameon=False)

    fig.legend(handles=[
        Patch(fc=CHOSE, alpha=0.35, label="rep window (both rules agree)"),
        Patch(fc=DROP, alpha=0.40, hatch="///", label="rep the shipping rule DROPS"),
        Patch(fc=REJ, alpha=0.25, label="lobe rejected before cadence"),
        Line2D([], [], marker="v", ls="", color=CHOSE, mec="white",
               label="concentric peak, in the cluster"),
        Line2D([], [], marker="v", ls="", color=REJ, mec="white",
               label="concentric peak, not in the cluster")],
        loc="upper center", ncol=5, fontsize=10.5, frameon=False,
        bbox_to_anchor=(0.5, 0.958))
    fig.suptitle("analysis/47 — the paused squat short-count: `_longest_cadence` drops a real rep\n"
                 "a paused set's cadence LENGTHENS rep by rep, so its global gap spread is "
                 "indistinguishable from a post-set movement",
                 fontsize=15, y=0.99)
    return fig


def plot_bar_path_with_d(data: dict):
    """C31 — the bar path with step 6 (the wrist lever `R(t).d`) off and on.

    `data` maps stem -> {"off": vs_truth dict, "on": vs_truth dict, "d": (3,)}.
    Both dicts must come from the SAME tracked video path, so the grey truth
    curve is one curve and not two; only `pipeline.run`'s `wrist_offset`
    differs between them.

    Why this figure exists. `d` was unmeasurable for the life of this project —
    B2 proved it could not be FITTED from the video (leave-one-out returned
    |d| = 129 cm) — and the owner tape-measured it on 2026-08-06. Step 6 is the
    only stage that was OFF because a number was missing rather than because it
    had been rejected, so "what does the path look like with it on" had never
    been drawn.

    Read the three captures as a disagreement, not a result. `d` helps the
    acceleration on 6 of 6 benches and the POSITION on only 3 of 6, so the
    panels are chosen to show both directions: one deadlift, one bench where it
    clearly helped and one where it clearly hurt. A figure showing only the
    wins would be the exact failure this project keeps repeating.
    """
    stems = list(data)
    fig, axes = plt.subplots(1, len(stems), figsize=(4.2 * len(stems), 6.4),
                             squeeze=False)
    flat = axes.ravel()

    for ax, stem in zip(flat, stems):
        off, on = data[stem]["off"], data[stem]["on"]
        goff = [r for r in off["per_rep"] if r.get("covered")]
        gon = [r for r in on["per_rep"] if r.get("covered")]

        for i, r in enumerate(goff):
            vid = r["curve_video"] * 100
            ax.plot(vid[:, 0], vid[:, 1], color="0.55", lw=2.4,
                    label="video (truth)" if i == 0 else None, zorder=2)
        for i, r in enumerate(goff):
            p = r["curve_pipeline"] * 100
            ax.plot(p[:, 0], p[:, 1], color="#c2410c", lw=1.2, alpha=0.85,
                    ls="--", label="step 6 OFF (was the default)" if i == 0 else None,
                    zorder=3)
        for i, r in enumerate(gon):
            p = r["curve_pipeline"] * 100
            ax.plot(p[:, 0], p[:, 1], color="#1d4ed8", lw=1.4, alpha=0.9,
                    label="step 6 ON (measured d)" if i == 0 else None,
                    zorder=4)

        ax.set_aspect(1.0 / STRETCH)
        ho, hn = off["pipeline_h_rms"], on["pipeline_h_rms"]
        bo, bn = off["beats_null"], on["beats_null"]
        verdict = "BETTER" if hn < ho else "WORSE"
        colour = "#166534" if hn < ho else "#b91c1c"
        d = data[stem]["d"]
        ax.set_title(
            f"{stem}\n"
            f"h rms  {ho:.2f} -> {hn:.2f} cm   {verdict}\n"
            f"beats_null  {bo:.2f} -> {bn:.2f}\n"
            f"d = ({d[0]:+.2f}, {d[1]:+.2f}, {d[2]:+.2f}) m,  |d| = "
            f"{float(np.linalg.norm(d)) * 100:.1f} cm",
            fontsize=8.5, color=colour)
        ax.set_xlabel("fore-aft (cm)", fontsize=8)
        ax.set_ylabel("vertical (cm)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, frameon=False, loc="best")

    fig.suptitle(
        "analysis/48 — the bar path with the wrist lever R(t).d removed, "
        "against the video\n"
        "d is a TAPE MEASUREMENT (owner, 2026-08-06), not a fit. Reps "
        "start-aligned, fore-aft stretched 4x as step 9 draws it.\n"
        "It helps the deadlift and one bench and HURTS the paused bench — that "
        "mixed metric was the argument for shipping OFF when this figure was "
        "made (7bc4bcb). The owner shipped it ON anyway hours later (70b2a63) "
        "on the geometry argument in pipeline.run's docstring, not on this "
        "metric — read the title's verdicts as history, not as the default.",
        fontsize=11, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    return fig


def plot_pause_attitude(data: dict):
    """C31 — does a PAUSE let Core Motion re-reference gravity mid-rep?

    `data` carries `ty` (per-capture tilt/yaw ratios, quasi-static and dynamic)
    and `prof` (per-lift median tilt-correction profiles across the rep).

    The observable needs no video. Core Motion reports an attitude; the gyro
    reports a rate. The difference between the attitude increment and the gyro's
    is what the FUSION added — and gravity can only correct TILT, never yaw
    about gravity, so the tilt/yaw ratio says whether the accelerometer is being
    trusted. Numerical error has no such preference, which is what makes the
    ratio the decisive statistic rather than the magnitude.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.4))

    ax = axes[0]
    names = list(data["ty"])
    qs = [data["ty"][n]["ratio_qs"] for n in names]
    dyn = [data["ty"][n]["ratio_dyn"] for n in names]
    y = np.arange(len(names))
    ax.scatter(dyn, y, s=26, color="#c2410c", label="moving")
    ax.scatter(qs, y, s=26, color="#1d4ed8", label="quasi-static")
    for i, (a, b) in enumerate(zip(dyn, qs)):
        ax.plot([a, b], [i, i], color="0.75", lw=0.8, zorder=0)
    ax.axvline(1.0, color="0.3", ls=":", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([n[:26] for n in names], fontsize=5.5)
    ax.set_xlabel("tilt / yaw in the fusion correction", fontsize=8)
    rose = sum(1 for n in names
               if data["ty"][n]["ratio_qs"] > data["ty"][n]["ratio_dyn"])
    ax.set_title(f"Gravity can only correct TILT.\nThe ratio rises when still on "
                 f"{rose} of {len(names)} —\nso the mechanism is REAL.", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    ax.grid(alpha=0.25, axis="x")

    for ax, lift in zip(axes[1:], ("bench", "squat")):
        ph = (np.arange(len(data["prof"][lift]["paused"])) + 0.5) / len(
            data["prof"][lift]["paused"])
        ax.plot(ph, data["prof"][lift]["paused"], lw=2.2, color="#b91c1c",
                marker="o", ms=3, label="PAUSED")
        ax.plot(ph, data["prof"][lift]["continuous"], lw=2.2, color="#166534",
                marker="s", ms=3, label="continuous")
        ax.set_xlabel("phase through the rep", fontsize=8)
        ax.set_ylabel("tilt correction (deg/s)", fontsize=8)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, frameon=False)
        verdict = data["prof"][lift]["verdict"]
        ax.set_title(f"{lift}\n{verdict}", fontsize=9)
    axes[1].set_ylim(bottom=0)
    axes[2].set_ylim(bottom=0)

    fig.suptitle(
        "analysis/49 — the owner's hypothesis: does a pause let the accelerometer "
        "find g, so Core Motion corrects tilt MID-REP?\n"
        "Half right. The mechanism is real and visible, but it separates the two "
        "lifts rather than the two styles: a paused SQUAT concentrates the "
        "correction mid-rep, a paused BENCH does not.",
        fontsize=11, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def plot_pipeline_now(panels: list):
    """C31 — what the branch pipeline actually produces, on all three lifts.

    Each entry of `panels` is a dict with `stem`, `paths` (list of (M,2) arrays,
    along-axis and up, in metres), optional `video` (same shape), and `caption`.

    This is the product view: step 9's output, reps overlaid and start-aligned,
    fore-aft stretched 4x exactly as the display would. It exists because the
    numbers in this repo are abstractions until you see the shape they describe
    — and because the branch changed what the pipeline computes (step 6 is on),
    so every figure drawn before 2026-08-06 shows a different quantity.

    Squat panels carried no video because `metrics.vs_truth` refused squat.
    **That refusal was removed in G2 (2026-08-15)** — its stated reason was
    about the v1 plate template on footage F1 deleted — so a squat panel now
    carries video whenever the capture syncs. The paragraph below is kept
    because its caution about which squat clips track is what the refusal's
    removal had to answer, and it was answered by `src/vtrack/` rather than by
    relaxing anything.
    That refusal is now STALE rather than wrong-headed — its stated reason is
    about the old template footage. Note the replacement claim needs care too:
    only TWO of the four 8-sticker squat clips track cleanly; `squat_170x1` and
    `squat_pause_140x4_3` report 14.0 and 24.7 cm of travel against 65-70 cm
    squats (C31, corrected 2026-08-07). And nobody has built a validated squat
    sync. So the honest thing is to draw the reconstruction alone and say so.
    """
    n = len(panels)
    cols = 3
    rows = -(-n // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4.4 * cols, 6.6 * rows),
                             squeeze=False)
    flat = axes.ravel()

    for ax, p in zip(flat, panels):
        vid = p.get("video")
        if vid is not None:
            for i, v in enumerate(vid):
                ax.plot(v[:, 0] * 100, v[:, 1] * 100, color="0.55", lw=2.4,
                        label="video (truth)" if i == 0 else None, zorder=2)
        for i, q in enumerate(p["paths"]):
            ax.plot(q[:, 0] * 100, q[:, 1] * 100, lw=1.6, alpha=0.9,
                    color="#1d4ed8" if vid is not None else None,
                    label=("reconstruction" if vid is not None else f"rep {i+1}")
                    if i == 0 or vid is None else None, zorder=3)
        ax.set_aspect(1.0 / STRETCH)
        ax.set_title(p["caption"], fontsize=8.5)
        ax.set_xlabel("fore-aft (cm)", fontsize=8)
        ax.set_ylabel("vertical (cm)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=6.5, frameon=False, loc="best")
    for ax in flat[n:]:
        ax.axis("off")

    fig.suptitle(
        "analysis/50 — what the branch pipeline produces, all three lifts, "
        "step 6 ON\n"
        "Reps overlaid and start-aligned, fore-aft stretched 4x as the display "
        "would draw it. Grey is the video where a referee exists.\n"
        "Squat has no referee: vs_truth still refuses it, and only two of the "
        "four 8-sticker squat clips track cleanly.",
        fontsize=11, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def plot_jump_with_d(rows: dict, arms: list):
    """C31 — do C29's jump correction and step 6's `d` compose, or overlap?

    `rows` maps capture stem -> arm -> (h_rms, beats_null, v_rms, n). `arms` is
    the ordered list of arm names.

    All four arms use the SAME rest-to-rest windows, so every bar is scored on
    the same spans and the comparison is internal. The control is C29's own
    honest baseline — rest windows with no correction — NOT the shipping
    number, which is measured on different windows entirely.
    """
    stems = list(rows)
    colours = {"control": "0.6", "C29": "#166534", "d": "#c2410c",
               "both": "#1d4ed8"}
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 5.6))
    x = np.arange(len(stems))
    w = 0.8 / len(arms)

    for j, arm in enumerate(arms):
        h = [rows[s][arm][0] for s in stems]
        b = [rows[s][arm][1] for s in stems]
        off = (j - (len(arms) - 1) / 2) * w
        axes[0].bar(x + off, h, w, label=arm, color=colours.get(arm))
        axes[1].bar(x + off, b, w, label=arm, color=colours.get(arm))

    axes[0].set_ylabel("per-rep horizontal rms (cm)", fontsize=9)
    axes[0].set_title("C29's jump correction does the work.\n"
                      "`d` on top of it buys nothing.", fontsize=10)
    axes[1].axhline(1.0, color="0.2", ls="--", lw=1.2)
    axes[1].set_ylabel("beats_null  (>1 = better than a flat line)", fontsize=9)
    # C29 reported deadlift_155x6_1 AND deadlift_180x3 crossing 1.0. Re-run
    # here, only 155x6_1 does (1.21); 180x3 reaches 0.89. Stated rather than
    # rounded up — C29's control and treatment medians reproduce exactly, so
    # this is a per-capture difference, not a broken reproduction.
    axes[1].set_title("ONE capture crosses 1.0 under C29 (155x6_1, 1.21).\n"
                      "C29 reported 180x3 crossing too; here it reaches 0.89",
                      fontsize=10)
    for ax in axes:
        ax.set_xticks(x)
        ax.set_xticklabels([s[:20] for s in stems], rotation=20, ha="right",
                           fontsize=7)
        ax.legend(fontsize=8, frameon=False)
        ax.grid(alpha=0.25, axis="y")

    fig.suptitle(
        "analysis/51 — do the impact-localised correction and the wrist lever "
        "COMPOSE? No: they correct the same thing.\n"
        "Median h rms: control 10.66 -> C29 3.93 -> +d 3.89 cm. `d` alone "
        "reaches only 9.82. Three captures better with `d`, three worse.\n"
        "Both act at the FLOOR IMPACT: |d/dt(R.d)| peaks there at 7.8x the rep "
        "median. Not a turnaround — the arms hang near-vertical and nothing "
        "reorients — but STRAP RINGING, the watch moving after the bar stops.",
        fontsize=11, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    return fig


def plot_deadlift_parabola(dl, bn, arms):
    """D1 — where the deadlift's invented fore-aft comes from. analysis/52.

    `dl` and `bn` are per-capture dicts built by `run.py --dlparabola`:
    `name`, `r` (a pipeline result), `vt` (its `vs_truth`), and `per`, one entry
    per scored rep holding `oracle.parabola_fit` of the reconstruction's path
    and of the video's. `arms` pairs the shipping row with the rejected
    parabola-detrend row for panel F.

    Six panels, and the order is the argument:

    A  per-rep fore-aft excursion in rep order. The reconstruction's grows
       monotonically through the set (7.6 -> 34.8 cm on `deadlift_160x6_1`)
       while the video's stays flat. Rep 0 is nearly right; the last rep is
       not. That alone rules out anything that happens identically every rep.
    B  one rep's path with `c*tau(tau-T)/2` over it. It is a parabola.
    C  the impact window's share of the excursion, swept over half-widths of
       0.10 to 0.50 s. It never reaches half on the marker-refereed captures,
       so the floor impact is NOT where this is generated — which is the
       measurement D1 set out to make and the hypothesis it killed.
    D  the reconstruction's parabola coefficient against the video's own. On
       deadlift 5.0x too big and uncorrelated (r = +0.18, n = 30); on bench
       0.7x and correlated. The same split C30b found in acceleration.
    E  the same coefficient as an effective tilt, asin(|c|/g), against C6's
       0.05-0.27 deg measured at a still HOLD. Sub-degree throughout: a third
       of a metre of invented travel is a fraction of a degree, times T^2.
    F  the rejected correction. `beats_null` enters spanning 0.13-5.39 and
       leaves spanning 0.76-1.16 — it converts every capture into the flat-line
       null, which is a gain on deadlift and a loss on bench.
    """
    from . import oracle

    fig, ax = plt.subplots(2, 3, figsize=(16.5, 9))

    # -- A: per-rep excursion in order, recon vs video -----------------------
    a = ax[0, 0]
    cols = plt.cm.viridis(np.linspace(0, .85, len(dl)))
    for c, row in zip(cols, dl):
        ks = [p["k"] for p in row["per"]]
        a.plot(ks, [p["rec"]["excursion_m"] * 100 for p in row["per"]], "o-",
               color=c, label=row["name"].replace("deadlift_", ""))
        a.plot(ks, [p["video_exc"] * 100 for p in row["per"]], "s--",
               color=c, alpha=.45, ms=4)
    a.set_xlabel("rep index within the set")
    a.set_ylabel("fore-aft excursion, cm")
    a.set_title("A  It GROWS through the set\n"
                "solid = reconstruction, dashed = video (flat)", fontsize=10)
    a.legend(fontsize=6.5, ncol=2)

    # -- B: one rep, path and the parabola -----------------------------------
    a = ax[0, 1]
    row = [r for r in dl if r["name"] == "deadlift_160x6_1"][0]
    for p, col in ((row["per"][0], "steelblue"), (row["per"][-1], "seagreen")):
        tau = np.linspace(0, p["T"], len(p["curve"]))
        fitc = p["rec"]["c"] * tau * (tau - p["T"]) / 2
        a.plot(tau, p["curve"] * 100, lw=2, color=col,
               label=f"rep {p['k']} recon  (r2={p['rec']['r2']:.2f}, "
                     f"{p['rec']['tilt_deg']:.2f} deg)")
        a.plot(tau, fitc * 100, "k:", lw=1.2)
        a.plot(tau, p["vcurve"] * 100, lw=1.4, alpha=.6, ls="--", color=col,
               label=f"rep {p['k']} video")
    a.set_xlabel("time through the rep, s")
    a.set_ylabel("fore-aft, cm")
    a.set_title("B  The path IS a parabola\n"
                "deadlift_160x6_1, first and last rep; dotted = c*tau(tau-T)/2",
                fontsize=10)
    a.legend(fontsize=6.5)

    # -- C: attribution ------------------------------------------------------
    a = ax[0, 2]
    widths = [0.10, 0.20, 0.30, 0.50]
    for c, row in zip(cols, dl):
        fr = []
        for hw in widths:
            mi = oracle.impact_mask(row["r"], hw)
            pa = oracle.rep_attribution(row["r"], {"i": mi, "e": ~mi},
                                        row["vt"]["axis"])
            axis = np.asarray(row["vt"]["axis"], float)[:2]
            axis = axis / np.linalg.norm(axis)
            f = []
            for k in range(len(pa["FULL"])):
                full = np.ptp(pa["FULL"][k][:, :2] @ axis)
                imp = np.ptp(pa["i"][k][:, :2] @ axis)
                f.append(imp / full)
            fr.append(np.median(f) * 100)
        a.plot(widths, fr, "o-", color=c)
    a.axhline(50, color="crimson", ls="--", lw=1)
    a.text(0.5, 52, "D1's pre-registered 'dominant' line", color="crimson", fontsize=7)
    a.set_xlabel("half-width of the window around each floor impact, s")
    a.set_ylabel("% of the per-rep excursion")
    a.set_ylim(0, 100)
    a.set_title("C  It is NOT the impact\n"
                "the ringing window never dominates, at any width", fontsize=10)

    # -- D: recon parabola vs video parabola ---------------------------------
    a = ax[1, 0]
    for rows, col, lab in ((dl, "crimson", "deadlift"), (bn, "steelblue", "bench")):
        x = [p["vid"]["c"] for r in rows for p in r["per"]]
        y = [p["rec"]["c"] for r in rows for p in r["per"]]
        rr = np.corrcoef(x, y)[0, 1]
        ratio = np.sqrt(np.mean(np.square(y))) / np.sqrt(np.mean(np.square(x)))
        a.scatter(x, y, s=22, color=col, alpha=.75,
                  label=f"{lab}  n={len(x)}  r={rr:+.2f}  {ratio:.1f}x")
    lim = 0.2
    a.plot([-lim, lim], [-lim, lim], "k-", lw=.8, alpha=.5)
    a.axhline(0, color="k", lw=.5); a.axvline(0, color="k", lw=.5)
    a.set_xlim(-lim, lim); a.set_ylim(-lim, lim)
    a.set_xlabel("video's own parabola coefficient, m/s^2")
    a.set_ylabel("reconstruction's, m/s^2")
    a.set_title("D  On deadlift the parabola is INVENTED\n"
                "on bench it tracks the bar (line = agreement)", fontsize=10)
    a.legend(fontsize=7, loc="upper left")

    # -- E: the effective tilt ------------------------------------------------
    a = ax[1, 1]
    for c, row in zip(cols, dl):
        a.plot([p["k"] for p in row["per"]],
               [p["rec"]["tilt_deg"] for p in row["per"]], "o-", color=c)
    a.axhspan(0.05, 0.27, color="grey", alpha=.25)
    a.text(0.02, 0.005, "C6: attitude error measured at a still HOLD, 0.05-0.27 deg",
           fontsize=7, color="dimgrey", va="bottom")
    a.set_ylim(0, None)
    a.set_xlabel("rep index within the set")
    a.set_ylabel("effective tilt, degrees")
    a.set_title("E  A third of a metre is a fraction of a degree\n"
                "theta = asin(|c|/g); T^2 does the rest", fontsize=10)

    # -- F: the rejected arm --------------------------------------------------
    a = ax[1, 2]
    nm = [x[0]["name"] for x in arms]
    y0 = [x[0]["bn"] for x in arms]
    y1 = [x[1]["bn"] for x in arms]
    ypos = np.arange(len(nm))
    for i, (b0, b1) in enumerate(zip(y0, y1)):
        a.annotate("", xy=(b1, i), xytext=(b0, i),
                   arrowprops=dict(arrowstyle="->", lw=1.4,
                                   color="seagreen" if b1 > b0 else "crimson"))
    a.scatter(y0, ypos, s=26, color="k", zorder=3, label="shipping")
    a.scatter(y1, ypos, s=26, facecolor="w", edgecolor="k", zorder=3,
              label="+ parabola removed")
    a.axvline(1.0, color="crimson", ls="--", lw=1)
    a.set_yticks(ypos)
    a.set_yticklabels([n.replace("deadlift_", "DL ").replace("bench_", "B ")
                       for n in nm], fontsize=6)
    a.set_xscale("log")
    a.set_xticks([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
    a.set_xticklabels(["0.1", "0.2", "0.5", "1.0", "2.0", "5.0"])
    a.minorticks_off()
    a.set_xlabel("beats_null   (1.0 = a flat vertical line)")
    a.set_title("F  REJECTED: it collapses everything onto the null\n"
                "0.13-5.39 in, 0.76-1.16 out. Bench loses what deadlift gains",
                fontsize=10)
    a.legend(fontsize=7, loc="lower right")

    for row in ax:
        for a_ in row:
            a_.grid(alpha=.25)
            a_.tick_params(labelsize=8)
    fig.suptitle(
        "D1 — the deadlift's invented fore-aft is ONE PARABOLA PER REP, and it grows through the set\n"
        "not the floor impact, not a constant of the capture: a 0.03-0.94 deg tilt error amplified by T^2",
        fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def plot_tracking_review(path: dict, stem: str, info: dict | None = None):
    """C31 — is this track usable? One figure per video, meant to be LOOKED AT.

    `path` is a tracked bar-path dict; `info` is `tracked.review(video)`.

    The figure this project should have had from the start. Two of the four
    squat clips fed 14 and 24 cm of travel into comparisons for days, because
    the tracker had locked onto gym furniture and every summary statistic —
    coverage 96.7%, residual 1.11 px — said healthy. Nobody was ever shown the
    path. A person glancing at the top-right panel catches that instantly.

    Top row is the whole clip: height against time with the video's own rep
    windows shaded, and the bar path. Below, one panel per rep, so a track that
    is fine for four reps and loses the bar on the fifth is visible as such
    rather than averaged away.

    The rep windows come from `tracked.video_reps`, which uses the video alone.
    They are trough-to-trough, so half a rep out of phase with
    `segment.rep_bounds`; that is deliberate and is explained there.
    """
    t = np.asarray(path["t"], dtype=float)
    x = np.asarray(path["x"], dtype=float) * 100
    h = np.asarray(path["height"], dtype=float) * 100
    reps = (info or {}).get("reps") or []

    n = len(reps)
    cols = max(4, min(6, n if n else 4))
    rep_rows = -(-n // cols) if n else 0
    fig = plt.figure(figsize=(4.0 * cols, 4.6 + 3.6 * rep_rows))
    gs = fig.add_gridspec(1 + rep_rows, cols, height_ratios=[1.25] + [1] * rep_rows)

    # --- whole clip: height against time -----------------------------------
    a = fig.add_subplot(gs[0, :max(2, cols // 2)])
    a.plot(t, h, lw=1.3, color="#1d4ed8")
    for i, (i0, i1) in enumerate(reps):
        a.axvspan(t[i0], t[i1], color="#166534", alpha=0.10)
        a.text((t[i0] + t[i1]) / 2, np.nanmax(h), str(i + 1), ha="center",
               va="top", fontsize=8, color="#166534")
    gaps = ~np.isfinite(h)
    if gaps.any():
        a.plot(t[gaps], np.full(gaps.sum(), np.nanmin(h)), "|", color="#b91c1c",
               ms=8, label="frames with no track")
        a.legend(fontsize=7, frameon=False)
    a.set_xlabel("time (s)", fontsize=8)
    a.set_ylabel("height (cm)", fontsize=8)
    a.set_title("whole clip — height, with the video's own rep windows",
                fontsize=9)
    a.grid(alpha=0.25)

    # --- whole clip: the path ----------------------------------------------
    b = fig.add_subplot(gs[0, max(2, cols // 2):])
    b.plot(x, h, lw=1.0, color="0.35")
    b.set_xlabel("fore-aft (cm)", fontsize=8)
    b.set_ylabel("height (cm)", fontsize=8)
    b.set_title("whole clip — the tracked bar path", fontsize=9)
    b.grid(alpha=0.25)

    # --- one panel per rep --------------------------------------------------
    for k, (i0, i1) in enumerate(reps):
        ax = fig.add_subplot(gs[1 + k // cols, k % cols])
        # NaN-safe throughout: a mis-tracked clip is exactly the case this
        # figure exists for, and those windows are full of untracked frames.
        # An empty panel captioned "nan" tells the reader nothing about why.
        xr, hr = x[i0:i1], h[i0:i1]
        good = np.isfinite(xr) & np.isfinite(hr)
        if good.any():
            x0 = xr[good][0]
            h0 = hr[good][0]
            ax.plot(xr - x0, hr - h0, lw=1.5, color="#1d4ed8")
            ax.plot(0, 0, "o", ms=4, color="#166534")
            travel = f"{np.nanmax(hr) - np.nanmin(hr):.0f} cm travel"
        else:
            travel = "NO TRACK"
        lost = int((~good).sum())
        note = f", {lost} frames lost" if lost else ""
        ax.set_title(f"rep {k + 1}   {travel}{note}", fontsize=8)
        ax.set_xlabel("fore-aft (cm)", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(alpha=0.25)

    if info:
        want = info.get("expected_reps")
        reps_note = (f"{info['n_reps']} reps found in the video"
                     if want is None else
                     f"{info['n_reps']} reps found in the video, "
                     f"filename says {want}")
        flags = []
        if info.get("implausible"):
            flags.append("*** TRAVEL IMPLAUSIBLE FOR THIS LIFT — the tracker is "
                         "very likely not on the bar ***")
        if not info.get("reps_match", True):
            flags.append(f"*** FOUND {info['n_reps']} REPS, FILENAME SAYS "
                         f"{info['expected_reps']} — do not trust this track ***")
        flag = ("   " + "   ".join(flags)) if flags else ""
        sub = (f"{stem}      tracker {info.get('tracker', '?')}   "
               f"lift {info.get('lift', '?')}   camera on the "
               f"{info.get('camera_side', '?')}, watch on the LEFT wrist\n"
               f"coverage {info['coverage'] * 100:.1f}%   "
               f"travel {info['travel_cm']:.1f} cm   "
               f"fore-aft {info['fore_aft_cm']:.1f} cm   "
               f"median residual {info['residual_px']:.2f} px   "
               f"{reps_note}{flag}")
        bad = info.get("implausible") or not info.get("reps_match", True)
        fig.suptitle(sub, fontsize=10.5, y=0.995, color="#b91c1c" if bad else "0.1")
    else:
        fig.suptitle(stem, fontsize=11, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def plot_segmenter_fixes(data: dict):
    """G1 — the two segmentation defects the 2026-08-08 captures exposed.

    Writes `analysis/53`. Four panels, arranged as evidence then rule, twice.

    The left column is the defect on its own capture with the CACHED VIDEO
    TRACK over the top, because in both cases the video is what settles it: at
    7.03 s on `deadlift_150x4_1` the bar is flat on the floor, and at 10.6 s on
    `bench_117.5x1` it is still in the rack. Neither is arguable from the IMU
    trace alone, which is the whole reason both defects survived a rep-count
    gate.

    The right column is the discriminator with every candidate in the corpus on
    it, so the gate can be read as a plateau rather than as a line through one
    point. That is this project's standing requirement for a constant, and both
    rules meet it from two sides: the wrist-rate gate sits between 28 real
    landings and 4 setup swings, the verticality gate between 36 real reps and
    the setup movement that broke the bench single.

    Verticality does a second job that this figure does not draw: it also ranks
    a DEGENERATE cluster, replacing the displacement rule that was picking the
    drop on `deadlift_200x1`. The amber point is that capture's real pull. See
    `segment._similar_cluster`.
    """
    fig, axes = plt.subplots(2, 2, figsize=(15.5, 9.6))

    # --- A: the counterfeit landing, against the video -------------------
    ax = axes[0][0]
    d = data["impact"]
    ax.plot(d["t"], d["accel_g"], color="#334155", lw=0.7, zorder=2)
    ax.axhline(6.0, color="#94a3b8", ls=":", lw=1.0)
    ax.text(0.6, 6.4, "threshold_g = 6", fontsize=7, color="#64748b")
    for k in d["kept"]:
        ax.axvline(k, color="#16a34a", lw=1.4, alpha=0.75, zorder=1)
    for k in d["rejected"]:
        ax.axvline(k, color="#dc2626", lw=2.0, zorder=1)
        ax.annotate("REJECTED\nwrist swing", (k, 21), fontsize=7.5,
                    color="#dc2626", ha="center", va="top", weight="bold")
    ax.set_ylim(0, 24)
    ax.set_ylabel("|accel| (g)", fontsize=8)
    ax.set_xlabel("time (s)", fontsize=8)

    tw = ax.twinx()
    tw.plot(d["video_t"], d["video_h_cm"], color="#2563eb", lw=1.8, zorder=3)
    tw.set_ylabel("video bar height (cm)", fontsize=8, color="#2563eb")
    tw.tick_params(labelsize=7, colors="#2563eb")
    tw.set_ylim(-4, 70)
    tw.annotate("bar on the floor, 0-11 s", (3.0, 6), fontsize=8,
                color="#2563eb")

    ax.set_title(
        "A. deadlift_150x4_1: five anchors in a four-rep set\n"
        "the 7.03 s spike reaches 7.01 g with the bar provably still down",
        fontsize=9)

    # --- B: the wrist-rate gate, whole corpus ----------------------------
    ax = axes[0][1]
    groups = [("real floor landings", data["quiet"]["landings"], "#16a34a", "o"),
              ("rack collisions (bench, squat)", data["quiet"]["racks"],
               "#0891b2", "s"),
              ("setup wrist swings", data["quiet"]["swings"], "#dc2626", "X")]
    for i, (label, vals, colour, marker) in enumerate(groups):
        ax.scatter(vals, np.full(len(vals), i) + np.random.default_rng(0)
                   .uniform(-0.13, 0.13, len(vals)), s=42, color=colour,
                   marker=marker, label=f"{label}  (n={len(vals)})", zorder=3)
    ax.axvspan(0.98, 2.83, color="#dcfce7", zorder=0)
    ax.axvline(1.3, color="#111827", lw=1.6, zorder=2)
    ax.text(1.33, 2.44, "max_wrist_rate = 1.3", fontsize=8, weight="bold")
    ax.text(1.05, -0.62, "plateau: every count correct for any gate in "
                         "[0.98, 2.83]", fontsize=7.5, color="#166534")
    ax.set_xscale("log")
    ax.set_xlim(0.25, 4.0)
    ax.set_xticks([0.3, 0.5, 1.0, 2.0, 3.0])
    # A log axis keeps its scientific MINOR labels unless they are cleared, so
    # the ticks came out as "4 x 10^-1" interleaved with the plain majors.
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_yticks([])
    ax.set_ylim(-0.8, 2.7)
    ax.set_xlabel("median wrist rotation rate in the second before the spike "
                  "(rad/s)", fontsize=8)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.set_title(
        "B. what separates them is the second BEFORE, not the peak\n"
        "peak height cannot: the counterfeit is 7.01 g, the weakest real "
        "landing 6.69 g", fontsize=9)

    # --- C: the bench single ---------------------------------------------
    ax = axes[1][0]
    d = data["single"]
    ax.plot(d["t"], d["v_cm"], color="#334155", lw=0.9, zorder=2)
    ax.axhline(0, color="#cbd5e1", lw=0.8)
    for pk, colour, label in d["lobes"]:
        ax.axvline(pk, color=colour, lw=2.0, alpha=0.85, zorder=1)
        ax.annotate(label, (pk, -60), fontsize=7.5, color=colour, ha="center",
                    va="top", weight="bold")
    ax.set_ylim(-75, 75)
    ax.set_ylabel("band-passed vertical velocity (cm/s)", fontsize=8)
    ax.set_xlabel("time (s)", fontsize=8)

    tw = ax.twinx()
    tw.plot(d["video_t"], d["video_h_cm"], color="#2563eb", lw=1.8, zorder=3)
    tw.set_ylabel("video bar height (cm)", fontsize=8, color="#2563eb")
    tw.tick_params(labelsize=7, colors="#2563eb")
    tw.annotate("bar in the rack until 16 s", (2.0, 27), fontsize=8,
                color="#2563eb")

    ax.set_title(
        "C. bench_117.5x1: the two candidates correlate 0.80 in shape and\n"
        "carry 0.290 and 0.304 m. Shape, size and cadence all tie.",
        fontsize=9)

    # --- D: the verticality gate -----------------------------------------
    ax = axes[1][1]
    for label, vals, colour, marker in [
            ("real bench and squat reps", data["upright"]["reps"], "#16a34a", "o"),
            ("bench_117.5x1 setup movement", data["upright"]["setup"],
             "#dc2626", "X"),
            ("deadlift single, the real pull", data["upright"]["deadlift"],
             "#a16207", "D")]:
        ax.scatter(vals, np.full(len(vals), 0) + np.random.default_rng(1)
                   .uniform(-0.3, 0.3, len(vals)), s=42, color=colour,
                   marker=marker, label=f"{label}  (n={len(vals)})", zorder=3)
    ax.axvspan(1.02, 3.62, color="#dcfce7", zorder=0)
    ax.axvline(2.0, color="#111827", lw=1.6, zorder=2)
    ax.text(2.1, 0.55, "min_ratio = 2.0", fontsize=8, weight="bold")
    ax.text(1.05, -0.62, "plateau: every count correct for any gate in "
                         "[1.02, 3.62] — 255% wide", fontsize=7.5,
            color="#166534")
    ax.set_xscale("log")
    ax.set_xlim(0.6, 20)
    ax.set_xticks([1, 2, 3, 5, 10, 15])
    # A log axis keeps its scientific MINOR labels unless they are cleared, so
    # the ticks came out as "4 x 10^-1" interleaved with the plain majors.
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_yticks([])
    ax.set_ylim(-0.8, 0.8)
    ax.set_xlabel("vertical travel / fore-aft travel, per candidate window "
                  "(detrended)", fontsize=8)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.set_title(
        "D. a loaded bench or squat rep is CONSTRAINED to vertical;\n"
        "the deadlift single is the thinnest margin in the corpus, 2.59 vs 2.13",
        fontsize=9)

    for row in axes:
        for ax in row:
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.2)

    fig.suptitle(
        "analysis/53 — G1: the segmentation defects the 2026-08-08 captures "
        "exposed, and the rules that fix them\n"
        "Every one was invisible to a rep count and every one was settled by "
        "the cached video track. A third — deadlift_200x1 segmenting the DROP "
        "— is not drawn here; see TASKS.md G1.\n"
        "Counting is now 16/16 captures, 64/64 reps.",
        fontsize=11.5, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def plot_pipeline_vs_tracked(panels: list):
    """G1 — every capture's reconstruction against its cached video track.

    Writes `analysis/54`. One panel per capture, all sixteen, drawn as step 9
    would draw them: reps overlaid, start-aligned, fore-aft stretched 4x.

    **The point of drawing all sixteen rather than a chosen six is the pattern
    in what CANNOT be drawn.** Six of the sixteen have no grey line at all, and
    they are not six arbitrary captures: the four squats, which `vs_truth`
    still refuses, and the two SINGLES, which no sync can reach — `bench_sync`
    needs a rep cadence and a single has none, and the deadlift clock fit needs
    at least two landings to fit an offset and a slope. So two of the three
    captures whose segmentation G1 repaired are singles that cannot be checked
    against the video at all — the segmenter is weakest exactly where the
    referee cannot reach.

    **THAT PARAGRAPH IS NO LONGER TRUE OF THE PIPELINE, and it is left standing
    because it describes what this figure shows.** G2 lifted the squat refusal
    on 2026-08-15 and G3 scored the three singles the same day, so all sixteen
    captures are refereed now and a regenerated `analysis/54` would have sixteen
    grey lines. Its own observation is what got acted on: the referee could not
    reach exactly where the segmenter was weakest, and closing that gap is what
    G2 and G3 were. Regenerate this figure and rewrite the paragraph together,
    or not at all — a caption that no longer matches its picture is worse than
    a stale one that does. See `analysis/56`.

    Captions carry `beats_null`, which is the number that matters: below 1.0
    the reconstruction is beaten by drawing NO fore-aft motion whatsoever.
    """
    cols = 4
    rows = -(-len(panels) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 5.4 * rows),
                             squeeze=False)
    flat = axes.ravel()

    for ax, p in zip(flat, panels):
        vid = p.get("video")
        if vid is not None:
            for i, v in enumerate(vid):
                ax.plot(v[:, 0] * 100, v[:, 1] * 100, color="0.55", lw=2.4,
                        label="video (cached track)" if i == 0 else None,
                        zorder=2)
        for i, q in enumerate(p["paths"]):
            ax.plot(q[:, 0] * 100, q[:, 1] * 100, lw=1.5, alpha=0.9,
                    color="#1d4ed8" if vid is not None else None,
                    label=("reconstruction" if vid is not None else f"rep {i+1}")
                    if i == 0 or vid is None else None, zorder=3)
        ax.set_aspect(1.0 / STRETCH)
        ax.set_title(p["caption"], fontsize=8, color=p.get("colour", "black"))
        ax.set_xlabel("fore-aft (cm)", fontsize=7.5)
        ax.set_ylabel("vertical (cm)", fontsize=7.5)
        ax.tick_params(labelsize=6.5)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=6, frameon=False, loc="best")
    for ax in flat[len(panels):]:
        ax.axis("off")

    fig.suptitle(
        "analysis/54 — G1: all sixteen data_v2 captures against the cached "
        "tracked paths, step 6 ON, segmentation fixed\n"
        "Reps overlaid and start-aligned, fore-aft stretched 4x. Grey is the "
        "video. RED captions cannot be scored at all; ORANGE lose to a flat "
        "line.\n"
        "Rep counting is 16/16 captures and 64/64 reps; the reconstruction is "
        "a different question, and it is the one this figure is about.",
        fontsize=12, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    return fig


def plot_squat_sync(data: dict):
    """G2 — squat is refereed now, and what licensed it.

    Writes `analysis/55`. The refusal that stood here was never really about
    squat being unmeasurable; it was about a tracker and a corpus that no
    longer exist. What actually had to be established was that a squat video
    can be put on the IMU clock, and the four panels are that argument.

    **A** is the reason the refusal could be lifted at all rather than merely
    argued down: the correlation curve. Bench's has rivals a whole rep away —
    that is `bench_sync`'s known, documented ambiguity — and the paused squat's
    does not. The pause breaks the periodicity that makes bench ambiguous, so
    a squat's lag is identified absolutely where a bench's is identified modulo
    one rep.

    **B** is the corroboration, and it is the part bench never had. The bottom
    of each rep is named twice, by instruments that cannot see each other: the
    raw IMU through `segment.dwell_instants`, and the tracked video height.
    Seven captures, agreement 0.003-0.083 of a rep against a 0.25 gate.

    **C** shows one capture's alignment directly, because a scatter plot of
    offsets is still a number and this project's recurring failure is a number
    that looks fine. Every video bottom should sit inside exactly one IMU rep
    window, near its middle.

    **D** is the guard doing its job. A one-rep sync error is injected in both
    directions on every capture with a cadence; all fourteen are refused. The
    separation is what the gate is set inside.
    """
    fig, axes = plt.subplots(2, 2, figsize=(15.0, 9.2))

    # --- A: correlation curves, bench against paused squat ----------------
    ax = axes[0][0]
    for d in data["curves"]:
        ax.plot(np.asarray(d["lags"]) - d["offset"],
                np.asarray(d["curve"]) / d["corr"],
                lw=1.5, color=d["colour"],
                label=f"{d['stem']}  (corr {d['corr']:.2f}, highest sidelobe "
                      f"{d['sidelobe']:.2f})")
        for lag, frac, periods in d["rivals"]:
            ax.plot(lag - d["offset"], frac, "v", color=d["colour"], ms=8,
                    zorder=5)
            ax.annotate(f"{periods:+.2f} rep", (lag - d["offset"], frac),
                        textcoords="offset points", xytext=(0, 8),
                        fontsize=7, color=d["colour"], ha="center")
    ax.axhline(0.70, color="#94a3b8", ls=":", lw=1.0)
    ax.text(-11.5, 0.715, "RIVAL_FRAC — a peak this high is a real rival",
            fontsize=7, color="#64748b")
    ax.set_xlim(-12, 12)
    ax.set_ylim(0, 1.08)
    ax.set_xlabel("lag from the chosen peak (s)", fontsize=8)
    ax.set_ylabel("correlation, as a fraction of the peak", fontsize=8)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax.set_title("A. bench's lag is identified modulo ONE REP; the paused "
                 "squat's is not\nbench sidelobes reach 0.72-0.79 of the peak, "
                 "squat 0.58-0.69 — but 145x4_1's 0.69 is 1% off the line",
                 fontsize=9)

    # --- B: landmark against correlation ----------------------------------
    ax = axes[0][1]
    for row in data["agree"]:
        c = "#7c3aed" if row["lift"] == "squat" else "#0891b2"
        ax.barh(row["stem"], row["disagree"], color=c, height=0.6)
        ax.annotate(f"  {row['disagree']:.3f}", (row["disagree"], row["stem"]),
                    va="center", fontsize=7.5, color=c)
    ax.axvline(data["tol"], color="#111827", lw=1.6)
    ax.axvline(1.0, color="#b91c1c", lw=1.6, ls="--")
    ax.text(data["tol"]*1.05, -0.45, f"gate {data['tol']}", fontsize=8,
            weight="bold")
    ax.text(0.62, -0.45, "a whole-rep error\nlands here", fontsize=7.5,
            color="#b91c1c")
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("disagreement between the correlation and the per-rep "
                  "bottoms (rep periods)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title("B. two instruments that cannot see each other, on the same "
                 "offset\npurple = squat, teal = bench", fontsize=9)

    # --- C: one capture's alignment, drawn -------------------------------
    ax = axes[1][0]
    d = data["aligned"]
    ax.plot(d["t_video"], d["height_cm"], color="#2563eb", lw=1.6,
            label="video bar height, on the IMU clock")
    for i, (a, b) in enumerate(d["windows"]):
        ax.axvspan(a, b, color="#dcfce7", zorder=0,
                   label="IMU rep window" if i == 0 else None)
    for i, x in enumerate(d["bottoms"]):
        ax.axvline(x, color="#dc2626", lw=1.3,
                   label="video bottom" if i == 0 else None)
    for i, x in enumerate(d["dwells"]):
        ax.axvline(x, color="#16a34a", lw=1.3, ls="--",
                   label="IMU dwell (raw signal)" if i == 0 else None)
    ax.set_xlabel("IMU time (s)", fontsize=8)
    ax.set_ylabel("bar height (cm)", fontsize=8)
    ax.legend(fontsize=7, frameon=False, loc="upper right")
    ax.set_title(f"C. {d['stem']}: every video bottom inside exactly one "
                 f"window\nphases {d['phases']}", fontsize=9)

    # --- D: the guard, tested by breaking it ------------------------------
    ax = axes[1][1]
    real = [r["disagree"] for r in data["agree"]]
    ax.scatter(real, np.zeros(len(real)) + 0.08*np.random.default_rng(0)
               .standard_normal(len(real)), s=45, color="#16a34a",
               label=f"as shipped  (n={len(real)})", zorder=3)
    shifted = data["shifted"]
    ax.scatter(shifted, np.zeros(len(shifted)) + 0.08*np.random.default_rng(1)
               .standard_normal(len(shifted)), s=45, color="#dc2626",
               marker="X", label=f"one-rep error injected  (n={len(shifted)}, "
               f"all refused)", zorder=3)
    ax.axvspan(0, data["tol"], color="#dcfce7", zorder=0)
    ax.axvline(data["tol"], color="#111827", lw=1.6)
    ax.text(data["tol"]*1.05, 0.22, f"gate {data['tol']}", fontsize=8,
            weight="bold")
    ax.set_xlim(0, max(shifted + real) * 1.1)
    ax.set_ylim(-0.35, 0.35)
    ax.set_yticks([])
    ax.set_xlabel("disagreement (rep periods)", fontsize=8)
    ax.legend(fontsize=7.5, frameon=False, loc="upper center")
    ax.set_title("D. the guard, tested by breaking it\n14 injected whole-rep "
                 "errors, 14 refused, 0 missed", fontsize=9)

    for row in axes:
        for ax in row:
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.2)

    fig.suptitle(
        "analysis/55 — G2: vs_truth's squat refusal is lifted, and the sync "
        "that replaces it is corroborated\n"
        "The refusal described the v1 plate template on footage F1 deleted. "
        "Squat now scores h 1.88-2.97 cm and all three paused captures beat "
        "the flat-line null.",
        fontsize=11.5, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def plot_short_sets(data: dict):
    """G3 — the singles and doubles the periodic machinery cannot reach.

    Writes `analysis/56`. The three captures `data_v2/` has never refereed are
    the three SINGLES, one per lift, and this is the evidence for the clock that
    reaches them.

    **A is the whole argument in one curve.** `bench_sync` widens its sweep
    until the peak is interior, because on a long set the true lag can sit 7 s
    out. On a single that is fatal: the record is flat apart from one event, so
    sliding the two records far apart correlates flat against flat on ever less
    of it, and the wrong answer wins OUTRIGHT — on `deadlift_200x1` a 17 s error
    scores 0.642 against the true peak's 0.335. The shaded band is where the two
    records still share 80% of the shorter one, which is the only region the
    sweep is allowed to look in. The dashed line is the offset the floor impact
    independently says is right.

    **B is the accuracy, against answers this module did not supply.** Thirteen
    singles and thirteen doubles cut from the multi-rep captures, each scored
    against the offset its own full capture fits. For scale, the multi-rep
    deadlift sync — the best-validated clock here — runs an 8-10 ms residual.

    **C is what it buys.** The three real singles, drawn against the video that
    could not previously be put on their clock at all.

    **D is the owner's proposed rule, measured and NOT shipped.** "Maximum
    displacement between IMU dwells" loses to the segmenter that already exists,
    on every reading tried, for one reason: integration drift produces more
    apparent displacement than a rep does, so the criterion prefers the longest
    admissible window. The bar marked 86.8 cm is a bench press whose true range
    is 27 cm. Recorded rather than deleted — on a drift-free position estimate
    it would very likely work, which is exactly why it looks right on paper.
    """
    fig, axes = plt.subplots(2, 2, figsize=(15.0, 9.4))

    # --- A: why the sweep must be bounded by overlap ------------------------
    ax = axes[0][0]
    c = data["curve"]
    ax.plot(c["lags"], c["curve"], lw=1.3, color="0.35",
            label="correlation vs lag")
    ax.axvspan(c["floor_lo"], c["floor_hi"], color="tab:green", alpha=0.13,
               label=f"admissible: records share {c['frac']:.0%}")
    ax.axvline(c["truth"], color="tab:blue", ls="--", lw=1.8,
               label=f"floor impact says {c['truth']:+.3f} s")
    ax.plot([c["accepted"]], [c["accepted_corr"]], "o", ms=9,
            color="tab:green", label=f"accepted {c['accepted']:+.3f} s "
                                     f"(corr {c['accepted_corr']:.2f})")
    for lag, corr in c["decoys"]:
        ax.plot([lag], [corr], "x", ms=11, mew=2.8, color="tab:red")
        ax.annotate(f"{lag:+.1f} s, corr {corr:.2f}", (lag, corr),
                    textcoords="offset points", xytext=(0, 12),
                    ha="center", fontsize=8.5, color="tab:red", weight="bold")
    ax.set_title(f"A  {c['stem']}: the unbounded sweep prefers a wrong lag,\n"
                 f"and prefers it more confidently", fontsize=10.5)
    ax.set_xlabel("lag (s), video relative to IMU")
    ax.set_ylabel("correlation")
    # Below the curve: the decoys sit high and the legend must not cover them,
    # which it did in the first render — the point of the panel is a red cross
    # ABOVE the accepted green dot.
    ax.legend(fontsize=8, loc="lower left", framealpha=0.95)
    ax.set_ylim(top=max(1.05, float(np.nanmax(c["curve"])) + 0.22))
    ax.grid(alpha=0.3)

    # --- B: accuracy against known offsets ----------------------------------
    ax = axes[0][1]
    for i, (label, errs, colour) in enumerate(data["accuracy"]):
        y = np.full(len(errs), i) + np.random.default_rng(0).uniform(
            -0.13, 0.13, len(errs))
        ax.plot(np.abs(errs) * 1000, y, "o", ms=7, color=colour, alpha=0.85,
                label=f"{label}  (n={len(errs)}, worst "
                      f"{np.abs(errs).max() * 1000:.0f} ms)")
    ax.axvspan(8.4, 9.7, color="tab:blue", alpha=0.15)
    ax.annotate("multi-rep deadlift sync\nresidual, 8.4-9.7 ms", (9.0, -0.55),
                fontsize=8.5, color="tab:blue", ha="center")
    ax.set_xscale("log")
    ax.set_xlim(0.5, 500)
    ax.get_xaxis().set_minor_formatter(plt.NullFormatter())
    ax.set_yticks(range(len(data["accuracy"])))
    ax.set_yticklabels([d[0] for d in data["accuracy"]], fontsize=9)
    ax.set_ylim(-0.8, len(data["accuracy"]) - 0.3)
    ax.set_title("B  offset error against the answer the FULL capture fits\n"
                 "(short sets cut from the thirteen multi-rep captures)",
                 fontsize=10.5)
    ax.set_xlabel("|error| (ms, log)")
    ax.grid(alpha=0.3, axis="x")

    # --- C: the three real singles, now scoreable ---------------------------
    ax = axes[1][0]
    # Each pair drawn in ONE colour — the video thick and faded, the
    # reconstruction thin and solid. A single grey for all three videos was
    # unreadable: with three captures overlaid you cannot tell which grey line
    # belongs to which coloured one, which is the only comparison the panel is
    # for.
    for d in data["singles"]:
        ax.plot(d["video"][:, 0] * 100, d["video"][:, 1] * 100, lw=5.0,
                color=d["colour"], alpha=0.25, solid_capstyle="round")
        ax.plot(d["path"][:, 0] * 100, d["path"][:, 1] * 100, lw=1.7,
                color=d["colour"],
                label=f"{d['stem']}  h {d['h_rms']:.2f} cm, "
                      f"null {d['null']:.2f}")
    ax.plot([], [], lw=5.0, color="0.5", alpha=0.35, label="video (thick, faded)")
    ax.plot([], [], lw=1.7, color="0.3", label="reconstruction (thin, solid)")
    ax.set_title("C  the three captures that had no referee at all,\n"
                 "now on the IMU clock (fore-aft stretched 4x)", fontsize=10.5)
    ax.set_xlabel("fore-aft (cm)")
    ax.set_ylabel("height (cm)")
    ax.legend(fontsize=8, loc="best")
    ax.grid(alpha=0.3)
    ax.set_aspect(0.25)

    # --- D: the rejected rule ------------------------------------------------
    ax = axes[1][1]
    rules = data["rules"]
    y = np.arange(len(rules))
    ax.barh(y, [r["median_iou"] for r in rules],
            color=["tab:green" if r["shipped"] else "tab:red" for r in rules],
            alpha=0.8)
    for i, r in enumerate(rules):
        ax.annotate(f"{r['median_iou']:.2f}   {r['hits']}/{r['n']} above 0.5",
                    (r["median_iou"], i), textcoords="offset points",
                    xytext=(6, -3), fontsize=8.5)
    ax.set_yticks(y)
    ax.set_yticklabels([r["name"] for r in rules], fontsize=8.5)
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("median IoU against the full capture's first rep window")
    ax.set_title("D  the proposed 'max displacement between dwells' rule,\n"
                 "measured on thirteen singles and not shipped", fontsize=10.5)
    ax.grid(alpha=0.3, axis="x")

    fig.suptitle(
        "56 — singles and doubles: the sync, not the segmenter, is what "
        "refused them. All three singles now score; the thirteen multi-rep "
        "captures are bit-identical.", fontsize=11.5, y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig

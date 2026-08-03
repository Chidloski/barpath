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
its fore-aft sign unresolved (B4). So a stretched plot is not a certified plot;
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
        "that has truth. Reps start-aligned, fore-aft stretched 4x as step 9 "
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
    from . import truth as truth_mod

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
    side on the same lift: `truth.py` matching a dark plate template, and
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

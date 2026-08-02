#!/usr/bin/env python3
"""Run the pipeline over captures and print what happened.

    python run.py                      # every capture in data/raw
    python run.py data/raw/foo.csv     # one
    python run.py --plot               # also write diagnostics to analysis/
    python run.py --truth              # also measure against the video (A3)
    python run.py --stages             # draw the pipeline stage by stage
    python run.py --rom                # per-rep vertical ROM against the bounds
    python run.py --anchors            # C6: attitude before and after a set
    python run.py --bias               # B6: constant-bias corrections vs the video
    python run.py --closure            # C11: vertical momentum, bench vs deadlift
    python run.py --splice             # B6: the impact splice, measured and rejected
    python run.py --b3oracle           # B3: what is left in the per-rep detrend
    python run.py --vstruth            # the reconstruction drawn on top of the video
    python run.py --scorecard          # how well the pipeline performs, per lift
    python run.py --paths              # step 9: the bar path itself

--truth is slow: it decodes each clip. It produces numbers on deadlift, and
since C8 on the bench captures whose sync is identified (3 of 7). Squat and the
remaining benches report why instead.

--stages writes analysis/21_pipeline_stages.png: one column per lift, one row
per stage, from raw acceleration to the bar path. It ignores any paths given
on the command line and uses one representative capture per lift, because the
point of it is the comparison.

--rom writes analysis/23_rom_bounds.png: every capture's per-rep vertical range
of motion against what the lifter can actually move a bar through. Also slow —
it decodes the deadlift clips to check the video against the same bounds, which
is where it found that two of the three are mis-scaled.

--paths writes analysis/27_bar_paths.png: steps 8 and 9 applied to every
capture in data/raw, which is the product this project exists to make. Read the
subtitles before reading the shapes — a panel drawn without the 4x stretch has
an axis project.confidence would not vouch for, and a panel drawn WITH it has
an identifiable axis and no accuracy claim whatever. Nothing here is inside
spec; see P2.

--anchors writes analysis/24_c6_two_anchors.png: Core Motion's attitude error at
the still holds bracketing each set, the per-rep residual that the anchors
cannot see, and where the deadlift's share of it enters. Needs the `phase`
column, so it uses the 2026-07-30 captures onward.

--closure writes analysis/31_c11_momentum_closure.png: the vertical impulse
between two moments the video says the bar was still, which must be zero. Bench
closes at the sensor's noise floor and deadlift does not, and the difference is
the floor impact. Slow — it decodes every bench and deadlift clip. Squat is
excluded because its footage does not track.

--splice writes analysis/32_b6_splice_rejected.png: B6's impact splice, measured
and rejected. It removes the vertical momentum deficit completely and still
loses on horizontal, which is the axis the spec is about. The splice lives here
and in the test that pins the result, deliberately not in `correct.py` — it was
rejected, and B7's precedent is to delete rather than leave a flag behind.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src import pipeline  # noqa: E402


STAGE_CAPTURES = [("squat", "squat_130x5"),
                  ("bench", "bench_90x4_1"),
                  ("deadlift", "deadlift_155x6_1")]


def draw_stages() -> int:
    """One representative capture per lift, drawn stage by stage."""
    import matplotlib
    matplotlib.use("Agg")
    from src import plot, truth

    raw = ROOT / "data" / "raw"
    results, truths = {}, {}
    for label, stem in STAGE_CAPTURES:
        path = next(raw.glob(f"{stem}*.csv"), None)
        if path is None:
            print(f"{stem} not in data/raw/ — skipping")
            continue
        video = pipeline.find_video(path, ROOT / "data" / "video")
        # Deadlift and bench have video truth; squat does not. See src/README.md.
        # A bench whose correlation misses the sync floor still raises, and
        # pipeline.run records that in result["blocked"] rather than dying.
        use = video if label in ("deadlift", "bench") else None
        results[f"{label}  ({stem})"] = pipeline.run(path, video=use)

        if use is not None:
            from src import segment
            log = results[f"{label}  ({stem})"]["log"]
            tp = truth.bar_path(use)
            fit = truth.sync(truth.landings(tp),
                             [float(log["t"][k]) for k in segment.impact_anchors(log)])
            truths[f"{label}  ({stem})"] = (truth.to_imu_time(tp, fit), tp["height"])

    if not results:
        print("no captures found for the stage diagram")
        return 1

    out = ROOT / "analysis" / "21_pipeline_stages.png"
    plot.plot_stages(results, truths).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_paths() -> int:
    """Step 9 — the bar path, for every capture that segments.

    The first time this pipeline has rendered its own product: steps 8 and 9
    both raised until 2026-07-30, and every bar path anybody had looked at was
    projected by hand inside plot.plot_stages.

    Deliberately every capture rather than one per lift. The scorecard already
    shows a representative of each; what this is for is seeing how often the
    axis is not vouched for at all, which one capture per lift hides.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from src import plot, truth

    raw = ROOT / "data" / "raw"
    runs = []
    for path in sorted(raw.glob("*.csv")):
        try:
            truth.lift_of(path)
        except ValueError:
            continue                      # stationary diagnostics have no reps
        result = pipeline.run(path)
        if "planar" in result:
            runs.append((path.stem.split("_2026")[0], result))

    if not runs:
        print("no captures with reps to draw")
        return 1

    cols = 5
    rows = -(-len(runs) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(3.4 * cols, 5.6 * rows))
    axes = np.atleast_1d(axes).ravel()

    n_confident = 0
    for ax, (stem, result) in zip(axes, runs):
        n_confident += bool(result["confident"])
        # Say what checked this lift, in the title, every time. A drawn path
        # that nothing external has measured is the thing this project keeps
        # mistaking for a working one — so it goes where the name is, not in a
        # corner a reader can skip.
        note = ("5-15 cm rms vs video, spec 1 cm"
                if stem.startswith("deadlift")
                else "NO external horizontal check")
        plot.plot_paths(result["planar"], confident=result["confident"],
                        title=f"{stem}\n{note}", ax=ax)
        ax.set_title(ax.get_title(), fontsize=8, color="0.15")
        # Outside the axes: aspect is locked, so a narrow panel has no interior
        # room and an overlaid legend hides the path it is labelling.
        ax.legend(fontsize=6, frameon=False, loc="center left",
                  bbox_to_anchor=(1.0, 0.5))
        print(f"{stem:22s} ratio {result['axis_ratio']:6.2f}  excursion "
              f"{result['excursion']*100:6.2f} cm  confident "
              f"{result['confident']}"
              + ("" if result["confident"]
                 else "  <- " + "; ".join(result["confidence_reasons"])))
    for ax in axes[len(runs):]:
        ax.axis("off")

    fig.suptitle(
        f"Step 9, every capture. {n_confident} of {len(runs)} sets have an axis "
        f"project.confidence will vouch for.\n"
        f"Vouching for the AXIS is not vouching for the PATH: horizontal error "
        f"is 5-15x outside spec where anything measures it (P2), and the axis "
        f"SIGN is unresolved (B4), so any panel may be mirrored.", fontsize=11)
    out = ROOT / "analysis" / "27_bar_paths.png"
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=105)
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


def draw_rom() -> int:
    """Per-rep vertical ROM for every capture, against the measured bounds."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import metrics, plot, truth

    raw = ROOT / "data" / "raw"
    recon, video = {}, {}
    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue                      # stationary diagnostics have no reps
        result = pipeline.run(path)
        recon[path.stem] = (lift, result["rep_rom_m"])

        clip = pipeline.find_video(path, ROOT / "data" / "video")
        if clip is None or lift == "squat":
            continue                      # squat video is not truth
        try:
            m = metrics.vs_truth(result, clip)
        except ValueError as e:           # a bench below the sync floor
            print(f"{path.stem}: no video ROM — {e}")
            continue
        video[path.stem] = [r["video_rom_cm"] / 100 for r in m["per_rep"]
                            if r["covered"]]
        flags = m["video_rom_flags"]
        print(f"{path.stem}: video ROM median "
              f"{np.median(video[path.stem])*100:.1f} cm, "
              f"{len(flags)} rep(s) flagged")

    if not recon:
        print("no captures found for the ROM plot")
        return 1

    out = ROOT / "analysis" / "23_rom_bounds.png"
    plot.plot_rom_bounds(recon, video).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_anchors() -> int:
    """C6 — the two-anchor attitude measurement, and what it cannot see."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import calibrate, io, orient, plot, segment, truth

    raw = ROOT / "data" / "raw"
    anchors, residuals, exclusion, momentum = {}, {}, {}, {}
    lifts: dict[str, tuple[list, list]] = {}

    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue
        result = pipeline.run(path)
        log = result["log"]
        world = orient.to_world(log["accel"], log["quat"], log["quat"])
        stem = path.stem.split("_2026")[0]

        try:
            a = calibrate.anchor_tilt(log, world)
        except ValueError:
            pass                              # pre-2026-07-30, no closing hold
        else:
            anchors[stem] = a
            print(f"{stem:22s} tilt {a['open_deg']:.3f} -> {a['close_deg']:.3f} deg "
                  f"over {a['span_s']:.0f} s  (gyro alone would drift "
                  f"{a['gyro_only_deg']:.2f} deg)")

        # The per-rep mean must be zero: a rep starts and ends at rest.
        rep_h = [float(np.linalg.norm(world[a:b].mean(axis=0)[:2]) / io.G)
                 for a, b in result["bounds"]]
        holds = calibrate.hold_windows(log)
        hold_h = [float(np.linalg.norm(world[w, :2].mean(axis=0)) / io.G)
                  for w in holds.values() if w is not None]
        lifts.setdefault(lift, ([], []))
        lifts[lift][0].extend(hold_h)
        lifts[lift][1].extend(rep_h)

        if lift != "deadlift":
            continue
        imp = segment.impact_anchors(log)
        pads, vals = [], []
        for pad_ms in (0, 50, 100, 250, 500):
            pad = int(pad_ms * log["fs"] / 1000)
            keep = np.ones(len(world), bool)
            for k in imp:
                keep[max(0, k - pad):k + pad + 1] = False
            v = [np.linalg.norm(world[a:b][keep[a:b]].mean(axis=0)[:2])
                 for a, b in result["bounds"] if keep[a:b].sum() > 10]
            pads.append(pad_ms)
            vals.append(float(np.median(v)) / io.G)
        exclusion[stem] = (pads, vals)
        momentum[stem] = [float(np.trapezoid(world[a:b, 2], log["t"][a:b]))
                          for a, b in result["bounds"]]

    if not anchors:
        print("no captures with both C3 holds — need 2026-07-30 or later")
        return 1

    for lift, (hold, rep) in lifts.items():
        print(f"{lift:9s} hold residual median "
              f"{np.median(hold) if hold else float('nan'):.4f} g, "
              f"per-rep median {np.median(rep):.4f} g")

    out = ROOT / "analysis" / "24_c6_two_anchors.png"
    plot.plot_anchors(anchors, lifts, exclusion, momentum).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_vs_truth() -> int:
    """Every capture with video: the reconstruction drawn on top of the truth."""
    import matplotlib
    matplotlib.use("Agg")
    from src import metrics, plot, truth

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"
    results = {}
    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue
        video = pipeline.find_video(path, vid)
        if video is None or lift == "squat":
            continue                      # vs_truth refuses squat; see its docstring
        result = pipeline.run(path, video=video)
        m = result.get("vs_truth")
        if m is None:
            print(f"{path.stem:34s} no comparison: "
                  f"{'; '.join(result['blocked']) or 'unknown'}")
            continue
        stem = path.stem.split("_2026")[0]
        results[stem] = m
        print(f"{stem:22s} {m['n_compared']}/{m['n_reps']} reps  "
              f"h {m['pipeline_h_rms']:5.2f} cm  v {m['pipeline_v_rms']:5.2f} cm  "
              f"beats_null {m['beats_null']:.2f}  "
              f"sign disagree {m['reps_disagreeing_on_sign']}/{m['n_compared']}")

    if not results:
        print("no captures with a usable video comparison")
        return 1

    out = ROOT / "analysis" / "33_reconstruction_vs_truth.png"
    plot.plot_vs_truth_paths(results).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def b3_oracle() -> int:
    """B3 — how much is left in the per-rep detrend, and does a quadratic pay?

    **An ORACLE, not a correction.** It fits the detrend against the video it
    is being scored on, which is forbidden in the pipeline (HANDOFF: "never fit
    a pipeline parameter to the video") and is the whole point here: an oracle
    bounds a FAMILY before anyone builds an estimator for it. B6 used the same
    move to cap constant-bias correction at ~30% and save building it.

    What is bounded. Step 7 subtracts one particular line per rep — the
    endpoint-to-endpoint one. Shipping's residual is therefore `err` minus *a*
    line, where `err` is the undetrended reconstruction minus the video. So
    `err` minus the BEST line is a floor no linear detrend can beat, however
    cleverly it picks that line, and `err` minus the best line-plus-quadratic
    is the same floor one order up. Both are computed per rep, per axis, by
    least squares on normalised rep time.

    THE DECISION RULE, FIXED BEFORE ANY NUMBER IS READ
    --------------------------------------------------
    Both thresholds are the project's 1 cm horizontal spec. Neither is tuned,
    and that is deliberate — HANDOFF's standing worry is that every constant
    here was chosen on the same 17 captures it is evaluated on.

    1. **Headroom.** oracle-linear must beat shipping's `pipeline_h_rms` by
       >= 1 cm, median over the scoreable captures. If it does not, today's
       endpoint line is already at the linear family's floor: B3's "own 2-4 cm"
       does not exist, and the lambda=0.99 shrinkage lead in TASKS.md was a fit
       to the validation set rather than a finding.

    2. **The extra order pays.** oracle-quadratic must beat oracle-linear by
       >= 1 cm on the same median. If it does not, a quadratic degree of
       freedom cannot help the horizontal whatever pins it, and B3's remaining
       value is confined to (3).

    3. **The B6 unlock, which is why B3 was promoted and is measured on the
       VERTICAL.** Independent of 1 and 2: with a quadratic detrend in place,
       B6's splice must keep per-rep vertical ROM inside
       `truth.VERTICAL_ROM_M["deadlift"]` -- it is 82.6 cm today against a
       61 cm ceiling -- without regressing horizontal past shipping.

    **(3) can hold while (1) and (2) both fail, and if so that is the result:**
    B3 is then not a horizontal fix at all, only an enabler for B6, and must be
    reported as one. Writing that down in advance is the point; B6's own rule
    was partly mis-specified because it read horizontal columns to judge a
    vertical correction, and this is the same trap one step later.

    Caution carried from A3: `vs_truth`'s horizontal rms is insensitive to
    gross time misalignment, so none of this is evidence the reps line up in
    time. It is a magnitude comparison between families.
    """
    import numpy as np
    from src import metrics, truth

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"

    def oracle(err: np.ndarray, order: int) -> float:
        """rms of `err` after removing the best polynomial of `order` in rep time."""
        tau = np.linspace(0.0, 1.0, len(err))
        X = np.vander(tau, order + 1)
        resid = err - X @ np.linalg.lstsq(X, err, rcond=None)[0]
        return float(np.sqrt((resid ** 2).mean()) * 100)

    rows = []
    for path in sorted(raw.glob("*.csv")):
        clip = pipeline.find_video(path, vid)
        if clip is None:
            continue
        try:
            result = pipeline.run(path)
            out = metrics.vs_truth(result, clip)
        except Exception as exc:                      # squat, unsynced bench
            print(f"{path.stem.split('_2026')[0]:22s} refused — {exc}")
            continue

        per = [r for r in out["per_rep"] if r["covered"]]
        if not per:
            continue

        # Per rep: the undetrended reconstruction's error against the video,
        # on the horizontal (column 0) and the vertical (column 1).
        h_ship = float(np.median([r["pipeline_h_rms"] for r in per]))
        v_ship = float(np.median([r["pipeline_v_rms"] for r in per]))
        h_lin = float(np.median([oracle(r["curve_raw"][:, 0] - r["curve_video"][:, 0], 1)
                                 for r in per]))
        h_quad = float(np.median([oracle(r["curve_raw"][:, 0] - r["curve_video"][:, 0], 2)
                                  for r in per]))
        v_lin = float(np.median([oracle(r["curve_raw"][:, 1] - r["curve_video"][:, 1], 1)
                                 for r in per]))
        v_quad = float(np.median([oracle(r["curve_raw"][:, 1] - r["curve_video"][:, 1], 2)
                                  for r in per]))
        null = float(np.median([r["null_h_rms"] for r in per]))

        rows.append({"capture": path.stem.split("_2026")[0], "null": null,
                     "h_ship": h_ship, "h_lin": h_lin, "h_quad": h_quad,
                     "v_ship": v_ship, "v_lin": v_lin, "v_quad": v_quad})
        print(f"{rows[-1]['capture']:22s} h {h_ship:6.2f} -> lin {h_lin:6.2f} "
              f"-> quad {h_quad:6.2f}   (null {null:5.2f})   "
              f"v {v_ship:6.2f} -> lin {v_lin:6.2f} -> quad {v_quad:6.2f}")

    if not rows:
        print("no capture with video to bound the detrend on")
        return 1

    def med(k):
        return float(np.median([r[k] for r in rows]))

    gain_1 = med("h_ship") - med("h_lin")
    gain_2 = med("h_lin") - med("h_quad")
    print(f"\nmedian over {len(rows)} captures, horizontal cm:")
    print(f"  shipping {med('h_ship'):.2f}   oracle-linear {med('h_lin'):.2f}"
          f"   oracle-quadratic {med('h_quad'):.2f}   null {med('null'):.2f}")
    print(f"  rule 1, headroom      : {gain_1:+.2f} cm  "
          f"{'PASS' if gain_1 >= 1.0 else 'FAIL'} (needs >= 1.00)")
    print(f"  rule 2, quadratic pays: {gain_2:+.2f} cm  "
          f"{'PASS' if gain_2 >= 1.0 else 'FAIL'} (needs >= 1.00)")
    print(f"\nmedian vertical cm: shipping {med('v_ship'):.2f}   "
          f"oracle-linear {med('v_lin'):.2f}   oracle-quadratic {med('v_quad'):.2f}")
    print(f"  (deadlift ROM ceiling {truth.VERTICAL_ROM_M['deadlift'][1] * 100:.0f} cm; "
          "rule 3 is measured by --splice, not here)")
    return 0


DL_SPLICE = [("deadlift_155x6_1_20260728_122828", "deadlift_155x6_1_20260728"),
             ("deadlift_155x6_2_20260728_123603", "deadlift_155x6_2_20260728"),
             ("deadlift_180x3_20260728_121739", "deadlift_180x3_20260728")]


def draw_splice() -> int:
    """B6 — the impact splice: it fixes the closure and loses anyway.

    Regenerates analysis/32. The splice is implemented here and in the test
    that pins the result, deliberately not in `correct.py` — it was measured
    and rejected, and B7's precedent is to delete rather than leave a flag.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from scipy.integrate import cumulative_trapezoid
    from scipy.signal import savgol_filter
    from src import correct, metrics, plot, segment, truth

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"

    # One decode per clip; vs_truth is called four times per capture.
    cache, original = {}, truth.bar_path

    def cached(v, *a, **k):
        cache.setdefault(str(v), original(v, *a, **k))
        return cache[str(v)]

    truth.bar_path = metrics.truth.bar_path = cached

    def splice(velocity, t, rest, impacts, axes):
        v = velocity.copy()
        keep = np.zeros(v.shape[1])
        keep[list(axes)] = 1.0
        for r in rest:
            k = max([i for i in impacts if i < r], default=None)
            if k is None:
                continue
            e = v[r] * keep
            w = np.zeros(len(v))
            w[k:r + 1] = (t[k:r + 1] - t[k]) / (t[r] - t[k])
            w[r + 1:] = 1.0
            v = v - w[:, None] * e
        return v

    def closure(result, velocity, video):
        t_imu, _, height, _ = metrics._video_on_imu_clock(result, video)
        v_vid = np.gradient(savgol_filter(height, 9, 3), t_imu)
        log, t = result["log"], result["log"]["t"]
        first, last = t[result["bounds"][0][0]], t[result["bounds"][-1][1] - 1]
        mids = metrics._video_zero_dwells(t_imu, v_vid, 0.10, 0.20)
        mids = mids[(mids >= first - 0.5) & (mids <= last + 0.5)]
        idx = [int(np.searchsorted(t, m)) for m in mids]
        impacts = segment.impact_anchors(log)
        return [velocity[b, 2] - velocity[a, 2]
                for a, b in zip(idx, idx[1:])
                if any(a <= k < b for k in impacts)]

    variants = [("shipping", None, (0, 1, 2)),
                ("splice z", (2,), (0, 1, 2)),
                ("splice xyz", (0, 1, 2), (0, 1, 2)),
                ("splice xyz\n+ z-only detrend", (0, 1, 2), (2,))]

    closures, h_rms, rom_trace = {}, {}, None
    for csv, video in DL_SPLICE:
        path, clip = raw / f"{csv}.csv", vid / f"{video}.mov"
        if not (path.exists() and clip.exists()):
            print(f"{csv} or {video} not present — skipping")
            continue
        result = pipeline.run(path)
        log, t = result["log"], result["log"]["t"]
        impacts = segment.impact_anchors(log)
        lo, hi = result["bounds"][0][0], result["bounds"][-1][1] - 1
        rest = [k for k in segment.rest_instants(log, impacts) if lo <= k <= hi]
        stem = csv.split("_2026")[0]

        closures[stem] = (closure(result, result["velocity"], clip),
                          closure(result, splice(result["velocity"], t, rest,
                                                 impacts, (2,)), clip))
        row = {}
        for label, axes, det in variants:
            v = (result["velocity"] if axes is None
                 else splice(result["velocity"], t, rest, impacts, axes))
            pos = cumulative_trapezoid(v, np.cumsum(log["dt"]), axis=0, initial=0)
            reps = correct.detrend_set(pos, result["bounds"], t, axes=det)
            row[label] = metrics.vs_truth(
                {**result, "reps": reps, "velocity": v}, clip)["pipeline_h_rms"]
        h_rms[stem] = row
        print(f"{stem:22s} closure {np.median(closures[stem][0]):+.3f} -> "
              f"{np.median(closures[stem][1]):+.3f} m/s   "
              + "  ".join(f"{k.splitlines()[0]} {v:.2f}" for k, v in row.items()))

        if rom_trace is None:
            v = splice(result["velocity"], t, rest, impacts, (2,))
            pos = cumulative_trapezoid(v, np.cumsum(log["dt"]), axis=0, initial=0)
            sp = correct.detrend_set(pos, result["bounds"], t)
            rom_trace = (stem, [p[:, 2] * 100 for p in result["reps"]],
                         [p[:, 2] * 100 for p in sp])

    if not closures:
        print("no deadlift capture with video to measure the splice on")
        return 1

    out = ROOT / "analysis" / "32_b6_splice_rejected.png"
    plot.plot_splice_rejected(closures, h_rms, rom_trace,
                              truth.VERTICAL_ROM_M["deadlift"][1] * 100
                              ).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_closure() -> int:
    """C11 — vertical momentum closure, bench against deadlift."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import metrics, orient, plot, segment, truth

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"
    groups: dict[str, list] = {"bench, lifting": [],
                               "deadlift, pull only": [],
                               "deadlift, impact inside": []}
    traces: dict[str, tuple] = {}

    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue
        if lift == "squat":
            continue                      # vs_truth refuses squat; so does this
        video = pipeline.find_video(path, vid)
        if video is None:
            continue

        result = pipeline.run(path, video=video)
        try:
            m = metrics.momentum_closure(result, video)
        except ValueError as exc:
            print(f"{path.stem:34s} SKIPPED  {exc}")
            continue

        log = result["log"]
        world = orient.to_world(log["accel"], log["quat"], log["quat"])
        impacts = segment.impact_anchors(log)

        for iv in m["intervals"]:
            key = ("bench, lifting" if lift == "bench" else
                   "deadlift, impact inside" if iv["spans_impact"] else
                   "deadlift, pull only")
            groups[key].append((iv["duration_s"], iv["dv"]))

        # One representative trace per kind: the interval nearest its own
        # group median, so the panel shows the typical case and not the worst.
        for iv in m["intervals"]:
            key = ("bench, lifting" if lift == "bench" else
                   "deadlift, impact inside" if iv["spans_impact"] else
                   "deadlift, pull only")
            same = [d for _, d in groups[key]]
            if key in traces or abs(iv["dv"] - np.median(same)) > 0.15:
                continue
            a = int(np.searchsorted(log["t"], iv["t_start"]))
            b = int(np.searchsorted(log["t"], iv["t_start"] + iv["duration_s"]))
            cum = np.concatenate(
                [[0.0], np.cumsum(world[a:b - 1, 2] * np.diff(log["t"][a:b]))])
            t_imp = next((float(log["t"][k] - log["t"][a])
                          for k in impacts if a <= k < b), None)
            traces[key] = (log["t"][a:b] - log["t"][a], cum, t_imp)

        print(f"{path.stem:34s} {m['n_intervals']:2d} intervals, "
              f"median {m['median_dv']:+.3f} m/s, max |dv| {m['max_abs_dv']:.3f}")

    if not any(groups.values()):
        print("no captures with video to measure closure on")
        return 1

    for label, rows in groups.items():
        dv = np.array([d for _, d in rows])
        if not len(dv):
            continue
        print(f"{label:26s} n={len(dv):3d}  median {np.median(dv):+.3f}  "
              f"max |dv| {np.abs(dv).max():.3f} m/s")

    out = ROOT / "analysis" / "31_c11_momentum_closure.png"
    plot.plot_momentum_closure(groups, traces).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


B6_VARIANTS = ["shipping", "zero-mean accel\nper rep",
               "zero-mean, no\nposition detrend", "bias from rest-to-rest\nclosure"]


def draw_bias_models() -> int:
    """B6 — measure each constant-bias correction against the video."""
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import correct, integrate, io, metrics, plot, segment

    raw = ROOT / "data" / "raw"
    variants: dict[str, list] = {k: [] for k in B6_VARIANTS}
    closure, traces = {}, {}

    for path in sorted(raw.glob("deadlift*.csv")):
        video = pipeline.find_video(path, ROOT / "data" / "video")
        if video is None:
            continue
        base = pipeline.run(path, video=video)
        log, t, world = base["log"], base["log"]["t"], base["world_accel"]
        stem = path.stem.split("_2026")[0]

        rest = segment.rest_instants(log)
        segs = [world[a:b].mean(axis=0) for a, b in zip(rest, rest[1:])]
        bias = np.mean(segs, axis=0) if segs else np.zeros(3)

        def build(offset, per_rep_mean, axes):
            reps = []
            for a, b in base["bounds"]:
                acc = world[a:b] - offset
                if per_rep_mean:
                    acc = acc - acc.mean(axis=0)
                _, p = integrate.integrate(acc, log["dt"][a:b])
                if axes:
                    p = correct.detrend_rep(p, 0, len(p), t[a:b], axes=axes)
                reps.append(p)
            return metrics.vs_truth({**base, "reps": reps}, video)

        variants[B6_VARIANTS[0]].append(base["vs_truth"]["pipeline_h_rms"])
        variants[B6_VARIANTS[1]].append(build(0.0, True, (0, 1, 2))["pipeline_h_rms"])
        variants[B6_VARIANTS[2]].append(build(0.0, True, ())["pipeline_h_rms"])
        variants[B6_VARIANTS[3]].append(build(bias, False, (0, 1, 2))["pipeline_h_rms"])

        # The bias the MEASURED error implies, against the one closure estimates.
        T = float(np.median([t[min(b, len(t) - 1)] - t[a] for a, b in base["bounds"]]))
        measured_cm = base["vs_truth"]["pipeline_v_rms"]
        implied = measured_cm / 100 * 8 / T ** 2 / io.G
        closure[stem] = (implied, float(abs(bias[2])) / io.G)

        if len(rest) >= 2:
            a, b = int(rest[0]), int(rest[1])
            imp = [k for k in segment.impact_anchors(log) if a <= k < b]
            traces[stem] = (t[a:b] - t[a],
                            np.concatenate([[0.0], np.cumsum(
                                world[a:b - 1, 2] * log["dt"][a:b - 1])]),
                            float(t[imp[0]] - t[a]) if imp else 0.0)

    if not closure:
        print("no deadlift captures with video for the B6 comparison")
        return 1

    for k, v in variants.items():
        print(f"{k.replace(chr(10), ' '):34s} " + " / ".join(f"{x:6.2f}" for x in v))
    for stem, (implied, estimated) in closure.items():
        print(f"{stem:22s} measured error implies {implied:.4f} g; "
              f"closure estimates {estimated:.4f} g ({estimated/implied:.1f}x)")

    out = ROOT / "analysis" / "25_b6_bias_models.png"
    plot.plot_bias_models(variants, closure, traces).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_scorecard() -> int:
    """How well the pipeline currently performs, per lift, on what evidence."""
    import matplotlib
    matplotlib.use("Agg")
    from src import metrics, plot, truth

    raw = ROOT / "data" / "raw"
    results, truths, roms = {}, {}, {}

    # Every rep of every capture feeds the ROM row; the other two rows use one
    # representative capture per lift, the same ones the stage diagram uses.
    for path in sorted(raw.glob("*.csv")):
        try:
            lift = truth.lift_of(path)
        except ValueError:
            continue
        roms.setdefault(lift, []).extend(pipeline.run(path)["rep_rom_m"])

    for lift, stem in STAGE_CAPTURES:
        path = next(raw.glob(f"{stem}*.csv"), None)
        if path is None:
            print(f"{stem} not in data/raw/ — skipping")
            continue
        video = pipeline.find_video(path, ROOT / "data" / "video")
        label = f"{lift}  ({stem})"
        result = pipeline.run(path)
        results[label] = result
        if video is not None and lift != "squat":
            try:
                truths[label] = metrics.vs_truth(result, video)
            except ValueError as e:       # a bench below the sync floor
                print(f"{stem}: no video truth — {e}")
                continue
            m = truths[label]
            # beats_null is printed alongside, never behind a flag: below 1.0
            # the reconstruction is worse than drawing no fore-aft motion at
            # all, which is true of six of the ten captures with video and of
            # every deadlift. See metrics.vs_truth.
            verdict = "beats" if m["beats_null"] >= 1.0 else "LOSES TO"
            print(f"{stem}: horizontal {m['pipeline_h_rms']:.2f} cm rms, "
                  f"vertical {m['pipeline_v_rms']:.2f} cm rms, "
                  f"{verdict} the flat line ({m['beats_null']:.2f}x), "
                  f"{len(m['video_rom_flags'])} truth rep(s) flagged")

    if not results:
        print("no captures found for the scorecard")
        return 1

    out = ROOT / "analysis" / "26_pipeline_scorecard.png"
    plot.plot_scorecard(results, truths, roms).savefig(out, dpi=105)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_plot = "--plot" in argv
    want_truth = "--truth" in argv

    if "--stages" in argv:
        return draw_stages()
    if "--paths" in argv:
        return draw_paths()
    if "--rom" in argv:
        return draw_rom()
    if "--anchors" in argv:
        return draw_anchors()
    if "--bias" in argv:
        return draw_bias_models()
    if "--closure" in argv:
        return draw_closure()
    if "--splice" in argv:
        return draw_splice()
    if "--b3oracle" in argv:
        return b3_oracle()
    if "--vstruth" in argv:
        return draw_vs_truth()
    if "--scorecard" in argv:
        return draw_scorecard()

    paths = [Path(a) for a in args] or sorted((ROOT / "data" / "raw").glob("*.csv"))
    if not paths:
        print("no captures found in data/raw/")
        return 1

    blocked: set[str] = set()
    for path in paths:
        video = pipeline.find_video(path, ROOT / "data" / "video") if want_truth else None
        result = pipeline.run(path, video=video)
        print(pipeline.summary(result))
        print()
        blocked.update(result["blocked"])

        if want_plot:
            import matplotlib
            matplotlib.use("Agg")
            from src import plot
            out = ROOT / "analysis" / f"run_{path.stem}.png"
            fig = plot.plot_diagnostics(result["log"], result["position"],
                                        bounds=result["bounds"])
            fig.savefig(out, dpi=110)
            print(f"  wrote {out.relative_to(ROOT)}\n")

    if blocked:
        print("=" * 72)
        print("The pipeline does not complete. Blocked stages, deduplicated:")
        for b in sorted(blocked):
            print(f"  - {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

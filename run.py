#!/usr/bin/env python3
"""Run the pipeline over captures and print what happened.

    python run.py                      # every capture in data/raw
    python run.py data/raw/foo.csv     # one
    python run.py --plot               # also write diagnostics to analysis/
    python run.py --truth              # also measure against the video (A3)
    python run.py --stages             # draw the pipeline stage by stage
    python run.py --rom                # per-rep vertical ROM against the bounds
    python run.py --v2rom              # C24: per-rep ROM on the paired benches
    python run.py --dlconic            # C27: 8-sticker deadlifts, conic vs pipeline
    python run.py --anchors            # C6: attitude before and after a set
    python run.py --bias               # B6: constant-bias corrections vs the video
    python run.py --closure            # C11: vertical momentum, bench vs deadlift
    python run.py --splice             # B6: the impact splice, measured and rejected
    python run.py --b3oracle           # B3: what is left in the per-rep detrend
    python run.py --vstruth            # the reconstruction drawn on top of the video
    python run.py --scorecard          # how well the pipeline performs, per lift
    python run.py --paths              # step 9: the bar path itself
    python run.py --overview           # stages, bar path and video, in one

--truth is slow: it decodes each clip. It produces numbers on deadlift, and
since C8 on the bench captures whose sync is identified (3 of 7). Squat and the
remaining benches report why instead.

--overview writes analysis/40_overview.png: one capture per column, the
pipeline stages down to the bar path, and underneath it the bar path drawn on
the video's. Three captures — a deadlift and a bench refereed by truth.py's
plate template, and a data_v2 bench refereed by markers.py — so the two
referees sit side by side on the same lift. Slow: it decodes three clips.

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

--v2rom writes analysis/41_paired_bench_video_rom.png: per-rep vertical ROM on
the four data_v2 benches, measured three ways — the reconstruction, the video
inside the IMU's rep window, and the video's OWN trough-to-shoulder range found
with no IMU and no sync. The third referees the other two, and it says the
reconstruction reads 15-20% high on every rep. It also showed two of the four
synced a full rep out, which C25 traced to `bench_sync`'s search window being
too narrow to contain its own peak and fixed; every window now holds one chest
touch, so a red window here means the sync has gone out again. Slow: it decodes
and marker-tracks four clips.

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

--b3oracle writes analysis/38_b3_detrend_oracle.png: B3, and what bounds it. An
ORACLE over the per-rep detrend basis — the best line and the best
line-plus-quadratic fitted AGAINST the video, so it caps every estimator rather
than being one. It found ~1.7 cm of real headroom in the linear family and that
the headroom is bench's, not deadlift's, and it rejected the buildable quadratic
on three rules fixed before it ran. Slow: it decodes every bench and deadlift
clip and runs the splice on the three deadlifts.
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


OVERVIEW_CAPTURES = [
    ("deadlift 155x6\ndata/raw · truth.py", "data/raw", "deadlift_155x6_1"),
    ("bench 90x4\ndata/raw · truth.py", "data/raw", "bench_90x4_2"),
    ("bench 95x2\ndata_v2 · markers.py", "data_v2/raw", "bench_95x2"),
]


def draw_overview() -> int:
    """Stages, bar path and video truth for three captures, in one figure."""
    import matplotlib
    matplotlib.use("Agg")
    import warnings
    from src import plot

    results = {}
    for label, folder, stem in OVERVIEW_CAPTURES:
        path = next((ROOT / folder).glob(f"{stem}*.csv"), None)
        if path is None:
            print(f"{stem} not in {folder}/ — skipping")
            continue
        video = pipeline.find_video(path)
        if video is None:
            print(f"{stem} has no video — skipping")
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results[label] = pipeline.run(path, video=video)

    if not results:
        print("no captures found for the overview")
        return 1

    out = ROOT / "analysis" / "40_overview.png"
    plot.plot_overview(results).savefig(out, dpi=105)
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


def draw_dl_conic() -> int:
    """C27 — the three 8-sticker deadlifts: conic referee against the pipeline.

    Writes `analysis/42_conic_deadlift.png`. Everything here is measured with
    `layout="auto"`, i.e. the path a caller gets by default, because C27's
    whole point is that `auto` was silently taking the wrong one.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import markers, metrics, plot

    raw = ROOT / "data_v2" / "raw"
    data: dict = {}
    for path in sorted(raw.glob("deadlift_*.csv")):
        stem = path.stem.split("_20260")[0]
        result = pipeline.run(path)
        clip = pipeline.find_video(path)
        if clip is None:
            print(f"{stem}: no marker clip paired — skipped")
            continue
        bp = markers.bar_path(clip, layout="auto", check=False)
        try:
            m = metrics.vs_truth(result, clip)
        except ValueError as exc:
            print(f"{stem}: vs_truth refused — {exc}")
            continue
        t_vid, _, height, _ = metrics._video_on_imu_clock(result, clip, None)

        h = np.asarray(bp["height"])
        nm = np.asarray(bp["n_markers"], dtype=float)
        ok = np.isfinite(h) & (nm > 0)
        lo, hi = np.nanmin(h[ok]), np.nanmax(h[ok])
        frac = (h[ok] - lo) / (hi - lo)
        dec = np.clip((frac * 10).astype(int), 0, 9)
        decile = [float(np.median(nm[ok][dec == d])) if (dec == d).any() else np.nan
                  for d in range(10)]

        data[stem] = {
            "t_vid": t_vid, "height": height,
            "bounds": result["bounds"], "t": result["log"]["t"],
            "per_rep": m["per_rep"],
            "h_rms": m["pipeline_h_rms"], "null_h_rms": m["null_h_rms"],
            "beats_null": m["beats_null"],
            "imu_rom_cm": [float((r[:, 2].max() - r[:, 2].min()) * 100)
                           for r in result["reps"]],
            "n_rim": int(bp["n_rim"]),
            "coverage": float(np.isfinite(h).mean()),
            "resid_px": float(np.nanmedian(bp["residual_px"])),
            "decile_markers": decile,
        }
        print(f"{stem}: n_rim {bp['n_rim']}, coverage {np.isfinite(h).mean()*100:.1f}%, "
              f"h_rms {m['pipeline_h_rms']:.2f} cm, beats_null {m['beats_null']:.2f}")

    if not data:
        print("nothing to draw")
        return 1
    fig = plot.plot_v2_deadlift_conic(data)
    out = ROOT / "analysis" / "42_conic_deadlift.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")
    return 0


def draw_v2_video_rom() -> int:
    """C24 — per-rep vertical ROM on the four paired benches, three ways.

    The third way is the one that matters: the video's own trough-to-shoulder
    range, found by peak detection on the height trace with no IMU input and no
    sync, so it can referee both of the others.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from scipy.signal import find_peaks
    from src import metrics, plot

    raw = ROOT / "data_v2" / "raw"
    data: dict = {}
    for path in sorted(raw.glob("*.csv")):
        stem = path.stem.split("_20260")[0]
        result = pipeline.run(path)
        clip = pipeline.find_video(path)
        if clip is None:
            print(f"{stem}: no marker clip paired — skipped")
            continue
        t_vid, _, height, _ = metrics._video_on_imu_clock(result, clip, None)
        try:
            m = metrics.vs_truth(result, clip)
        except ValueError as exc:
            print(f"{stem}: vs_truth refused — {exc}")
            continue

        h = np.asarray(height) * 100
        fs = 1.0 / float(np.median(np.diff(t_vid)))
        # The video's own reps. `prominence` in cm rejects the wobble at the
        # rack; `distance` is a second, well under a bench cadence. Neither is
        # tuned against the IMU — that is the whole point of this measurement.
        touches, _ = find_peaks(-h, prominence=15.0, distance=int(1.0 * fs))
        own = []
        for i, k in enumerate(touches):
            lo = touches[i - 1] if i else 0
            hi = touches[i + 1] if i + 1 < len(touches) else len(h) - 1
            own.append(float(min(h[lo:k + 1].max(), h[k:hi + 1].max()) - h[k]))

        imu = [100.0 * v for v in result["rep_rom_m"]]
        win = [r["video_rom_cm"] for r in m["per_rep"] if r["covered"]]
        data[stem] = {"t_vid": t_vid, "height": height, "t": result["log"]["t"],
                      "bounds": result["bounds"], "imu_rom_cm": imu,
                      "window_rom_cm": win, "own_rom_cm": own,
                      "touches": list(touches),
                      "whole_clip_cm": float(h.max() - h.min())}

        t = result["log"]["t"]
        missed = [k for k, (a, b) in enumerate(result["bounds"])
                  if not any(t[a] <= t_vid[i] <= t[b - 1] for i in touches)]
        print(f"{stem:16s} IMU {np.mean(imu):5.1f}  window {np.mean(win):5.1f}  "
              f"own {np.mean(own):5.1f} cm  ({len(touches)} touches, "
              f"{len(result['bounds'])} windows"
              + (f", NO TOUCH in window {missed}" if missed else "") + ")")

    if not data:
        print("no paired captures found in data_v2/raw")
        return 1

    allown = [v for c in data.values() for v in c["own_rom_cm"]]
    allimu = [v for c in data.values() for v in c["imu_rom_cm"]]
    print(f"\nover {len(allown)} reps: video's own extents "
          f"{min(allown):.1f}-{max(allown):.1f} cm, reconstruction "
          f"{min(allimu):.1f}-{max(allimu):.1f} cm "
          f"({100 * (np.mean(allimu) / np.mean(allown) - 1):+.1f}%)")

    out = ROOT / "analysis" / "41_paired_bench_video_rom.png"
    plot.plot_v2_video_rom(data).savefig(out, dpi=105)
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
    from src import correct, metrics, truth

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"

    # One decode per clip: vs_truth is called twice per capture below.
    cache, original = {}, truth.bar_path

    def cached(v, *a, **k):
        cache.setdefault(str(v), original(v, *a, **k))
        return cache[str(v)]

    truth.bar_path = metrics.truth.bar_path = cached

    def oracle(err: np.ndarray, order: int) -> float:
        """rms of `err` after removing the best polynomial of `order` in rep time."""
        tau = np.linspace(0.0, 1.0, len(err))
        X = np.vander(tau, order + 1)
        resid = err - X @ np.linalg.lstsq(X, err, rcond=None)[0]
        return float(np.sqrt((resid ** 2).mean()) * 100)

    rows, traces = [], [None]
    for path in sorted(raw.glob("*.csv")):
        stem = path.stem.split("_2026")[0]
        clip = pipeline.find_video(path, vid)
        if clip is None:
            # Say so. A silent `continue` here scored this oracle on 7 captures
            # instead of 10 the first time it ran, because a git WORKTREE gets
            # only the tracked half of data/video — 10 clips of the 17 in the
            # shared checkout, the 2026-07-30 session's among the missing. The
            # numbers looked entirely reasonable. That is this project's
            # recurring shape once more: a check that passes by not looking.
            print(f"{stem:22s} no video paired — skipped")
            continue
        try:
            result = pipeline.run(path)
            out = metrics.vs_truth(result, clip)
        except Exception as exc:                      # squat, unsynced bench
            print(f"{stem:22s} refused — {str(exc).splitlines()[0][:90]}")
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

        # The BUILDABLE thing, not an oracle: order=2 pinned by the rep's own
        # velocity closure. Nothing here reads the video.
        reps2 = correct.detrend_set(result["bar_position"], result["bounds"],
                                    result["log"]["t"],
                                    velocity=result["velocity"], order=2)
        out2 = metrics.vs_truth({**result, "reps": reps2}, clip)
        per2 = [r for r in out2["per_rep"] if r["covered"]]
        h_est = float(np.median([r["pipeline_h_rms"] for r in per2]))
        v_est = float(np.median([r["pipeline_v_rms"] for r in per2]))
        rom = float(np.median([abs(p[:, 2].max() - p[:, 2].min()) for p in reps2]) * 100)
        rom_ship = float(np.median([abs(p[:, 2].max() - p[:, 2].min())
                                    for p in result["reps"]]) * 100)
        if stem.startswith("deadlift") and traces[0] is None:
            traces[0] = (stem, [p[:, 2] * 100 for p in result["reps"]],
                         [p[:, 2] * 100 for p in reps2])

        rows.append({"capture": stem, "null": null, "rom": rom,
                     "rom_ship": rom_ship,
                     "h_ship": h_ship, "h_lin": h_lin, "h_quad": h_quad,
                     "h_est": h_est, "v_est": v_est,
                     "v_ship": v_ship, "v_lin": v_lin, "v_quad": v_quad})
        print(f"{stem:22s} h {h_ship:6.2f} -> lin {h_lin:6.2f} "
              f"-> quad {h_quad:6.2f}   (null {null:5.2f})   "
              f"v {v_ship:6.2f} -> lin {v_lin:6.2f} -> quad {v_quad:6.2f}"
              f"   || order=2 h {h_est:7.2f} v {v_est:6.2f} rom {rom:6.1f}")

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
    print(f"\n  the BUILDABLE order=2 (velocity closure, no video): "
          f"h {med('h_est'):.2f} cm  v {med('v_est'):.2f} cm")
    print(f"\nmedian vertical cm: shipping {med('v_ship'):.2f}   "
          f"oracle-linear {med('v_lin'):.2f}   oracle-quadratic {med('v_quad'):.2f}")

    # Rule 3 — the B6 unlock, and the reason B3 was promoted at all.
    ceil = truth.VERTICAL_ROM_M["deadlift"][1] * 100
    print(f"\nrule 3, the B6 unlock (deadlift ROM ceiling {ceil:.0f} cm):")
    rule3 = _b3_rule_three(ceil)
    ok = all(r["rom"] <= ceil for r in rule3 if r["variant"] == "splice, order=2")
    print(f"  rule 3, splice stays in ROM: {'PASS' if ok else 'FAIL'}")

    if traces[0] is not None:
        import matplotlib
        matplotlib.use("Agg")
        from src import plot
        out = ROOT / "analysis" / "38_b3_detrend_oracle.png"
        plot.plot_b3_oracle(rows, traces[0], ceil).savefig(out, dpi=105)
        print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


def _b3_rule_three(ceil: float) -> list[dict]:
    """B6's splice under an order=2 detrend. Rule 3 of `b3_oracle`.

    The splice is re-implemented here rather than imported from `draw_splice`
    for the reason that function gives: it was measured and rejected, so it
    lives in `run.py` and in the test that pins it, not in `correct.py`.
    """
    import numpy as np
    from scipy.integrate import cumulative_trapezoid
    from src import correct, metrics, segment

    def splice(velocity, t, rest, impacts):
        v = velocity.copy()
        for r in rest:
            k = max([i for i in impacts if i < r], default=None)
            if k is None:
                continue
            e = v[r]
            w = np.zeros(len(v))
            w[k:r + 1] = (t[k:r + 1] - t[k]) / (t[r] - t[k])
            w[r + 1:] = 1.0
            v = v - w[:, None] * e
        return v

    raw, vid = ROOT / "data" / "raw", ROOT / "data" / "video"
    rows = []
    for csv, video in DL_SPLICE:
        path, clip = raw / f"{csv}.csv", vid / f"{video}.mov"
        if not (path.exists() and clip.exists()):
            print(f"  {csv} or {video} not present — skipping")
            continue
        result = pipeline.run(path)
        log, t = result["log"], result["log"]["t"]
        impacts = segment.impact_anchors(log)
        lo, hi = result["bounds"][0][0], result["bounds"][-1][1] - 1
        rest = [k for k in segment.rest_instants(log, impacts) if lo <= k <= hi]
        stem = csv.split("_2026")[0]

        for label, do, order in [("shipping", False, 1),
                                 ("splice, order=1", True, 1),
                                 ("splice, order=2", True, 2)]:
            v = splice(result["velocity"], t, rest, impacts) if do else result["velocity"]
            pos = cumulative_trapezoid(v, np.cumsum(log["dt"]), axis=0, initial=0)
            reps = correct.detrend_set(pos, result["bounds"], t,
                                       velocity=v, order=order)
            h = metrics.vs_truth({**result, "reps": reps, "velocity": v},
                                 clip)["pipeline_h_rms"]
            rom = float(np.median([abs(p[:, 2].max() - p[:, 2].min())
                                   for p in reps]) * 100)
            rows.append({"capture": stem, "variant": label, "h": h, "rom": rom})
            print(f"  {stem:22s} {label:18s} h {h:6.2f} cm   ROM {rom:6.1f} cm"
                  + ("   <-- BREAKS ROM" if rom > ceil else ""))
    return rows


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


def draw_paused_squat() -> int:
    """C31a — the paused-squat short-count in `_longest_cadence`.

    Writes `analysis/47_squat_pause_segmentation.png`. Two of the four paused
    squats of 2026-08-06 counted 3 of 4 under the shipping rule: a paused set's
    cadence lengthens rep by rep, so the run's global gap spread cannot tell a
    fatiguing set from a set with a post-set movement tacked on.

    The tolerance panel is measured, not quoted. For each capture this sweeps
    the cadence tolerance and records every value at which that capture
    segments to its labelled rep count, under BOTH the pre-C31a rule (the run's
    global spread) and the shipped one (worst step between adjacent gaps). The
    old rule's two binding captures come out disjoint, which is the evidence
    that the constant could not simply be re-tuned.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import plot, segment

    def spread_cadence(chosen, t, tol):
        """`segment._longest_cadence` exactly as it stood before C31a."""
        if len(chosen) < 3:
            return chosen
        times = [t[l[0]] for l in chosen]
        found, i = [], 0
        while i < len(chosen):
            j = i + 1
            while j < len(chosen):
                g = np.diff(times[i:j + 1])
                if g.min() <= 0 or g.max() / g.min() > tol:
                    break
                j += 1
            found.append((j - i, float(np.median(times[i:j])), i, j))
            i += 1
        b = max(found, key=lambda r: (r[0], r[1]))
        return chosen[b[2]:b[3]]

    def cluster_of(vb, t, lobes):
        shapes = np.array([segment._shape(vb, t, i) for i, _, _, _ in lobes])
        peaks = np.array([np.abs(vb[a:b]).max() for _, a, b, _ in lobes])
        times = np.array([t[i] for i, _, _, _ in lobes])
        areas = np.array([abs(a) for _, _, _, a in lobes])
        best, bs = None, None
        for s in range(len(lobes)):
            keep = segment._grow(shapes, peaks, s, 0.7, 2.5)
            if not keep.any():
                continue
            n = int(keep.sum())
            sc = (n, float(np.median(times[keep])) if n > 1
                  else float(areas[keep].sum()))
            if bs is None or sc > bs:
                best, bs = keep, sc
        return [l for l, k in zip(lobes, best) if k] if best is not None else []

    def windows(allb, chosen, t, n):
        """`_similar_cluster`'s NMS then `_full_cycles`, i.e. the rest of step 5."""
        if len(chosen) > 2:
            span = np.median(np.diff([t[l[0]] for l in chosen]))
            merged = [chosen[0]]
            for l in chosen[1:]:
                if t[l[0]] - t[merged[-1][0]] < 0.6 * span:
                    if l[3] > merged[-1][3]:
                        merged[-1] = l
                else:
                    merged.append(l)
            chosen = merged
        return [tuple(map(int, b))
                for b in segment._full_cycles(allb, chosen, False, n)]

    raw2 = ROOT / "data_v2" / "raw"
    data: dict = {}
    for path in sorted(raw2.glob("squat_pause_*.csv")):
        stem = path.stem.split("_20260")[0]
        result = pipeline.run(path)
        log = result["log"]
        t = log["t"]
        vb = segment.bandpass(result["velocity"][:, 2], log["fs"])
        lobes = segment._concentric_lobes(vb, t, 0.08)
        allb = segment._all_lobes(vb, t, 0.08)
        cl = cluster_of(vb, t, lobes)
        old = windows(allb, spread_cadence(cl, t, 1.45), t, len(vb))
        new = windows(allb, segment._longest_cadence(cl, t), t, len(vb))
        data[stem] = {
            "t": t, "vb": vb,
            "lobes": [(int(a), int(b), int(pk), float(ar))
                      for pk, a, b, ar in lobes],
            "cluster": [float(t[l[0]]) for l in cl],
            "old": old, "new": new,
            "exp": pipeline.expected_reps(path),
        }
        print(f"{stem}: shipping rule {len(old)}/{data[stem]['exp']}, "
              f"C31a rule {len(new)}/{data[stem]['exp']}")

    if not data:
        print("no paused squats in data_v2/raw/")
        return 1

    # --- the tolerance panel, over every labelled capture in both datasets --
    cache: dict = {}
    for root in (ROOT / "data" / "raw", ROOT / "data_v2" / "raw"):
        for path in sorted(root.glob("*.csv")):
            exp = pipeline.expected_reps(path)
            if exp is None:
                continue
            result = pipeline.run(path)
            log = result["log"]
            t = log["t"]
            vb = segment.bandpass(result["velocity"][:, 2], log["fs"])
            lobes = segment._concentric_lobes(vb, t, 0.08)
            if not lobes:
                continue
            # a lift with floor impacts never reaches the cadence rule at all
            impact = len(segment.impact_anchors(log)) >= 3
            cache[path.name] = {
                "t": t, "allb": segment._all_lobes(vb, t, 0.08), "n": len(vb),
                "cl": None if impact else cluster_of(vb, t, lobes),
                "exp": exp, "impact": impact,
            }

    grid = np.arange(1.02, 2.60, 0.004)
    tol: dict = {}
    for rule_name, rule in (("old", spread_cadence),
                            ("new", segment._longest_cadence)):
        per: dict = {}
        for value in grid:
            for name, c in cache.items():
                good = (c["impact"] or
                        len(windows(c["allb"], rule(c["cl"], c["t"], float(value)),
                                    c["t"], c["n"])) == c["exp"])
                per.setdefault(name, []).append(good)
        tol[rule_name] = {
            name: (float(grid[np.argmax(v)]) if any(v) else None,
                   float(grid[len(v) - 1 - np.argmax(v[::-1])]) if any(v) else None,
                   bool(all(v)))
            for name, v in per.items()}
    data["_tol"] = tol
    data["_grid"] = (float(grid[0]), float(grid[-1]))

    fig = plot.plot_squat_pause_segmentation(data)
    out = ROOT / "analysis" / "47_squat_pause_segmentation.png"
    fig.savefig(out, dpi=125)
    print(f"wrote {out}")
    return 0


def draw_bar_path_with_d() -> int:
    """C31 — the bar path with step 6 on, now that `d` has been measured.

    Writes `analysis/48_bar_path_with_d.png`.

    `d` comes from `correct.WRIST_OFFSET_M`, the owner's tape of 2026-08-06.
    It is NOT fitted — B2 established that fitting it against the video is
    ill-conditioned and returns |d| = 129 cm under leave-one-out.

    Three captures, chosen to show the disagreement rather than the win: a
    deadlift, the bench where `d` clearly helped (`bench_95x2`, 1.46 -> 0.80 cm)
    and the paused bench where it clearly hurt (`bench_spoto_95x5_1`,
    1.17 -> 3.54). Each is scored twice against ONE tracked video path, so the
    only thing differing between the two curves is `wrist_offset`.
    """
    import matplotlib
    matplotlib.use("Agg")
    from src import correct, metrics, pipeline, plot, truth

    picks = ["deadlift_160x6_1", "bench_95x2", "bench_spoto_95x5_1"]
    raw = ROOT / "data_v2" / "raw"

    data = {}
    for stem in picks:
        hits = sorted(raw.glob(f"{stem}_*.csv"))
        if not hits:
            print(f"  {stem}: no capture found, skipping")
            continue
        csv = hits[0]
        video = pipeline.find_video(csv)
        if video is None:
            print(f"  {stem}: no video, skipping")
            continue
        # Track ONCE and score twice. resolve_path accepts the dict straight
        # back, so the two arms cannot differ by a re-track.
        path = metrics.resolve_path(video)
        d = correct.WRIST_OFFSET_M[truth.lift_of(csv)]
        arms = {}
        for tag, off in (("off", None), ("on", d)):
            res = pipeline.run(csv, wrist_offset=off)
            arms[tag] = metrics.vs_truth(res, path)
        arms["d"] = d
        data[stem] = arms
        print(f"  {stem}: h rms {arms['off']['pipeline_h_rms']:.2f} -> "
              f"{arms['on']['pipeline_h_rms']:.2f} cm")

    if not data:
        print("nothing to draw")
        return 1

    fig = plot.plot_bar_path_with_d(data)
    out = ROOT / "analysis" / "48_bar_path_with_d.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_pause_attitude() -> int:
    """C31 — does a PAUSE let Core Motion re-reference gravity mid-rep?

    Writes `analysis/49_pause_attitude_correction.png`.

    The owner's hypothesis, 2026-08-06: during a pause the watch is quasi-static,
    so the accelerometer becomes a trustworthy gravity reference and Core Motion
    corrects accumulated tilt error DURING the rep. That would land a step
    mid-rep at the same phase every rep, which is P3's signature and is exactly
    what step 7's boundary-anchored linear detrend cannot remove.

    The observable needs no video and no sync: the per-sample FUSION CORRECTION,
    Core Motion's attitude increment minus the gyro's (midpoint rule, so the
    left-endpoint discretisation error that contaminates a naive version is
    gone). Decomposed in the world frame into TILT and YAW, because gravity can
    correct tilt and is geometrically incapable of correcting yaw about gravity,
    while numerical error has no such preference.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from scipy.spatial.transform import Rotation
    from src import io, pipeline, plot

    NB = 20

    def split(log):
        q, dt, w = log["quat"], log["dt"], log["gyro"]
        R = Rotation.from_quat(q, scalar_first=True)
        wm = 0.5 * (w[:-1] + w[1:])
        inc = Rotation.from_rotvec(wm * dt[:-1, None]).inv() * (R[:-1].inv() * R[1:])
        world = R[:-1].apply(inc.as_rotvec())
        tilt = np.degrees(np.linalg.norm(world[:, :2], axis=1)) / dt[:-1]
        yaw = np.degrees(np.abs(world[:, 2])) / dt[:-1]
        return tilt, yaw

    csvs = sorted(list((ROOT / "data" / "raw").glob("*.csv"))
                  + list((ROOT / "data_v2" / "raw").glob("*.csv")))
    ty, prof = {}, {}
    for c in csvs:
        if pipeline.expected_reps(c) is None:
            continue
        log = io.load_log(c)
        tilt, yaw = split(log)
        a = np.linalg.norm(log["accel"], axis=1)[:-1]
        wm = np.degrees(np.linalg.norm(log["gyro"], axis=1))[:-1]
        q = (wm < 20.0) & (a < 1.5)
        ty[c.stem] = {
            "ratio_qs": float(np.median(tilt[q]) / max(np.median(yaw[q]), 1e-9)),
            "ratio_dyn": float(np.median(tilt[~q]) / max(np.median(yaw[~q]), 1e-9)),
        }
        if "deadlift" in c.name:
            continue
        r = pipeline.run(c)
        lift = "bench" if "bench" in c.name else "squat"
        style = "paused" if ("spoto" in c.name or "pause" in c.name) else "continuous"
        rows = []
        for i0, i1 in r["bounds"]:
            i1 = min(i1, len(tilt))
            if i1 - i0 < NB:
                continue
            ph = np.linspace(0, 1, i1 - i0)
            rows.append([np.median(tilt[i0:i1][(ph >= k / NB) & (ph < (k + 1) / NB)])
                         for k in range(NB)])
        if rows:
            prof.setdefault(lift, {}).setdefault(style, []).append(
                np.nanmedian(np.array(rows, dtype=float), axis=0))

    for lift in prof:
        for style in prof[lift]:
            prof[lift][style] = np.median(np.array(prof[lift][style]), axis=0)
        p, cont = prof[lift]["paused"], prof[lift]["continuous"]
        pk = float(np.max(p) / np.min(p))
        ck = float(np.max(cont) / np.min(cont))
        if pk > ck * 1.4:
            prof[lift]["verdict"] = (f"paused CONCENTRATES it mid-rep: peak/min "
                                     f"{pk:.2f} vs {ck:.2f}, peak at phase "
                                     f"{(np.argmax(p) + 0.5) / NB:.2f}")
        else:
            prof[lift]["verdict"] = (f"no concentration: peak/min {pk:.2f} vs "
                                     f"{ck:.2f}. Hypothesis does NOT hold here")
        print(f"  {lift}: {prof[lift]['verdict']}")

    rose = sum(1 for v in ty.values() if v["ratio_qs"] > v["ratio_dyn"])
    print(f"  tilt/yaw rises when quasi-static on {rose} of {len(ty)} captures")

    fig = plot.plot_pause_attitude({"ty": ty, "prof": prof})
    out = ROOT / "analysis" / "49_pause_attitude_correction.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_pipeline_now() -> int:
    """C31 — what the branch pipeline produces, on all three lifts.

    Writes `analysis/50_pipeline_now.png`. The product view rather than a
    diagnostic: step 9's output, reps overlaid, fore-aft stretched 4x, with the
    video over the top wherever a referee exists.

    Six captures chosen to span what the corpus can and cannot check: two
    deadlifts (one refereed by the conic marker path, one by the plate
    template), two benches (one where step 6 clearly helped, one where it
    clearly hurt) and two squats, which have no referee at all because
    `metrics.vs_truth` still refuses squat.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import metrics, pipeline, plot, truth

    picks = [
        ("data_v2", "deadlift_160x6_1"), ("data", "deadlift_155x6_1"),
        ("data_v2", "bench_95x2"), ("data_v2", "bench_spoto_95x5_1"),
        ("data_v2", "squat_pause_145x4_1"), ("data_v2", "squat_170x1"),
    ]
    panels = []
    for dataset, stem in picks:
        hits = sorted((ROOT / dataset / "raw").glob(f"{stem}_*.csv"))
        if not hits:
            print(f"  {stem}: not found, skipping")
            continue
        csv = hits[0]
        res = pipeline.run(csv)
        rom = np.median(res["rep_rom_m"]) * 100 if res["rep_rom_m"] else float("nan")
        exp = pipeline.expected_reps(csv)
        head = (f"{stem}   {len(res['reps'])}/{exp} reps   "
                f"median ROM {rom:.0f} cm")

        video, paths = None, res["planar"]
        try:
            m = metrics.vs_truth(res, pipeline.find_video(csv))
        except (ValueError, FileNotFoundError):
            # vs_truth's squat refusal is STALE rather than wrong-headed: its
            # stated reason describes the OLD template footage. Do not paraphrase
            # the exception into the caption — it would print a reason that is no
            # longer true. But do not overcorrect either: only two of the four
            # 8-sticker squat clips track cleanly (C31, 2026-08-07).
            cap = (f"{head}\nNO REFEREE — vs_truth still refuses squat "
                   f"(reason is stale; this footage tracks)")
        else:
            good = [r for r in m["per_rep"] if r.get("covered")]
            video = [r["curve_video"] for r in good]
            paths = [r["curve_pipeline"] for r in good]
            verdict = "beats" if m["beats_null"] > 1 else "LOSES TO"
            cap = (f"{head}\nh {m['pipeline_h_rms']:.2f} cm rms, "
                   f"v {m['pipeline_v_rms']:.2f}   "
                   f"{verdict} flat line ({m['beats_null']:.2f}x)")
        panels.append({"stem": stem, "paths": paths, "video": video,
                       "caption": cap})
        print(f"  {stem}: {len(res['reps'])}/{exp} reps"
              + ("" if video is None else f", scored"))

    if not panels:
        print("nothing to draw")
        return 1
    fig = plot.plot_pipeline_now(panels)
    out = ROOT / "analysis" / "50_pipeline_now.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def draw_jump_with_d() -> int:
    """C31 — does C29's jump correction compose with step 6's `d`?

    Writes `analysis/51_jump_with_d.png`.

    P6 was measured entirely before `d` existed: C29's rest-window jump
    correction took deadlift horizontal rms from 10.66 to 3.93 cm with step 6
    OFF, on the axis `d` most affects. Four arms on all six deadlifts, sharing
    the same rest-to-rest windows so the comparison is internal:

        control  rest windows, no correction, no d   <- C29's honest baseline
        C29      rest windows + 0.20 s jump, no d
        d        rest windows, no correction, with d
        both     rest windows + 0.20 s jump, with d

    Reproduces C29's own control and treatment (10.66 -> 3.93, beats_null
    0.21 -> 0.69) to two decimals, which is what licenses reading the new rows.
    """
    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    from src import correct, metrics, oracle, pipeline, plot, truth

    ARMS = [("control", -1, False), ("C29", 0.20, False),
            ("d", -1, True), ("both", 0.20, True)]
    csvs = (sorted((ROOT / "data" / "raw").glob("deadlift_*.csv"))
            + sorted((ROOT / "data_v2" / "raw").glob("deadlift_*.csv")))
    rows = {}
    for csv in csvs:
        video = pipeline.find_video(csv)
        if video is None:
            continue
        path = metrics.resolve_path(video)
        d = correct.WRIST_OFFSET_M[truth.lift_of(csv)]
        row = {}
        for tag, width, use_d in ARMS:
            base = pipeline.run(csv, wrist_offset=None)
            res = oracle.jump_rest_windows(
                base, width_s=width, wrist_offset=(d if use_d else None))
            m = metrics.vs_truth(res, path)
            row[tag] = (m["pipeline_h_rms"], m["beats_null"],
                        m["pipeline_v_rms"], m["n_compared"])
        rows[csv.stem[:24]] = row
        print(f"  {csv.stem[:24]}: "
              + "  ".join(f"{t} {row[t][0]:.2f}" for t, _, _ in ARMS))

    if not rows:
        print("nothing to draw")
        return 1
    for tag, _, _ in ARMS:
        med = np.median([r[tag][0] for r in rows.values()])
        mb = np.median([r[tag][1] for r in rows.values()])
        print(f"  {tag:8s} median h_rms {med:5.2f} cm   beats_null {mb:.2f}")

    fig = plot.plot_jump_with_d(rows, [a[0] for a in ARMS])
    out = ROOT / "analysis" / "51_jump_with_d.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_plot = "--plot" in argv
    want_truth = "--truth" in argv

    if "--stages" in argv:
        return draw_stages()
    if "--overview" in argv:
        return draw_overview()
    if "--paths" in argv:
        return draw_paths()
    if "--rom" in argv:
        return draw_rom()
    if "--dlconic" in argv:
        return draw_dl_conic()
    if "--v2rom" in argv:
        return draw_v2_video_rom()
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
    if "--pausedsquat" in argv:
        return draw_paused_squat()
    if "--dpaths" in argv:
        return draw_bar_path_with_d()
    if "--pauseattitude" in argv:
        return draw_pause_attitude()
    if "--pipelinenow" in argv:
        return draw_pipeline_now()
    if "--jumpd" in argv:
        return draw_jump_with_d()

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

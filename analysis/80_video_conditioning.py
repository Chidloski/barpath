"""H30 — what conditioning the video path rejects, and what it costs.

The owner: *"Video path should be smoothed slightly rather than being so
jagged, furthermore any anomalous data entries should be removed."*

Built as `src/vtrack/condition.py` and ON by default in `vtrack.bar_path` as of
2026-08-22. This is its evidence: what it catches, and the gate that it does
not move the measurement while catching it.

THE FIND, WHICH WAS NOT THE JAGGEDNESS
---------------------------------------
Smoothing was the ask; the anomalies were the problem. Four of the 36 committed
tracks contain frames implying motion faster than free fall, and **only two of
them were flagged by anything.** `IMPLAUSIBLE_FRAC`/`IMPLAUSIBLE_MULT` test
whole-clip travel, which cannot see a single frame in the middle of a sound
track:

    squat_pause_140x4_3_20260806   frame 128 reads 0.399 m between two
                                   neighbours at 0.663 — a 26 cm round trip in
                                   33 ms, inside a clip whose 71.6 cm travel
                                   passes the 61-68 cm band comfortably
    deadlift_150x4_1_20260808      peaks at 6.99 m/s downward against free
                                   fall's 5.05, and is the capture `TASKS.md`
                                   already records for segmenting 5 reps
                                   against a labelled and video-confirmed 4

Both are repaired — one frame and 22 frames respectively — and both keep their
clip. The two 2026-08-13 benches fail 2.2% and 10.0% of frames on speed and are
CONDEMNED rather than repaired, which is the distinction the module is built
around: a smooth path that is not the bar is worse than a visibly broken one.

THE GATE
--------
Smoothing a path invites one specific silent failure — clipping the turnarounds,
which shrinks range of motion and rescales every vertical figure in the repo
with nothing complaining. Savitzky-Golay at order 2 reproduces a parabola
exactly and a turnaround is locally parabolic, so it should not. Measured over
the 34 captures that are not condemned: **travel changes by a median of -0.004
cm and at most 0.27 cm**, against a +-2-3 cm vertical spec. `tests/test_vtrack.py`
gates it at 0.75 cm.

    python3 analysis/80_video_conditioning.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import tracked                        # noqa: E402
from src.vtrack import condition as C          # noqa: E402

TRACKED = ROOT / "data_v2" / "tracked"
OUT = ROOT / "analysis" / "80_video_conditioning.png"


def raw(csv):
    """The path as the tracker left it, whatever the cache has since become.

    `travel_m` is RECOMPUTED here and not read from the header. The cache now
    stores the conditioned scalar, so reading it while restoring the raw
    columns compares a path against itself and reports a change of exactly
    zero — which is what a first version of this script did, and it looked like
    a clean result rather than a bug.
    """
    d = tracked.read(None, src=csv)
    if "x_raw" in d and np.isfinite(d["x_raw"]).any():
        d = dict(d, x=d["x_raw"], height=d["height_raw"])
    d.pop("conditioned", None)
    h = np.asarray(d["height"], float)
    fin = np.isfinite(h)
    if fin.sum() > 2:
        lo, hi = np.nanpercentile(h[fin], [1, 99])
        d["travel_m"] = float(hi - lo)
    return d


def main():
    warnings.simplefilter("ignore")
    rows = []
    for csv in sorted(TRACKED.glob("*.csv")):
        d = raw(csv)
        c = C.condition(d, name=csv.stem)
        a = C.anomalies(d)
        dt = np.diff(d["t"])
        vz0 = float(np.nanmax(np.abs(np.diff(d["height"])) / dt))
        vx0 = float(np.nanmax(np.abs(np.diff(d["x"])) / dt))
        fin = np.isfinite(c["height"])
        vz1 = float(np.nanmax(np.abs(np.diff(c["height"][fin]))
                              / np.diff(c["t"][fin]))) if fin.sum() > 2 else np.nan
        rows.append(dict(name=csv.stem, lift=d.get("lift", "?"),
                         n=len(d["t"]), n_bad=a["n_bad"], n_speed=a["n_speed"],
                         n_resid=a["n_resid"], n_missing=a["n_missing"],
                         cond=c["condemned"], t0=d["travel_m"] * 100,
                         t1=c["travel_m"] * 100, vz0=vz0, vx0=vx0, vz1=vz1))

    print(f"{'capture':36s} {'lift':9s} {'rej':>4s} {'spd':>4s} {'res':>4s} "
          f"{'gap':>4s} {'travel':>7s}{'->':>8s} {'d cm':>6s} {'maxv':>6s}{'->':>7s}")
    for r in rows:
        tag = "  CONDEMNED" if r["cond"] else ""
        print(f"{r['name']:36s} {r['lift']:9s} {r['n_bad']:4d} {r['n_speed']:4d} "
              f"{r['n_resid']:4d} {r['n_missing']:4d} {r['t0']:7.2f} {r['t1']:8.2f} "
              f"{r['t1'] - r['t0']:+6.2f} {r['vz0']:6.2f} {r['vz1']:7.2f}{tag}")

    keep = [r for r in rows if not r["cond"]]
    d = np.array([r["t1"] - r["t0"] for r in keep])
    print(f"""
{len(rows)} captures, {sum(r['cond'] for r in rows)} condemned, {len(keep)} conditioned.
travel change over the conditioned: median {np.median(d):+.3f} cm, worst |{np.abs(d).max():.3f}| cm
  -> the smoothing does NOT eat the turnarounds, which is the only way an
     order-2 filter could have damaged the measurement.
frames rejected: {sum(r['n_bad'] for r in keep)} of {sum(r['n'] for r in keep)} """
          f"""({100 * sum(r['n_bad'] for r in keep) / sum(r['n'] for r in keep):.2f}%)
impossible frames surviving: {sum(1 for r in keep if r['vz1'] > C.V_MAX_MS)}""")

    _figure(rows)


def _figure(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1])

    # -- the two repairs, drawn ------------------------------------------
    for k, (name, lo, hi) in enumerate([
            ("squat_pause_140x4_3_20260806", 100, 165),
            ("deadlift_150x4_1_20260808", None, None)]):
        ax = fig.add_subplot(gs[0, k])
        d = raw(TRACKED / f"{name}.csv")
        c = C.condition(d, name=name)
        sl = slice(lo, hi) if lo is not None else slice(None)
        ax.plot(d["t"][sl], d["height"][sl] * 100, lw=1.4, color="#c53030",
                label="raw", zorder=1)
        ax.plot(c["t"][sl], c["height"][sl] * 100, lw=1.1, color="#2b6cb0",
                label="conditioned", zorder=2)
        rej = np.asarray(c["rejected"], bool)[sl]
        ax.scatter(d["t"][sl][rej], d["height"][sl][rej] * 100, s=42,
                   facecolors="none", edgecolors="#c53030", lw=1.6,
                   label="rejected", zorder=3)
        ax.set_title(f"{name}\n{c['n_rejected']} rejected — the travel gate saw "
                     f"nothing wrong", fontsize=9)
        ax.set_xlabel("t, s")
        ax.set_ylabel("height, cm")
        ax.legend(fontsize=8)

    # -- the speed separation --------------------------------------------
    ax = fig.add_subplot(gs[0, 2])
    keep = [r for r in rows if not r["cond"]]
    cond = [r for r in rows if r["cond"]]
    ax.scatter([r["vz0"] for r in keep], [r["vx0"] for r in keep], s=26,
               color="#2b6cb0", label=f"tracks ({len(keep)})")
    ax.scatter([r["vz0"] for r in cond], [r["vx0"] for r in cond], s=70,
               marker="X", color="#c53030", label=f"condemned ({len(cond)})")
    ax.axvline(C.V_MAX_MS, color="#2f855a", ls="--", lw=1.2)
    ax.axhline(C.V_MAX_MS, color="#2f855a", ls="--", lw=1.2,
               label=f"free fall, {C.V_MAX_MS} m/s")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("peak vertical speed, m/s")
    ax.set_ylabel("peak horizontal speed, m/s")
    ax.set_title("the constant is derived, and it sits in a real gap", fontsize=9)
    ax.legend(fontsize=8)

    # -- travel is preserved ---------------------------------------------
    ax = fig.add_subplot(gs[1, :2])
    names = [r["name"] for r in keep]
    delta = [r["t1"] - r["t0"] for r in keep]
    ax.bar(range(len(keep)), delta, color="#2b6cb0")
    ax.axhline(0, color="k", lw=.6)
    for y, c_ in ((0.75, "#c53030"), (-0.75, "#c53030")):
        ax.axhline(y, color=c_, ls="--", lw=1.0)
    ax.set_xticks(range(len(keep)))
    ax.set_xticklabels(names, rotation=90, fontsize=5.5)
    ax.set_ylabel("travel change, cm")
    ax.set_ylim(-1.0, 1.0)
    ax.set_title("smoothing does not move the vertical measurement "
                 "(dashed: the 0.75 cm gate; spec is +-2-3 cm)", fontsize=9)

    # -- what each test caught -------------------------------------------
    ax = fig.add_subplot(gs[1, 2])
    tot = {"speed": sum(r["n_speed"] for r in rows),
           "residual": sum(r["n_resid"] for r in rows),
           "untracked": sum(r["n_missing"] for r in rows)}
    ax.bar(list(tot), list(tot.values()),
           color=["#c53030", "#c05621", "#718096"])
    for i, v in enumerate(tot.values()):
        ax.text(i, v, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("frames, whole corpus")
    ax.set_title("what each test rejected", fontsize=9)

    fig.suptitle("H30 — conditioning the video referee: four broken tracks, "
                 "two of them invisible until now", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

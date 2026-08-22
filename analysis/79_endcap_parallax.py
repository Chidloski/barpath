"""H30 — can the sleeve endcap marker give us bar TILT, and so the bar CENTRE?

The owner's proposal: there are eight markers on the plate and one on the
endcap, so use the orientation and parallax between the endcap and the eight
point conic to remove tilt and recover the path at the CENTRE of the bar.

This measures whether that is possible on this footage. It builds no
correction. `src/vtrack/geometry.py` holds the conversion the answer would feed.

WHAT THE CONVERSION ACTUALLY NEEDS, WHICH IS LESS THAN IT SOUNDS
----------------------------------------------------------------
The sticker circle and the bar centre are separated PURELY ALONG THE BAR. Both
reported quantities — height and fore-aft — are perpendicular to the bar. So a
level bar needs no conversion at all: the tracked point already has the bar
centre's height and the bar centre's fore-aft. The whole of "convert to the bar
centre" is one term, `L * sin(theta)`, and the whole difficulty is `theta`.

THREE FINDINGS, AND THE THIRD DECIDES IT
-----------------------------------------
1. The conic's own ORIENTATION cannot supply theta, and this is arithmetic
   rather than a measurement. A circle tilted by theta projects to an ellipse of
   aspect cos(theta). At the 1-3 degrees a barbell actually tilts that is a
   0.015-0.14% departure from round — on an 85 px radius, 0.01 to 0.11 px. The
   ellipticity is second order in the angle and dies in the noise. Only the
   endcap PARALLAX, which is first order, carries the signal. So of the owner's
   two proposed cues, one is unusable for a reason no better footage fixes.

2. The endcap offset is real, large, and 81-96% explained by WHERE THE BAR IS
   IN FRAME. That is perspective, not tilt: the endcap sits nearer the camera
   than the sticker plane, so it projects displaced radially from the principal
   point, and the bar traverses most of the frame during a rep. A quadratic in
   the plate centre's own image position cuts the offset's spread from
   10.2-12.9 px to 2.0-2.7 px.

3. **The residual has not converged, so it is an upper bound on tilt and not a
   measurement of it.** Going from a plane to a quadratic ate a third of it
   (3.07/3.22/3.89 -> 2.00/2.74/2.44 px) and a cubic ate a little more, and the
   deadlift's lag-1 autocorrelation fell from 0.51 to 0.32 as it did — i.e. what
   the plane left behind was substantially the plane's own rep-periodic error,
   which is exactly the error class `CLAUDE.md`'s spec section says does NOT
   cancel rep-to-rep. What survives is 2.0-2.7 px, and `geometry.lever_ratio`
   magnifies that by 2.0-3.7 on its way to the bar centre: 1.1-1.7 cm against a
   ~1 cm horizontal spec.

So: the mechanism the owner named is real and correctly identified, the conic
half of it is unusable in principle, and the endcap half bounds bar tilt at
about 1-2 cm at the bar centre without being able to measure it. That bound is
worth having — `tracked.py` has named bar tilt as an error source since C31
without anyone sizing it — but a correction built on a residual that shrinks
every time the model improves would be fitting the model's own error into the
bar path. Nothing is applied. What would change it is in the report at the end.

    python3 analysis/79_endcap_parallax.py [clip ...]
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.vtrack import geometry as G          # noqa: E402
from src.vtrack.detect import frames_rgb      # noqa: E402
from src.vtrack.path import track_clip        # noqa: E402

VIDEO = ROOT / "data_v2" / "video"
OUT = ROOT / "analysis" / "79_endcap_parallax.png"

# A window around the fitted circle centre, in px, inside which the endcap
# marker must lie. The endcap is on the bar AXIS and so is the circle centre,
# so their image separation is bounded by the parallax — measured at 7-22 px
# over the corpus, so 26 is generous without admitting the stickers themselves
# at r = 85-90.
R_WIN = 26

# The marker is retroreflective: lit, it is among the brightest things in the
# frame; unlit, it is simply absent. These are the presence test, and the
# detector MUST be allowed to return nothing — a first version took the
# brightest thing in the window unconditionally and produced incoherent offsets
# because it was tracking the collar and the sleeve highlight half the time.
W_ABS = 0.62
W_CONTRAST = 0.22

DEFAULT = ["deadlift_160x6_2_20260804", "squat_pause_140x4_2_20260806",
           "bench_spoto_95x5_1_20260806"]


def endcap_offsets(name, cache_dir=None):
    """Endcap marker position RELATIVE to the fitted sticker-circle centre."""
    v = VIDEO / f"{name}.mov"
    res = track_clip(v, cache_dir=cache_dir)
    sm = res["summary"]
    cy, cx = sm["y_px"], sm["x_px"]
    n = len(cy)
    dy = np.full(n, np.nan)
    dx = np.full(n, np.nan)

    i = 0
    for chunk in frames_rgb(v):
        for fr in chunk:
            if i >= n:
                break
            if np.isfinite(cy[i]):
                f = fr.astype(np.float32) / 255.0
                vv, mn = f.max(2), f.min(2)
                sat = np.where(vv > 1e-6, (vv - mn) / np.maximum(vv, 1e-6), 0.0)
                w = vv * (1.0 - sat)
                y, x = int(round(cy[i])), int(round(cx[i]))
                y0, y1 = max(0, y - R_WIN), min(w.shape[0], y + R_WIN + 1)
                x0, x1 = max(0, x - R_WIN), min(w.shape[1], x + R_WIN + 1)
                gy, gx = np.mgrid[y0:y1, x0:x1]
                mask = np.hypot(gy - cy[i], gx - cx[i]) <= R_WIN
                s = np.where(mask, w[y0:y1, x0:x1], 0.0)
                sm3 = ndimage.uniform_filter(s, 3)
                j = np.unravel_index(np.argmax(sm3), s.shape)
                pk = float(sm3[j])
                if pk > W_ABS and pk - float(np.median(s[mask])) > W_CONTRAST:
                    a0, a1 = max(0, j[0] - 2), min(s.shape[0], j[0] + 3)
                    b0, b1 = max(0, j[1] - 2), min(s.shape[1], j[1] + 3)
                    ww = np.clip(s[a0:a1, b0:b1] - s[a0:a1, b0:b1].min(), 0, None)
                    tot = ww.sum()
                    if tot > 0:
                        my, mx = np.mgrid[a0:a1, b0:b1]
                        dy[i] = (ww * my).sum() / tot + y0 - cy[i]
                        dx[i] = (ww * mx).sum() / tot + x0 - cx[i]
            i += 1
        if i >= n:
            break
    return dict(name=name, lift=res["lift"], t=sm["t"], dy=dy, dx=dx,
                cy=cy, cx=cx, m_per_px=sm["m_per_px"], height=sm["height_m"])


def _design(cy, cx, order):
    """Perspective model in the plate centre's own image position.

    True perspective is a RATIO in depth, so a plane in (cy, cx) under-fits it
    and the shortfall is rep-periodic — the bar returns to the same depth every
    rep. Order 2 is what the corpus asks for: it takes the residual from
    3.07/3.22/3.89 px to 2.00/2.74/2.44, while order 3 gains only 0.06-0.20
    more. See `main`'s note on what that does to the verdict.
    """
    cols = [np.ones_like(cy), cy, cx]
    if order >= 2:
        cols += [cy * cy, cx * cx, cy * cx]
    return np.column_stack(cols)


def decompose(s, order=2):
    """Split the offset into a perspective model and what it leaves behind."""
    dy, dx, cy, cx = s["dy"], s["dx"], s["cy"], s["cx"]
    ok = np.isfinite(dy) & np.isfinite(cy)
    if ok.sum() < 30:
        return None
    A = _design(cy[ok], cx[ok], order)
    out = {"n": int(ok.sum()), "ok": ok, "order": order}
    for k, d in (("y", dy), ("x", dx)):
        r = d[ok] - A @ np.linalg.lstsq(A, d[ok], rcond=None)[0]
        out[f"sd_{k}"] = float(d[ok].std())
        out[f"resid_{k}"] = float(r.std())
        full = np.full(len(dy), np.nan)
        full[ok] = r
        out[f"r{k}"] = full
    out["corr_y"] = float(np.corrcoef(dy[ok], cy[ok])[0, 1])
    out["corr_x"] = float(np.corrcoef(dx[ok], cx[ok])[0, 1])
    return out


def autocorr(r, k=1):
    """Lag-k autocorrelation over the longest contiguous run of detections."""
    fin = np.isfinite(r)
    best, cur = [], []
    for i, v in enumerate(fin):
        cur = cur + [i] if v else []
        if len(cur) > len(best):
            best = list(cur)
    if len(best) < 40:
        return float("nan"), len(best)
    seg = r[best] - r[best].mean()
    return float((seg[:-k] * seg[k:]).mean() / seg.var()), len(best)


def load_kg(name):
    import re
    m = re.search(r"_(\d+(?:\.\d+)?)x\d+", name)
    return float(m.group(1)) if m else None


def main(names):
    warnings.simplefilter("ignore")
    rows, series = [], []
    for name in names:
        s = endcap_offsets(name)
        d = decompose(s)
        if d is None:
            print(f"{name:34s} too few endcap detections")
            continue
        a1, nrun = autocorr(d["ry"])
        kg = load_kg(name)
        lift = s["lift"]
        lev = G.lever_ratio(lift, kg) if kg else float("nan")
        L = G.marker_plane_m(lift, kg) if kg else float("nan")
        cm_endcap = d["resid_y"] * s["m_per_px"] * 100
        rows.append(dict(name=name, lift=lift, kg=kg, n=d["n"], L=L, lever=lev,
                         sd=d["sd_y"], resid=d["resid_y"], corr=d["corr_y"],
                         ac1=a1, nrun=nrun, cm_endcap=cm_endcap,
                         cm_centre=cm_endcap * lev,
                         deg=np.degrees(np.arcsin(np.clip(
                             cm_endcap / 100 / G.endcap_baseline_m(lift, kg),
                             -1, 1))) if kg else float("nan")))
        series.append((s, d))

    print(f"\n{'capture':32s} {'n':>5s} {'r(dy,cy)':>9s} {'sd':>6s} {'resid':>6s} "
          f"{'ac1':>6s} {'L':>6s} {'L/a':>5s} {'cm@cap':>7s} {'cm@ctr':>7s} {'deg':>6s}")
    for r in rows:
        print(f"{r['name']:32s} {r['n']:5d} {r['corr']:+9.3f} {r['sd']:6.2f} "
              f"{r['resid']:6.2f} {r['ac1']:+6.3f} {r['L']:6.3f} {r['lever']:5.2f} "
              f"{r['cm_endcap']:7.2f} {r['cm_centre']:7.2f} {r['deg']:6.2f}")

    print(f"""
READ IT AS THE ERROR BUDGET IT IS
  resid   px left after a QUADRATIC perspective model — the tilt budget, and
          an upper bound rather than an estimate (see the verdict)
  ac1     lag-1 autocorrelation of that residual. >0.7 means SMOOTH, i.e. a
          physical signal rather than centroid noise
  L/a     geometry.lever_ratio — how much an endcap error is magnified at the
          bar centre
  cm@ctr  resid, in cm, AT THE BAR CENTRE. This is the number to compare with
          the ~1 cm horizontal spec

VERDICT — AND IT IS AN UPPER BOUND, NOT AN ESTIMATE
The residual is smooth on {sum(1 for r in rows if r['ac1'] > 0.7)} of {len(rows)}, so the endcap is sensing something
physical. But raising the perspective model from a plane to a quadratic ate a
THIRD of it (3.07/3.22/3.89 -> 2.00/2.74/2.44 px) and a cubic ate a little
more, so the residual is still converging and we cannot separate "tilt the
endcap can see" from "perspective this model gets wrong".

So the honest statement is a BOUND: bar tilt contributes AT MOST {min(r['cm_centre'] for r in rows):.1f}-{max(r['cm_centre'] for r in rows):.1f} cm at the
bar centre, and possibly much less. That is worth having on its own — `tracked.py`
names bar tilt as a known error source that nothing in the repo had ever sized —
but it is not a correction, and building one on a signal that shrinks every time
the model improves would be fitting the model's own error into the bar path.

WHAT WOULD CHANGE IT, cheapest first
  1. Resolution. This footage is 360x640. The endcap centroid error scales
     directly with it, so 1080p would cut every figure above by ~3x and put the
     bar-centre bound at 0.4-0.6 cm — under the spec, and low enough that what
     survives could finally be separated from the perspective model. This is
     the single highest-value change and it costs nothing but a capture
     setting.
  2. A second endcap marker, or markers on BOTH ends. The far plate is
     currently unmarked; marking it turns a 0.185-0.375 m tilt baseline into
     1.73 m and makes the lever ratio LESS than one instead of 2-5.
  3. Camera intrinsics. A checkerboard calibration would replace the fitted
     polynomial with the real projection. An unknown but demonstrably nonzero
     part of the 2.0-2.7 px is that model being approximate — going from a
     plane to a quadratic already removed a third of it.
""")

    _figure(series, rows)


def _figure(series, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(series)
    fig, axs = plt.subplots(3, n, figsize=(4.6 * n, 10.5), squeeze=False)
    for k, ((s, d), r) in enumerate(zip(series, rows)):
        ok = d["ok"]
        ax = axs[0][k]
        ax.scatter(s["cy"][ok], s["dy"][ok], s=3, alpha=.35, color="#2b6cb0")
        ax.set_title(f"{r['name']}\noffset vs bar height in frame  "
                     f"r={r['corr']:+.2f}", fontsize=9)
        ax.set_xlabel("plate centre, px down frame")
        ax.set_ylabel("endcap offset dy, px")

        ax = axs[1][k]
        ax.plot(s["t"], d["ry"], lw=.8, color="#c05621")
        ax.axhline(0, color="k", lw=.5)
        ax.set_title(f"residual after the quadratic model — sd {r['resid']:.2f} px, "
                     f"ac1 {r['ac1']:+.2f}", fontsize=9)
        ax.set_xlabel("t, s")
        ax.set_ylabel("residual, px")

        ax = axs[2][k]
        ax.bar([0, 1, 2], [r["cm_endcap"], r["cm_centre"], 1.0],
               color=["#2b6cb0", "#c53030", "#2f855a"])
        ax.set_xticks([0, 1, 2])
        ax.set_xticklabels(["at the\nendcap", f"at the bar centre\n(x{r['lever']:.1f})",
                            "the spec"], fontsize=8)
        ax.set_ylabel("cm")
        ax.set_title("the error budget", fontsize=9)
    fig.suptitle("H30 — the endcap as a tilt sensor: real signal, wrong size",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT, dpi=120)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)

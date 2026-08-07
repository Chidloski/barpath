"""Track a video once, cache it to CSV, and SHOW whether the tracking is usable.

Added 2026-08-07 (C31) on the owner's instruction, and it fixes two problems
that turned out to be the same problem.

**Re-tracking is the dominant cost of every analysis.** A clip takes 1-2 minutes
to decode and track, `metrics.resolve_path` did it afresh on every call, and a
comparison that scores one capture two ways paid for it twice. Whole sessions
here have been spent waiting on ffmpeg.

**And nobody ever looked at the tracking.** That is the expensive half. Two of
the four squat clips have been reporting 14 and 24 cm of travel for 65-70 cm
squats — the tracker locked onto a rack upright and a floor fixture, with two
static points pinning the fit so coverage read 96.7-97.8% and the whole-clip
residual 1.11-1.12 px (D2, 2026-08-07). Every summary statistic said healthy.
A human glancing at the path for two seconds would have caught it immediately,
and no human had ever been shown one.

So the protocol is now: **the moment a video is supplied, track it, write the
path to CSV beside the capture, and render a review figure.** The CSV is
committed, so the cost is paid once for the life of the repo rather than once
per analysis. The figure exists to be looked at by a person before any number
derived from that clip is believed.

The review figure
-----------------
One panel for the whole clip and one per rep, and **the reps are found from the
video alone** — no IMU, no sync, no `pipeline.run`. That is deliberate: this
figure has to be readable for a clip that has no paired capture at all, and it
must not inherit a segmentation error from the thing it exists to check. See
`video_reps`.

What the cache does NOT protect you from
----------------------------------------
**A cached path is only valid for the tracker code that produced it.** Change
`markers.py` or `truth.py` and every CSV is stale, silently, in exactly the way
this project keeps getting hurt by. The header records the tracker, the git
commit and the time, so staleness is visible if you look — but nothing enforces
it. `refresh` and `force=True` exist for that; use them after any tracker
change, and re-render the figures.

The camera side is recorded here because it is not recoverable from the footage
by anything in this repo, and it matters: on bench and squat the camera is on
the lifter's right while the watch is on the left wrist, so the referee tracks
the plate on the OPPOSITE END OF THE BAR from the sensor. Bar tilt or an uneven
press is then scored as pipeline error. Deadlift is the only lift where camera
and watch are on the same side.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import metrics, truth

# Which side of the lifter the camera stands on (owner, 2026-08-06). The watch
# is on the LEFT wrist throughout. Not derivable from the footage; recorded
# because it decides which end of the bar the referee is watching.
CAMERA_SIDE = {"deadlift": "left", "bench": "right", "squat": "right"}

# Per-frame columns written to the CSV. Anything else in the path dict is a
# scalar or a diagnostic and goes in the header, except the (N, 2) arrays which
# are dropped — they are reconstructible and would double the file.
FRAME_COLUMNS = ("t", "x", "height", "score", "n_markers", "residual_px",
                 "m_per_px_t", "circumradius_px", "axis_ratio", "angle")

# Scalars worth keeping. `calibration` is a nested dict and is flattened out.
SCALAR_KEYS = ("fps", "m_per_px", "travel_m", "plate_radius_px", "seed_frame",
               "perspective_shift_cm", "n_rim", "sticker_radius_m")


def _dataset(video: str | Path) -> Path:
    """The dataset root a clip belongs to — `data/` or `data_v2/`."""
    return Path(video).resolve().parents[1]


def csv_path(video: str | Path) -> Path:
    """Where the cached track for `video` lives, `<dataset>/tracked/<stem>.csv`.

    Beside the capture rather than in `analysis/`, because it is data derived
    from that dataset and belongs with it. These ARE committed — they are small
    (one row per frame, ~900 rows) and deterministic, and committing them is the
    whole point: the cost is paid once for the repo, not once per session.
    """
    return _dataset(video) / "tracked" / f"{Path(video).stem}.csv"


def figure_path(video: str | Path, root: Path | None = None) -> Path:
    """Where the review figure for `video` lives."""
    root = root or Path(__file__).resolve().parents[1] / "analysis" / "tracking"
    return Path(root) / f"{Path(video).stem}.png"


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=Path(__file__).resolve().parents[1],
                              capture_output=True, text=True,
                              timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def write(path: dict, video: str | Path, dest: Path | None = None) -> Path:
    """Write a tracked path dict to CSV. Header carries the scalars.

    The header is `# key = value` lines, which `read` parses back. It records
    the tracker, the git commit and the timestamp so a stale cache is visible to
    anyone who looks — see the module docstring on why nothing enforces it.
    """
    dest = Path(dest) if dest else csv_path(video)
    dest.parent.mkdir(parents=True, exist_ok=True)

    cols = [c for c in FRAME_COLUMNS
            if isinstance(path.get(c), np.ndarray) and path[c].ndim == 1]
    n = len(path["t"])
    data = np.column_stack([np.asarray(path[c], dtype=float) for c in cols])

    lines = [f"# video = {Path(video).name}",
             f"# tracker = {metrics.infer_tracker(video)}",
             f"# commit = {_git_commit()}",
             f"# generated = {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}",
             f"# n_frames = {n}"]
    try:
        lines.append(f"# lift = {truth.lift_of(video)}")
        lines.append(f"# camera_side = {CAMERA_SIDE[truth.lift_of(video)]}")
    except (ValueError, KeyError):
        pass
    for k in SCALAR_KEYS:
        v = path.get(k)
        if isinstance(v, (int, float, np.integer, np.floating)):
            lines.append(f"# {k} = {float(v):.12g}")
    lines.append(",".join(cols))
    # 12 significant figures, not 6. At 6 a cached score differed from a
    # fresh track by ~1.6e-3 cm — negligible against a 1 cm spec, but this
    # repo checks regressions by bit-identity and a cache that is silently
    # 0.1% different is exactly the kind of thing that costs a day.
    body = "\n".join(",".join(f"{v:.12g}" for v in row) for row in data)
    dest.write_text("\n".join(lines) + "\n" + body + "\n")
    return dest


def read(video: str | Path, src: Path | None = None) -> dict | None:
    """Read a cached track back, or None if there is no cache.

    Returns a dict shaped like `truth.bar_path` / `markers.bar_path` output —
    key-compatible by design, so `metrics.vs_truth` consumes it without knowing
    it came from disk. Keys absent from the CSV are simply absent; callers that
    need a tracker-specific diagnostic should track afresh.
    """
    src = Path(src) if src else csv_path(video)
    if not src.is_file():
        return None

    out: dict = {}
    header, names = [], None
    with src.open() as fh:
        for line in fh:
            if line.startswith("#"):
                header.append(line[1:].strip())
            else:
                names = [c.strip() for c in line.strip().split(",")]
                break
    if not names:
        return None
    for h in header:
        if "=" not in h:
            continue
        k, v = (p.strip() for p in h.split("=", 1))
        if k in SCALAR_KEYS:
            try:
                out[k] = float(v)
            except ValueError:
                pass
        else:
            out[k] = v

    arr = np.loadtxt(src, delimiter=",", skiprows=len(header) + 1, ndmin=2)
    if arr.size == 0:
        return None
    for i, name in enumerate(names):
        out[name] = arr[:, i]
    return out


def ensure(video: str | Path, force: bool = False, figure: bool = True) -> dict:
    """The protocol: track once, cache to CSV, render the review figure.

    Returns the path dict either way. `force=True` re-tracks and overwrites,
    which is what you do after changing a tracker — see the module docstring.

    `figure=False` skips the render, for callers that only want the numbers;
    the CSV is still written, because a cache that is sometimes not written is
    worse than no cache.
    """
    cached = None if force else read(video)
    if cached is not None:
        return cached

    path = metrics.resolve_path(video)
    write(path, video)
    if figure:
        try:
            render_figure(path, video)
        except Exception as exc:                       # pragma: no cover
            # A figure failure must not cost the caller its track. The CSV is
            # already on disk by this point, which is the part that matters.
            print(f"  {Path(video).name}: figure failed ({exc})")
    return path


def video_reps(path: dict, min_frac: float = 0.35) -> list[tuple[int, int]]:
    """Rep windows found from the VIDEO ALONE — no IMU, no sync, no pipeline.

    Deliberately independent of `segment.py`. This figure exists to let a human
    judge whether the tracking is usable, so it must work on a clip with no
    paired IMU capture, and it must not inherit a segmentation error from the
    very thing it is checking. C24 used the same idea to referee both sides of
    a disagreement the IMU could not settle.

    Windows run trough to trough of the smoothed height. That is the bottom of
    the movement on every lift here — the floor on a deadlift, the chest on a
    bench, the hole on a squat — so one rule covers all three, at the cost of
    windows being half a rep out of phase with `segment.rep_bounds`. For a
    review figure that does not matter; do not use these as rep boundaries for
    anything quantitative.

    `min_frac` is the prominence a trough needs, as a fraction of total travel.
    Returns [] rather than guessing when the height is unusable.
    """
    from scipy.signal import find_peaks

    h = np.asarray(path.get("height"), dtype=float)
    ok = np.isfinite(h)
    if ok.sum() < 10:
        return []
    h = np.interp(np.arange(len(h)), np.flatnonzero(ok), h[ok])

    fps = float(path.get("fps") or 30.0)
    win = max(3, int(round(0.15 * fps)) | 1)
    kern = np.ones(win) / win
    sm = np.convolve(h, kern, mode="same")

    travel = float(np.ptp(sm))
    if travel <= 0:
        return []
    troughs, _ = find_peaks(-sm, prominence=min_frac * travel,
                            distance=max(1, int(0.5 * fps)))
    if len(troughs) < 2:
        return []
    return [(int(a), int(b)) for a, b in zip(troughs[:-1], troughs[1:])]


def review(video: str | Path) -> dict:
    """Numbers a human needs to judge a track, for the figure's captions."""
    path = read(video) or metrics.resolve_path(video)
    h = np.asarray(path["height"], dtype=float)
    x = np.asarray(path["x"], dtype=float)
    ok = np.isfinite(h) & np.isfinite(x)
    reps = video_reps(path)
    out = {
        "coverage": float(ok.mean()),
        "travel_cm": float(np.ptp(h[ok]) * 100) if ok.any() else float("nan"),
        "fore_aft_cm": float(np.ptp(x[ok]) * 100) if ok.any() else float("nan"),
        "n_reps": len(reps),
        "reps": reps,
        "tracker": path.get("tracker", "?"),
        "lift": path.get("lift", "?"),
        "camera_side": path.get("camera_side", "?"),
    }
    res = path.get("residual_px")
    out["residual_px"] = (float(np.nanmedian(res))
                          if isinstance(res, np.ndarray) else float("nan"))
    sc = path.get("score")
    out["score"] = (float(np.nanmedian(sc))
                    if isinstance(sc, np.ndarray) else float("nan"))

    # The flag that would have caught the squat clips. A lift's per-rep travel
    # is fixed by the lifter's limbs, so a whole-clip travel far below the
    # plausible range means the tracker is following something that is not the
    # bar — however healthy its coverage and residual look.
    try:
        lo, _ = truth.VERTICAL_ROM_M[truth.lift_of(video)]
        out["implausible"] = out["travel_cm"] < lo * 100 * 0.9
    except (ValueError, KeyError):
        out["implausible"] = False
    return out


def render_figure(path: dict, video: str | Path) -> Path:
    """Render and save the per-video review figure. Returns its path."""
    import matplotlib
    matplotlib.use("Agg")
    from . import plot

    dest = figure_path(video)
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = review(video) if csv_path(video).is_file() else None
    fig = plot.plot_tracking_review(path, Path(video).stem, info)
    fig.savefig(dest, dpi=110)
    matplotlib.pyplot.close(fig)
    return dest

"""Draw detections (and optional fitted ellipse) over a frame, for eyeballing."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "/Users/sam/.claude/jobs/b4b2d95a/tmp")
from detect import probe


def frame_at(path, idx):
    """One frame by index, seeking by timestamp.

    `select=eq(n,idx)` decodes every frame from the start, so pulling four
    frames from the end of a 1600-frame clip costs four full decodes. Seeking
    with `-ss` before `-i` costs one keyframe jump. The half-frame offset lands
    the seek inside the target frame's interval rather than on its boundary.
    """
    w, h, fps = probe(path)
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{(idx + 0.5) / fps:.4f}",
         "-i", str(path), "-frames:v", "1",
         "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    if len(raw) < w * h * 3:
        # Seeking past the last frame returns nothing. Fall back to decoding
        # the tail, which matters because the artifact frames on
        # `deadlift_150x4_1` are literally the last four of the clip.
        raw = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-sseof", "-1.0",
             "-i", str(path), "-frames:v", "1",
             "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
            capture_output=True, check=True).stdout
    return np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3)


def show(path, idx, dets=None, ellipse=None, out="/tmp/f.png", title="",
         zoom=None):
    img = frame_at(path, idx)
    fig, ax = plt.subplots(figsize=(7, 12), dpi=110)
    ax.imshow(img)
    if dets is not None and len(dets):
        d = np.asarray(dets)
        sc = ax.scatter(d[:, 1], d[:, 0], s=90, facecolors="none",
                        edgecolors=plt.cm.viridis(
                            (d[:, 2] - d[:, 2].min()) /
                            max(1e-9, np.ptp(d[:, 2]))), linewidths=1.2)
    if ellipse is not None:
        t = np.linspace(0, 2 * np.pi, 200)
        cy, cx, a, b, th = ellipse
        y = cy + a * np.sin(t) * np.sin(th) + b * np.cos(t) * np.cos(th)
        x = cx + a * np.sin(t) * np.cos(th) - b * np.cos(t) * np.sin(th)
        ax.plot(x, y, "r-", lw=1.5)
    if zoom:
        y0, y1, x0, x1 = zoom
        ax.set_ylim(y1, y0); ax.set_xlim(x0, x1)
    ax.set_title(title, fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out

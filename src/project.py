"""
Step 8 — choosing the display plane.

This module was reserved for the owner until 2026-07-28. It is not any more —
every file is collaborative now. What the lockout was protecting survived it:
this is where the physics lives, so a change here explains the mechanism
alongside the diff and names what would falsify it. See CLAUDE.md, "Learning
contract".

Background
----------
Vertical is always one display axis, because gravity is what makes the
movement work. PCA chooses the partner axis.

Take the horizontal displacement over the whole set, form the 2x2
covariance matrix, and take the eigenvector with the larger eigenvalue. That
is the direction of greatest horizontal variance — which for a squat comes
out fore-aft, and for a lateral raise comes out mediolateral, with no change
of code and no knowledge of which lift is being performed.

This is why the variance approach beats deriving heading from wrist
attitude: attitude needs a per-lift constant relating wrist normal to body
heading, which means a lookup table to extend for every new exercise and
which breaks on unusual grips. PCA does not use a taxonomy, so there is
nothing to enumerate and nothing to get wrong.

Accuracy needed is low. If the estimated axis is off by an angle phi, the
displayed fore-aft excursion is scaled by cos(phi). At 20 degrees that is
still 94% of the signal. So the problem is not "estimate heading precisely",
it is "do not be badly wrong".

The failure mode is self-limiting. Variance methods break when the two
eigenvalues are similar and the principal axis becomes meaningless — which
here happens when horizontal excursion is tiny. But if excursion is 1 cm the
rendered path is a near-vertical line whichever axis you chose, so the case
where the estimator fails is the case where the answer does not matter.

Still gate on it, because stretching noise 4x is how you invent faults that
a lifter will then try to correct.


State — what is implemented, and the one thing that is not
----------------------------------------------------------

principal_axis(paths) -> (unit_vector, eigenvalue_ratio, excursion)
    2x2 covariance of horizontal displacement across all reps in the set.

    It used np.linalg.eig on a symmetric matrix until 2026-07-30. eig does not
    know the matrix is symmetric, so it returned complex dtypes with a zero
    imaginary part and gave no ordering guarantee — which is why pipeline.py
    and metrics.py had to wrap results in np.real to use them. That is eigh's
    job and it now does it; the np.real calls are workarounds for a line that
    no longer exists.

    THE SIGN IS STILL NOT RESOLVED, and this is the honest state of B4.
    Eigenvectors carry an arbitrary sign, so this returns the axis but not
    which end is forward, and nothing downstream fixes it — so the rendered
    path can silently mirror, which is worse than no path at all.

    The fix this docstring used to propose — take the sign from wrist attitude
    at the calibration pause — has NOT been implemented, and A3 is why. It
    yields one sign per set, and `metrics.vs_truth` reports that 4 of 6, 2 of 6
    and 1 of 3 reps on the three deadlifts individually prefer the OTHER sign
    from the one their own set was given. A per-set answer cannot be right for
    a set whose reps point different ways, however that answer is derived, so
    implementing it would have replaced an unresolved sign with a confidently
    wrong one. What has to happen first is P2/P3: the reconstruction has to
    agree with itself about fore-aft before there is a direction to name.
    `confidence` below is what this module does about it in the meantime, and
    all it can do is decline to magnify.

project_to_plane(paths, axis) -> list of (M, 2) arrays
    Columns: (along-axis, vertical). A pure linear map and nothing else — no
    alignment, no scaling, no sign correction. Start alignment is inherited
    from step 7, which translates every rep to the origin, and re-doing it here
    would hide a step-7 regression rather than fix one.

confidence(ratio, excursion, n_reps) -> bool
    Whether the display axis is identifiable enough to earn plot.py's 4x
    horizontal stretch. Read its docstring before quoting it: it is a NECESSARY
    condition and not a sufficient one, and the difference is most of P2.


Deferred, deliberately
----------------------
The axis is estimated per set, so it can wobble a few degrees between sets
of the same exercise. That is fine within a session and only matters when
comparing across time. Locking a per-exercise axis by averaging over past
sets is a later step, not a now step.
"""

from __future__ import annotations

import numpy as np

# The angle the module docstring calls acceptable: cos(20 deg) = 0.94, so an
# axis 20 degrees out still renders 94% of the fore-aft excursion. Everything
# in `min_ratio` is this number pushed back through the estimator.
AXIS_TOLERANCE_DEG = 20.0

# Measured floors and ceilings on the set's horizontal excursion. Both are in
# metres and both come from real captures — see `confidence` for the evidence
# and for what would move them.
EXCURSION_MIN_M = 0.05
EXCURSION_MAX_M = 0.20


def principal_axis(paths: list[np.ndarray]):
    """Direction of greatest horizontal variance over the whole set.

    Returns (unit axis in world xy, eigenvalue ratio, peak-to-peak excursion
    along that axis in metres). The ratio is >= 1 by construction; it is the
    conditioning of the estimate, and `confidence` turns it into a verdict.

    `paths` is a list of (M_i, 3) rep arrays — step 7's output. They are
    concatenated, so the excursion spans BETWEEN-rep divergence as well as
    within-rep travel. That is deliberate (divergence is the product) but it
    means this number is not comparable with a per-rep excursion: on the three
    deadlifts the video's per-rep fore-aft travel is 8.4-12.8 cm and its
    whole-set figure, computed exactly the way this function computes its own,
    is 9.9-18.4 cm.

    eigh, not eig: the covariance is symmetric by construction, and eigh
    returns real eigenvalues in ascending order for that case. eig returns a
    complex dtype with a zero imaginary part and no ordering, which is what the
    np.real calls scattered around this codebase were compensating for.
    """
    xy = np.concatenate(paths)[:, :2]      # all reps, horizontal only
    covariance = np.atleast_2d(np.cov(xy, rowvar=False))

    eigenvalues, eigenvectors = np.linalg.eigh(covariance)   # ascending
    axis = eigenvectors[:, -1]

    # A degenerate covariance (a set that never moved horizontally) has a zero
    # smaller eigenvalue. inf is the right ratio there and it is also the
    # honest one: nothing constrains the axis at all. It reaches `confidence`
    # as a pass on ratio and a fail on excursion, which is the correct verdict
    # for the correct reason.
    smaller = float(eigenvalues[0])
    ratio = float(eigenvalues[-1] / smaller) if smaller > 0 else np.inf

    projection = xy @ axis
    excursion = float(projection.max() - projection.min())

    return axis, ratio, excursion


def project_to_plane(paths: list[np.ndarray], axis: np.ndarray) -> list[np.ndarray]:
    """Each (M, 3) rep onto the display plane: columns (along-axis, vertical).

    The axis is normalised first. A non-unit axis would silently rescale the
    horizontal channel, and a scale error on the axis the 1 cm spec is about is
    exactly the kind of invisible defect this project keeps rediscovering.

    No alignment happens here. Step 7 translates every rep to the origin, so
    a start-aligned input gives a start-aligned output — a linear map cannot do
    otherwise — and re-subtracting the first sample here would mask a step-7
    regression instead of letting it show.
    """
    axis = np.asarray(axis, dtype=float)[:2]
    norm = float(np.linalg.norm(axis))
    if norm == 0.0:
        raise ValueError("axis is the zero vector; there is no plane to project onto")
    axis = axis / norm

    return [np.column_stack([np.asarray(p, dtype=float)[:, :2] @ axis,
                             np.asarray(p, dtype=float)[:, 2]])
            for p in paths]


def min_ratio(n_reps: int) -> float:
    """Smallest eigenvalue ratio that pins the axis to AXIS_TOLERANCE_DEG.

    The mechanism, because it is the whole argument for the threshold. For a
    2x2 sample covariance the principal eigenvector's angular error has
    asymptotic standard deviation

        sigma_phi = sqrt(lambda1 * lambda2) / (lambda1 - lambda2) / sqrt(N)
                  = sqrt(r) / ((r - 1) * sqrt(N))          [radians]

    (Anderson 1963). It says what the docstring above says qualitatively: as
    the eigenvalues approach each other the axis stops being determined. Set
    sigma_phi to 20 degrees and solve for r.

    **N is the judgement in this, and it is not the sample count.** The samples
    inside one rep are one smooth excursion traced at 100 Hz, not hundreds of
    independent draws; what the set contains that is genuinely repeated is
    REPS. So N = n_reps. That is conservative, and measurably so: bootstrapping
    the axis over reps on all 16 multi-rep captures in data/raw gives an
    observed angular spread 2-4x SMALLER than this formula predicts on most of
    them. Being conservative is the right direction for a gate that authorises
    a 4x magnification, and the conservatism is the reason it is stated rather
    than tuned away.

    What falsifies it: the same bootstrap. If the observed spread ever comes
    out LARGER than the prediction across captures, N = n_reps is too generous
    and this is licensing a stretch it should not. `tests/test_projection.py`
    runs that comparison on real captures for exactly that reason — and note it
    already fails on two of sixteen, both of which have an independently known
    defect, so the check is a distribution statement and not a per-capture one.

    Concretely: 10.1 at 1 rep, 5.9 at 2, 4.5 at 3, 3.8 at 4, 3.3 at 5, 3.0 at 6.
    The module docstring's original "about 3" was right for a six-rep set.
    """
    if n_reps < 1:
        raise ValueError(f"n_reps must be at least 1, got {n_reps}")
    k = np.deg2rad(AXIS_TOLERANCE_DEG) * np.sqrt(n_reps)
    root = (1.0 + np.sqrt(1.0 + 4.0 * k * k)) / (2.0 * k)     # sqrt(r)
    return float(root * root)


def confidence_reasons(ratio: float, excursion: float,
                       n_reps: int = 4) -> list[str]:
    """Why this set does not earn the stretch. Empty means it does.

    `confidence` is the bool; this is the same three tests with their evidence
    attached, so `pipeline.summary` can print a reason instead of a verdict.
    """
    reasons = []
    want = min_ratio(n_reps)
    if ratio < want:
        reasons.append(
            f"axis ratio {ratio:.1f} below {want:.1f} needed at {n_reps} rep(s) "
            f"for a {AXIS_TOLERANCE_DEG:.0f} deg axis")
    if excursion < EXCURSION_MIN_M:
        reasons.append(
            f"excursion {excursion*100:.1f} cm is inside the pipeline's own "
            f"horizontal error ({EXCURSION_MIN_M*100:.0f} cm)")
    if excursion > EXCURSION_MAX_M:
        reasons.append(
            f"excursion {excursion*100:.1f} cm exceeds the {EXCURSION_MAX_M*100:.0f} cm "
            f"any external measurement has recorded — this is drift, not the bar")
    return reasons


def confidence(ratio: float, excursion: float, n_reps: int = 4) -> bool:
    """Is the display axis identifiable enough to stretch 4x? Necessary, not sufficient.

    Read that second clause first. This function answers ONE question — is the
    principal axis determined, and is the excursion it found the size of a
    barbell's travel — and it is blind to whether the path along that axis is
    right. P2 measures 5.05, 9.19 and 15.44 cm rms of horizontal error against
    video on the three deadlifts, and neither a ratio nor an excursion can see
    any of it: an error at rep frequency (P3) lands in the covariance as
    variance and makes the ratio look BETTER. So `confident=True` licenses the
    stretch and says nothing whatever about accuracy. There is no function of
    these two numbers that could say more, which is why plot.plot_scorecard
    labels the unverifiable lifts in words rather than trusting this flag.

    The three tests, and where each number comes from.

    **ratio >= min_ratio(n_reps)** — the axis is determined to within 20
    degrees. Derived; see `min_ratio`.

    **excursion >= 5 cm** — below this the whole excursion is inside the
    pipeline's own error bar. 5.05 cm is the smallest per-rep horizontal rms
    error ever measured against video here (deadlift_155x6_1, analysis/19); the
    other two deadlifts are 9.19 and 15.44. Comparing a set peak-to-peak
    against a per-rep rms is generous by roughly a factor of 2-3, so this is a
    floor and not a signal-to-error criterion. Falsified by any capture that
    measures a smaller horizontal error, which would lower it, or by bench and
    squat acquiring truth and measuring a larger one, which would raise it for
    them. Both are the same experiment: horizontal ground truth on a lift that
    has none.

    **excursion <= 20 cm** — above this the excursion is integration drift
    rather than bar travel. This one is an addition to what the module
    docstring originally specified, and it is the gate with teeth. Measured on
    the same quantity `principal_axis` returns: the video's whole-set fore-aft
    excursion on the three deadlifts is 18.4, 15.4 and 9.9 cm, against
    reconstructions of 18.3, 35.9 and 30.0 — the pipeline over-reads two of
    three by 2.3x and 3.0x. 20 cm is the largest of those measurements plus a
    small allowance.

    PROVISIONAL, and specifically so: 18.4 cm is one lifter, one lift, three
    sets, and deadlift is only ASSUMED to be the lift with the largest fore-aft
    travel. Applying it to bench and squat is an extrapolation with nothing
    behind it. It is stated as a ceiling anyway because it only ever refuses,
    and because on data/raw it refuses exactly the four captures that are
    independently known to be wrong: two deadlifts that over-read the video by
    2-3x, `bench_spoto_90x5_1` whose sixth window is a re-rack (P1), and
    `squat_160x1` whose single window fails the ROM bound (P1). A gate whose
    rejections all coincide with known defects is doing something real. It
    moves the moment any other lift gets horizontal ground truth.
    """
    return not confidence_reasons(ratio, excursion, n_reps)

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

**THAT ARGUMENT LOST, AND `anatomical_axis` IS WHAT REPLACED IT (H9,
2026-08-16).** Its premise was that the variance axis is the fore-aft axis, and
it is not: H2 measured this module's choice sitting **4 degrees from the axis of
the INVENTED parabola** and **11 of 13 captures outside the 20-degree tolerance
declared below**, on all three lifts. The objection to attitude survives in
weakened form and is answered rather than ignored — `anatomical_axis` needs ONE
constant (`BAR_ANGLE_DEG`), not a per-exercise table, because the geometry it
encodes is "a hand is clamped to a bar" rather than anything about a lift. An
unusual grip does still move it, and that is named as the thing that falsifies
it.

**The paragraph below about the failure mode being self-limiting is also
false**, and it is the more expensive of the two errors. "The case where the
estimator fails is the case where the answer does not matter" assumes failure
looks like two similar eigenvalues. The observed failure is the opposite: the
drift is smooth and common-mode, so it produces a LARGE, superbly conditioned
eigenvalue that every rep agrees on — bootstrap spread of 1-10 degrees on an
axis up to 84 degrees wrong, and a ratio uncorrelated with the error
(Spearman +0.03). The estimator fails hardest exactly where the excursion is
largest and the ratio highest. See TASKS.md H2 and `analysis/60`.

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
from scipy.spatial.transform import Rotation

# The angle the module docstring calls acceptable: cos(20 deg) = 0.94, so an
# axis 20 degrees out still renders 94% of the fore-aft excursion. Everything
# in `min_ratio` is this number pushed back through the estimator.
AXIS_TOLERANCE_DEG = 20.0

# Measured floors and ceilings on the set's horizontal excursion. Both are in
# metres and both come from real captures — see `confidence` for the evidence
# and for what would move them.
EXCURSION_MIN_M = 0.05
EXCURSION_MAX_M = 0.20


# The angle of the bar around the wrist, in the plane perpendicular to the
# forearm, measured from the watch's SCREEN NORMAL (+z, out through the
# display). H9, 2026-08-16.
#
# **Why one angle is the whole parameter.** The hand is clamped to the bar, so
# the watch's orientation relative to the bar is fixed by the GRIP. Fore-aft is
# perpendicular to the bar and horizontal, so once the forearm's direction is
# known from the attitude — which it is, and well: attitude is the
# best-conditioned quantity in this system and is never double-integrated — the
# only thing left to know is where the bar sits AROUND the wrist. That is one
# number, and it is a constant of the grip rather than something to estimate per
# capture.
#
# **Why near the screen normal.** The bar runs across the wrist, so fore-aft —
# perpendicular to it — points roughly along the display's normal. The
# measurement puts it 20-26 degrees off that, toward +y.
#
# **WHICH WAY the display faces depends on the GRIP, and the AXIS does not.**
# The owner deadlifts with a MIXED grip, left hand supinated, and wears the
# watch on the left wrist — so on a deadlift the screen faces TOWARD them, and
# on a bench (pronated) it faces away. That is visible in the data and is not
# inferred: the mean world-horizontal screen normal projected on the display
# axis is **-0.91 on all six deadlifts and +0.92 on all four benches**.
#
# A supination is a ~180 degree rotation about the forearm, and 180 degrees is
# INVISIBLE to an axis. That is why this constant survives the difference, and
# it is corroborated rather than assumed: the six MIXED-grip deadlifts put the
# optimum at 20 degrees and the four PRONATED benches at 26, six degrees apart.
# Had the flip been materially off 180 the two would have disagreed by that
# much, so the 6 degrees also bounds how close to 180 it is.
#
# HOW THIS WAS OBTAINED, because it is a fitted constant and must be read as one.
# Swept over the six deadlifts against the video, the best single value is 20
# degrees (median horizontal 2.20 cm). **The four BENCH captures put it at 26
# degrees independently**, having been used to fit nothing here — and
# `correct.WRIST_OFFSET_M` already records that bench and deadlift share the
# same tape-measured `d`, so two lifts and two routes agree on one geometry to 6
# degrees. 23 is the midpoint and is what ships.
#
# **The basin is 20 degrees wide** (11-31 within 0.5 cm of the optimum), which
# is why this is a shipped constant and not a tape measure. `d` was the opposite
# case: B2 found no interior optimum at all and it had to be measured with a
# ruler.
#
# What it costs, measured on all thirteen scoreable captures. Deadlift median
# horizontal 4.97 -> 3.15 cm on its own and 4.97 -> 2.22 with `correct.
# fit_drift_tilt`; squat 2.65 -> 1.68; bench 2.01 -> 2.03, unchanged, and its
# `beats_null` count goes 3 of 4 to 4 of 4. **It was NOT separately optimised on
# squat** — 23 degrees is a deadlift-and-bench number that squat happens to like,
# and a squat sweep is the obvious next measurement.
#
# WHAT WOULD FALSIFY IT, corrected 2026-08-16 after the owner supplied the grip.
#
# *This block used to say a mixed grip "moves this angle by something of order
# 90 degrees". That was wrong twice: a supination is ~180 degrees, which an axis
# cannot see, and **the deadlift captures this constant was fitted on were
# ALREADY mixed grip** — so the case named as the threat was the case in the
# data. The correction makes the constant more robust, not less.*
#
# What would actually move it is a grip that turns the wrist by something OTHER
# than 180 degrees relative to the bar: a false grip, a thumbless bench, a much
# wider or narrower hand position, or a hook grip held differently. Those change
# where the bar sits around the wrist rather than which side of it the watch is
# on, and only the former is an axis.
#
# Still one lifter and one watch. And note what this constant does NOT fix: the
# SIGN. See `anatomical_axis` and B4.
BAR_ANGLE_DEG = 23.0

# Which anatomical direction the body-frame fore-aft vector points, per lift.
# +1 means it points ANTERIOR (the way the lifter faces); -1 means POSTERIOR.
# This is B4 — the sign — and it is closed for the two UPRIGHT lifts and left
# as a convention for bench. 2026-08-16.
#
# THE DERIVATION, which is what makes this geometry rather than a fitted sign.
#
# 1. `vtrack.track` sets `fore_aft_m = (cx - median(cx)) * scale`, so **+video_x
#    is IMAGE-RIGHT**.
# 2. For an UPRIGHT lifter, image-right is `D x U` where `D` is the camera's
#    view direction and `U` is up. A camera on the lifter's LEFT looks along
#    `D = F x U`, giving image-right `= -F`, the POSTERIOR. A camera on the
#    RIGHT gives `+F`, ANTERIOR. `tracked.CAMERA_SIDE` records deadlift left,
#    bench and squat right — the owner's note, not inferred from footage.
# 3. So the video supplies an ANATOMICAL reference the reconstruction never
#    touches, and the screen normal can be checked against it.
#
# MEASURED, and consistent within every lift on all 13 scoreable captures. The
# mean world-horizontal screen normal dotted with the direction that correlates
# positively with +video_x:
#
#     deadlift  +0.06 .. +0.92    so the screen points POSTERIOR   -> -1
#     squat     +0.45 .. +0.97    so the screen points ANTERIOR    -> +1
#     bench     -1.00 .. -0.38    consistent, but see below        -> -1
#
# **Deadlift corroborates the owner independently.** They grip MIXED with the
# left hand supinated and wear the watch on the left, so the screen faces toward
# them — posterior. The camera-side derivation says the same thing without using
# that fact, which is why this is a check rather than a restatement.
#
# **BENCH IS A CONVENTION, NOT A DERIVATION, and the difference is recorded
# because it is the kind of thing that gets forgotten.** Step 2 assumes an
# UPRIGHT lifter. A bench presser is SUPINE: their anterior points at the
# ceiling, and the horizontal axis is head-to-toe, which the camera-side
# argument says nothing about. The bench entry is the empirical relation (4 of
# 4, consistent) with an arbitrary anatomical label. It gives a stable
# orientation, which is what the display needs; it does not give a derived one.
#
# WHAT WOULD FALSIFY IT. Turning the watch to the other wrist, or a grip that
# rotates the wrist relative to the bar — for deadlift that means dropping the
# mixed grip, since a double-overhand pull supinates neither hand and would flip
# this entry. The owner confirmed the mixed grip is stable across sets
# (2026-08-16); if that changes, this table changes with it. Filming a lift from
# the OTHER side is the cheap experiment that would test the whole chain: every
# sign here should invert and `sign_agrees_with_geometry` should stay true.
FORE_AFT_SENSE = {"deadlift": -1.0, "squat": +1.0, "bench": -1.0}


def anatomical_axis(quat: np.ndarray, bounds: list[tuple[int, int]],
                    angle_deg: float = BAR_ANGLE_DEG,
                    lift: str | None = None) -> np.ndarray:
    """The display axis from ATTITUDE alone, DIRECTED when the lift is known.

    Returns a unit vector in world xy, like `principal_axis`'s first element,
    and takes no position at all — which is the entire point. **The variance
    axis cannot be trusted because the variance is the drift**: H2 measured
    step 8's axis sitting 4 degrees from the axis of the invented parabola
    alone, with 11 of 13 captures outside the 20-degree tolerance this module
    declares for itself, on all three lifts. This axis is computed from a
    quantity the drift cannot reach.

    The construction. `angle_deg` fixes the fore-aft direction in WATCH
    coordinates (see `BAR_ANGLE_DEG`); rotate it into the world at every sample
    inside a rep, drop the vertical component, and take the dominant direction
    of what is left. Dropping the vertical rather than assuming it is zero
    matters on squat, where the forearm is nowhere near vertical.

    **Read `BAR_ANGLE_DEG` before using this on a new lift or grip.** The angle
    is a property of how the hand holds the bar, and this function is only as
    good as that constant.

    **THE SIGN IS RESOLVED WHEN `lift` IS GIVEN. B4 is closed (2026-08-16),
    open since 2026-07-30.** With `lift=None` this returns an undirected axis and
    behaves as it did before, which is what a caller with an unknown lift should
    get.

    Two things had to become true, and both are measurements rather than
    arguments. **First, the reconstruction had to agree with itself.** This
    module refused a per-set sign because reps WITHIN a set disagreed about
    forward — 4 of 6, 2 of 6 and 1 of 3 on the three deadlifts — so no per-set
    answer could be right however derived. After H8/H9 that is **6 of 61 reps**,
    five of them inside the two captures already known bad. **Second, an
    anatomical reference had to exist that the reconstruction does not touch**,
    and `tracked.CAMERA_SIDE` plus `vtrack`'s image-right convention is one. See
    `FORE_AFT_SENSE` for the derivation and for what is derived versus assumed.

    The sign is taken from the MEAN of the world-projected body vector, not from
    the eigenvector: `numpy.linalg.eigh` fixes eigenvector signs by its own
    convention, and a display orientation resting on a LAPACK detail would be a
    silent mirror waiting to happen — which is exactly what B4 was.

    **But B4's stated blocker has largely dissolved, and that is worth knowing
    before anyone re-reads the refusal above.** This module declined a per-set
    sign because reps WITHIN a set disagreed about which way is forward — 4 of 6,
    2 of 6 and 1 of 3 on the three deadlifts it was measured on — so no per-set
    answer could be right however it was derived. Re-measured after H8/H9 that
    is **6 of 61 reps**, with five of the six inside the two captures already
    known bad (`deadlift_170x4_3`, whose clock fits 22.8% drift, and
    `bench_spoto_95x5_2`). Four of six deadlifts disagree on nothing.

    What is still missing is not self-consistency but a CONVENTION: which end of
    the axis is "toward the lifter". The watch knows its wrist, and the owner's
    grip is known (mixed, left supinated, so the screen faces the lifter on a
    deadlift and away on a bench) — and the sign of the screen normal along this
    axis predicts the sign `vs_truth` chose on 5 of 6 deadlifts and 3 of 3
    squats. It is not smuggled in here because it needs a grip input the API
    does not have and an anatomical convention checked against `camera_side`,
    both of which are changes of their own.
    """
    quat = np.asarray(quat, dtype=float)
    inside = np.zeros(len(quat), dtype=bool)
    for start, stop in bounds:
        inside[start:stop] = True
    if not inside.any():
        raise ValueError("anatomical_axis needs at least one rep window")

    phi = np.deg2rad(angle_deg)
    body = np.array([0.0, np.sin(phi), np.cos(phi)])

    R = Rotation.from_quat(quat[inside], scalar_first=True)
    world = R.apply(np.tile(body, (int(inside.sum()), 1)))[:, :2]

    norms = np.linalg.norm(world, axis=1, keepdims=True)
    keep = norms[:, 0] > 1e-9
    if not keep.any():
        raise ValueError(
            "anatomical_axis: the bar direction is vertical throughout, so it "
            "has no horizontal projection to take an axis from")
    world = world[keep] / norms[keep]

    # Dominant AXIS rather than mean direction, because averaging signed vectors
    # would let two halves of a set cancel if the wrist turned through 180.
    eigenvalues, eigenvectors = np.linalg.eigh(world.T @ world / len(world))
    axis = eigenvectors[:, -1]

    # ...then ORIENT it from the mean, which eigh cannot supply. `world` is the
    # fore-aft direction in watch coordinates rotated out to the world, so its
    # mean already points somewhere anatomically meaningful; the eigenvector
    # only supplies a well-conditioned line for it to snap to.
    mean = world.mean(axis=0)
    if float(mean @ axis) < 0.0:
        axis = -axis

    if lift is None:
        return axis
    try:
        return FORE_AFT_SENSE[lift] * axis
    except KeyError:
        raise ValueError(
            f"no fore-aft sense recorded for lift {lift!r}; add it to "
            f"FORE_AFT_SENSE with its derivation, or pass lift=None to get an "
            f"undirected axis") from None


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

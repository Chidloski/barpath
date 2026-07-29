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


State — what is implemented and what is not
------------------------------------------

principal_axis(paths) -> (unit_vector, eigenvalue_ratio, excursion)
    Implemented. 2x2 covariance of horizontal displacement across all reps in
    the set.

    Two known defects, both tracked as B4 in TASKS.md:

    It uses np.linalg.eig on a symmetric matrix where eigh is correct. eig
    does not know the matrix is symmetric, so it returns complex dtypes with
    zero imaginary part and gives no ordering guarantee. That is why
    pipeline.py has to wrap the ratio and excursion in np.real to print them —
    a workaround for this line, not a property of the quantity.

    THE SIGN IS NOT RESOLVED. Eigenvectors carry an arbitrary sign, so this
    returns the axis but not which end is forward, and nothing downstream fixes
    it — so the rendered path can silently mirror, which is worse than no path
    at all. The intended fix, unimplemented: take the sign from wrist attitude
    at the calibration pause, where the watch's screen-normal rotated into the
    world frame is a directed vector that only has to be right to within 90
    degrees.

project_to_plane(paths, axis) -> list of (M, 2) arrays
    NOT IMPLEMENTED — B4. Columns: (along-axis, vertical).

confidence(ratio, excursion) -> bool
    NOT IMPLEMENTED — B4. Low confidence below a ratio of about 3, or
    excursion under about 2 cm. Low-confidence sets are drawn without the
    horizontal stretch.


Deferred, deliberately
----------------------
The axis is estimated per set, so it can wobble a few degrees between sets
of the same exercise. That is fine within a session and only matters when
comparing across time. Locking a per-exercise axis by averaging over past
sets is a later step, not a now step.
"""

from __future__ import annotations

import numpy as np

# find the vector with the most variance via the max eigenvalue in the xy plane
def principal_axis(paths: list[np.ndarray]):
    all_reps_xy = np.concatenate(paths)[:, :2] # combines all reps, and slices off the z coordinate
    covariance = np.cov(all_reps_xy, rowvar=False)

    eigenvalues, eigenvectors = np.linalg.eig(covariance)

    projection = all_reps_xy @ eigenvectors[:, eigenvalues.argmax()]
    excursion = projection.max() - projection.min()

    return eigenvectors[:, eigenvalues.argmax()], (eigenvalues.max() / eigenvalues.min()), excursion


def project_to_plane(paths: list[np.ndarray], axis: np.ndarray):
    raise NotImplementedError("step 8 — see TASKS.md B4 and this module's docstring")


def confidence(ratio: float, excursion: float) -> bool:
    raise NotImplementedError("step 8 — see TASKS.md B4 and this module's docstring")

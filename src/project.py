"""
Step 8 — choosing the display plane.

=========================================================================
RESERVED MODULE. The owner writes this. Claude Code reviews and explains,
but does not implement. See CLAUDE.md.
=========================================================================

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


What to implement
-----------------

principal_axis(paths) -> (unit_vector, eigenvalue_ratio, excursion)
    2x2 covariance of horizontal displacement across all reps in the set.

    Eigenvectors carry an arbitrary sign, so this gives the axis but not
    which end is forward, and a mirrored path is worse than none. Resolve
    the sign from wrist attitude at the calibration pause: the watch's
    screen-normal rotated into the world frame is a directed vector, and it
    only needs to be right to within 90 degrees.

project_to_plane(paths, axis) -> list of (M, 2) arrays
    Columns: (along-axis, vertical).

confidence(ratio, excursion) -> bool
    Low confidence below a ratio of about 3, or excursion under about 2 cm.
    Low-confidence sets are drawn without the horizontal stretch.


Deferred, deliberately
----------------------
The axis is estimated per set, so it can wobble a few degrees between sets
of the same exercise. That is fine within a session and only matters when
comparing across time. Locking a per-exercise axis by averaging over past
sets is a later step, not a now step.
"""

from __future__ import annotations

import numpy as np


def principal_axis(paths: list[np.ndarray]):
    raise NotImplementedError("Reserved module — see docstring.")


def project_to_plane(paths: list[np.ndarray], axis: np.ndarray):
    raise NotImplementedError("Reserved module — see docstring.")


def confidence(ratio: float, excursion: float) -> bool:
    raise NotImplementedError("Reserved module — see docstring.")

# Tasks

**What is open right now, and nothing else.** Working state of the pipeline
rebuild started 2026-07-28, after milestones 1–6 all passed on synthetic data
while the pipeline failed in the gym by two orders of magnitude.

Deliberately not here:

- `CLAUDE.md` — the protocols. Read it first; it is binding.
- `FINDINGS.md` — what works and what does not, one entry per mechanism, and
  the problems P1–P6. **An item below that cites a problem is pointing there.**
- `analysis/README.md` — the measurements and plots behind each finding.
- `src/README.md` — the video referee in depth.

*Cut back on 2026-08-22, when this file held 57 completed task entries alongside
the open ones. Those entries and the old To-do list were retired with the
chronological record on 2026-08-23; `git show fa7588d:FINDINGS.md` has them, and
what they established is in `FINDINGS.md` as verdicts.*

---

## Red in the suite

**Three captures miscount.** Was five until 2026-08-23, when
`segment._readmit` fixed two on the branch `h34-segment-readmit` — **not yet on
main, awaiting the owner**. The rows below are the state ON MAIN; with the
branch applied, `squat_140x4_1` and `squat_pause_140x4_1` count 4/4. Left RED rather than registered in `WRONG_REP_COUNT`, per
F1's precedent: they are the finding, and burying them under an expected-failure
mark is how the previous ones stayed invisible.

| capture | windows | labelled | shape |
|---|---|---|---|
| `deadlift_210x1_20260815` | 2 | 1 | a spurious PAIR outvotes the real single |
| `squat_170x1_20260820` | 2 | 1 | same — and its real rep scores upright 0.63 against 8.3–23.4 corpus-wide, which has no explanation |
| `squat_140x4_1_20260813` | 3 | 4 | `_similar_cluster` discards a rep it identified — **fixed on the branch** |
| `squat_140x4_2_20260813` | 2 | 4 | same, two of them; the branch abstains, its cluster holding only 2 members |
| `squat_pause_140x4_1_20260820` | 3 | 4 | same — **fixed on the branch** |

The video counts the 2026-08-13 and 2026-08-15 cases correctly, so the labels
are right and the segmenter is wrong.

**The "long cadence gap" shape in the table above is FALSIFIED (2026-08-23).**
The most irregular cadence in the corpus belongs to a capture that counts
correctly, and every failure is *less* irregular than something that passes. The
real mechanisms are two, both in `_similar_cluster`: it discards reps its own
fourth discriminator separates by 10×, and on a single a spurious mutually-
similar PAIR outvotes the real rep before the singleton rule is consulted. See
`FINDINGS.md` P1 and `analysis/82`.

**`deadlift_170x4_3_20260808` rep 4 spans 67.5 cm against a 40–61 band** while
counting 4/4 — extent wrong without a miscount. It is a reconstruction defect
surfacing in a segmentation gate, the mechanism is not established, and it is
the last entry in `KNOWN_ROM_FAILURES`.

## Defects recorded and not fixed

- **Two 2026-08-13 spoto benches do not track** — 94.1 and 72.2 cm of whole-clip
  travel on a bench press. A footage problem, not a code one. `vtrack.IMPLAUSIBLE_MULT`
  is the two-sided flag that now catches them (H16).
- **`deadlift_170x4_3` is scored through a 22.8% clock drift** — a
  landing-to-impact fit with slope 0.7715 and a 216 ms residual — and **nothing
  gates on `drift_pct` or `rms_ms`.** Found by G3.
- **`capture.sync` and `metrics.bench_sync` return `fit["offset"]` with opposite
  signs.** Safe as long as nobody compares them, silently wrong the moment
  somebody does. Found by G3.
- **`capture.fore_aft_flags` has no caller anywhere** — not in `src/`, not in
  `run.py`, not in a test. So `FORE_AFT_ACCEL_MAX` is never evaluated against
  anything: a bound nothing checks is not a gate. The function is sound, it is
  simply not wired up. Wiring it in would start flagging reps, which is a
  decision rather than a tidy-up. Found by H28.
- **`capture.find_plate`, `sticker_plate_diameter` and `STICKER_PLATE_DIAMETER_M`
  have had no caller since `markers.py` was deleted** (H21). Recorded as
  orphaned rather than removed, since nothing can score with them.
- **P1 says squat's phase is unverified; G2 says the bottom dwell verifies it.**
  `metrics.pause_landmark` agrees with the IMU to 0.003–0.083 of a rep on all
  seven multi-rep bench and squat captures, which reads like the anchor P1 says
  squat lacks. One of the two is stale. **Reconcile before quoting either.**

## Decisions for the owner

- **Should `deadlift_160x6_1_20260818` be excluded from scoring IN CODE?** It is
  the only strapped capture in the corpus, the watch moved, and it should
  referee nothing. Excluding it changes what every corpus-wide median means, so
  it is a decision and not a tidy-up. Until it is taken, exclude it by hand and
  say so. See H20 and the *Reading a number* section of `CLAUDE.md`.
- **Wire `capture.fore_aft_flags` in, or delete it?** See above.

## Measurement debt

- **Nothing has been re-measured on 36 captures.** Every corpus-wide median in
  these docs — H17's scorecard included — is the 29-capture figure from
  2026-08-17. Five captures arrived on 2026-08-20 and all five track at 100%
  coverage; two are among the best-conditioned in the project.
- **C28b and C29 have never been re-run with step 6 applied.** Every number in
  P6 was measured with `d` off, and `d` is the term that recovers most of the
  deadlift horizontal *acceleration* channel. Do the two compose, or correct the
  same thing twice? `analysis/C31b_STATE.md` item B; the highest-priority open
  item there.
- **`bench_spoto_95x5_1` is the capture to explain.** It loses to the flat-line
  null and reproduced the old referee to 0.01 when its session-mate crossed —
  so half of P2's referee-versus-pause tension was a referee artefact and half
  is real. This is the real half.
- **`deadlift_190x3_20260818` improves under every arm of H27's correction**,
  reaching `beats_null` 1.69, the highest any deadlift has scored here. It is
  also the capture H20 left open as elevated. n = 1, on the one capture that was
  already anomalous. The thing to ask is whether its error really is closer to
  uniform, which would make it a different failure rather than the same one
  inverted.

## Open problems

Stated in full, with their evidence, in `FINDINGS.md`. What is *open* about each:

- **B3 — CLOSED BY MEASUREMENT, 2026-08-23, and not in the direction expected.**
  The premise is confirmed and stronger than recorded: over 111 refereed reps
  the bar misses closing horizontally by a median of **1.61 cm**, only 33% of
  reps close inside the 1 cm spec, and forcing them shut injects ~0.9 cm rms.
  But an **oracle given the true non-closure gains nothing** — +0.15 cm bench,
  +0.33 deadlift, −0.61 squat, −0.18 corpus-wide, better on 50% of reps. There
  is no estimator worth building behind a ceiling of zero. See `FINDINGS.md`
  and `analysis/83`. **What replaced it is sharper (2026-08-23):** the error is
  a BULGE peaking at phase 0.56, the endpoint carries 45% of it, and an oracle
  over polynomial order says a per-rep QUADRATIC would reach 0.71 cm — inside
  spec. On deadlift that bulge scales as a·T²/8 with the implied `a` inside the
  range P6 measured, so the live question is an estimator for a per-set constant
  acceleration offset. H27 built one from the pull anchors and it was too large
  on 9 of 9 by a median 4.6×; the mechanism was right and the estimator was not.
  See `FINDINGS.md` P3 and `analysis/84`.
- **The rest-ZUPT bump correction, ready to build and not built.** H36/H37: the
  rest-to-rest velocity change predicts the mid-rep bump at Pearson +0.59, and
  applied with its calibrated gain of 0.173 takes deadlift 3.10 -> 2.66 cm under
  leave-one-capture-out, against an oracle ceiling of 1.88. The gain is
  understood — it is the least-squares attenuation `r*sd_o/sd_e`, verified as an
  identity — and stable at 0.157-0.218 across held-out captures. **What is not
  settled is whether it should ship**, because it improves the median while
  helping only 48% of reps, and because it introduces a calibrated constant into
  `correct.py`. That is a decision, not a measurement. See `FINDINGS.md` and
  `analysis/86`, `analysis/87`.

- **B6 / P3 / P6 — a deadlift correction that meets all three requirements at
  once.** Local in time (B7, B6, C19 and C28b each failed this); boundaries not
  on the impacts, or step 7 annihilates it (C29); and it must cover every rep
  (the owner's ruling, H23). H24's final cut is the first frame to meet all
  three — and it still reaches only `beats_null` 0.77, worse than drawing no
  fore-aft motion at all, while H24b found it damages the vertical past spec.
  **Nothing is proposed for the pipeline.** Requirement 2 is about where the
  detrend's *boundaries* sit and requirement 3 is about which samples are
  *covered*; nothing says one implies the other, and nobody has tried a frame
  that separates them.
- **D — replace the remaining synthetic tests.** Gates 5 and 6 are deleted; keep
  the algebraic-identity tests and replace the rest with real-data gates.
  Largely done incidentally — worth a pass to confirm nothing behavioural
  survives.

---

## Capture protocol

Not code, and the highest value per effort available. *Completed items and the
reasoning behind them are in `FINDINGS.md`.*

- **NO LIFTING STRAPS. Owner's decision, 2026-08-19, and it is the first rule
  here because it is the only one that has already cost a capture.** Straps put
  the watch further up the forearm and let it move: `deadlift_160x6_1_20260818`
  invents 19.9–27.9 cm of per-rep fore-aft where its own unstrapped twin invents
  5.4–7.7 and the bar really moved 4.4–6.0, reconstructing at 14.91 cm against
  the twin's 1.97. This supersedes H20's own recommendation, which was to
  *record* straps per capture — omitting them is better, because the effect is
  large, invisible in both the IMU log and the video, and a recorded-but-present
  confound still has to be excluded from every corpus median by hand.

- **Two deadlift sets, one each, each testing something no capture in this
  corpus can** (H10/B4). Same session, same grip, same everything else — the
  point is to vary ONE thing.

  1. **A deadlift filmed from the lifter's RIGHT.** Every deadlift here is
     filmed from the LEFT, so `tracked.CAMERA_SIDE` is perfectly confounded with
     the lift. **Prediction, written down before the capture: every sign in
     `project.FORE_AFT_SENSE` should invert while `sign_agrees_with_geometry`
     stays TRUE.** *(The equivalent experiment on a SQUAT has since run and the
     prediction FAILED — H15 — so this is now a re-test on the lift the
     derivation was built for, not a first look.)*
  2. **A DOUBLE-OVERHAND deadlift.** The owner grips mixed with the left hand
     supinated and the watch is on the left wrist, so `FORE_AFT_SENSE["deadlift"]`
     is −1. **Prediction: the screen normal flips to point ANTERIOR and that
     entry becomes +1.** If it does not, the sign is not coming from the grip.
     Lighter is fine — this is a geometry capture, not a strength one.

  *Both are worth more than another set at the same angle: what limits the
  deadlift horizontal now is not the pipeline, it is that every corrected number
  sits inside the referee's own 3.0 cm of fore-aft wander at lockout, and that
  the two constants carrying the result — `BAR_ANGLE_DEG` and `FORE_AFT_SENSE` —
  are fitted or derived on a corpus that varies neither camera side nor grip.*

- **Nothing is wanted here for the quadratic detrend.** A set paused partway
  through a rep was proposed on 2026-08-23 and **withdrawn the next day on the
  owner's rule: the capture must never affect the set.** Pausing before and
  after is fine and the protocol already does it. The rule is right on its own
  terms and the proposal was also unnecessary — the deadlift already carries the
  missing constraint, because the bar rests on the floor between reps. See
  `FINDINGS.md` and `analysis/86`.

- **A deadlift DOUBLE.** A deadlift set has no gap between reps, so no
  truncation of a longer set can imitate one; deadlift doubles remain the one
  short-set case unvalidated end to end. Carried from G3.

- **A set whose reps genuinely DIFFER in shape.** `correct.fit_drift_tilt`
  assumes a set's reps should agree and pulls them together when they do not,
  and nothing in this corpus can tell that premise from a correct one. A set
  with a deliberately changing bar path — first reps clean, last reps drifting
  forward — is the only named way to catch step 5b removing real signal.

- **Three still holds at different wrist postures, not two.** Five seconds of
  capture and no code. C28 proved two holds can *never* separate the attitude
  tilt leak from the accelerometer bias: `R_open − R_close = R_open(I − Δ)`, and
  a relative rotation fixes its own axis, so the difference of two rotation
  matrices is rank ≤ 2 exactly. A third posture breaks the degeneracy.

- **A capture with the session running and 30+ s of wrist-down.** C16 put the
  `HKWorkoutSession` back after C7 removed it and lost; what is wanted now is
  the same test *with* the session. If the rate still drops, the session is not
  what keeps Core Motion alive. Check gaps in `dt`, never the sample counter,
  which rises either way. **Every capture taken between C7 and C16 is suspect**
  and any showing wrist-down truncation should be re-taken.

- **Film a bench single, with the watch on.** One was filmed on 2026-08-01 and
  that session produced no IMU log, so it still cannot answer the question.
  C5's singleton rule ranks by concentric displacement and `bench_92.5x2`'s
  unrack moves the bar *further* than its reps, so a bench single is predicted
  to segment onto the unrack. The video says the prediction is plausible — the
  unrack excursion reaches 14 cm fore-aft against a press of a few.

- **Film a plumb line once**, to put a number on lens distortion.

- **Tape the lockout height.** Deadlift bar centre at lockout, once. It would
  turn `VERTICAL_ROM_M`'s deadlift ceiling from a bound into a measurement and
  let the video be calibrated against it rather than flagged by it.

- **Step the camera back**, still worth it for bench: its plate sits against
  clutter and the seed is hand-placed, carrying ~4% on every bench distance that
  nothing checks. *(The deadlift and squat halves of this item were answered by
  stickers rather than by moving the camera — the camera never moved.)*

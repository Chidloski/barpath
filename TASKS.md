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

- **THE SEVEN 2026-08-24/25 CAPTURES ARE TRACKED AND FIVE OF THEM ARE JUNK.**
  Their CSVs are written into `data_v2/tracked/` but **deliberately NOT
  committed**, pending the owner, because a cached read does not run
  `vtrack.validate` — committing a bad track silences its own warning for the
  life of the repo.

  | capture | verdict |
  |---|---|
  | `bench_90x4_20260824` | GOOD — 98.4% coverage, 32.7 cm travel, 4/4 reps |
  | `deadlift_160x6_20260825` | GOOD — 100%, 41.4 cm, 6/6 reps |
  | `bench_pause_105x2_20260824` | flagged — 218.7 cm travel, 59.6% coverage |
  | `deadlift_180x3_20260825` | flagged — travel implausible, 4 reps vs 3 |
  | `squat_ssb_110x4_1_20260824` | flagged — 3 reps vs 4 |
  | `squat_ssb_130x4_3_20260824` | flagged — 36.1 cm travel |
  | `squat_ssb_120x4_2_20260824` | **BAD AND SILENT** — see below |

  **No SSB squat tracks.** That is a loss beyond the three captures: an SSB is a
  different grip, and grip is the live hypothesis for why squat's fore-aft sign
  is unrecoverable, so these were the natural experiment for it.

- **`vtrack.validate` does not gate FORE-AFT excursion, and one capture proves
  it should.** `squat_ssb_120x4_2` passes every check — 100% coverage, 1.58 px
  residual, 4 of 4 reps — with **163.4 cm of whole-clip fore-aft on a squat**.
  It is the D2 failure the `implausible` flag exists to catch, arriving through
  the one quantity nothing looks at.

  **Travel is the wrong thing to tighten**: `implausible` uses `VERTICAL_ROM_M`
  as a FLOOR and must, because whole-clip travel legitimately includes the
  walkout — good squats reach 70.2-81.2 cm against a 45-76 cm rep ROM, so a
  ceiling would fire on `squat_145x4_2`. **Fore-aft separates cleanly where
  travel cannot**: every straight-bar squat in the corpus sits at 42.1-55.1 cm
  (median 51.7), and the two SSB tracks that produced a number are 149.6 and
  163.4 — 2.7x the worst good one, with nothing in the gap. A `FORE_AFT_MAX_M`
  per lift, measured the way `VERTICAL_ROM_M` was, would have caught this.
- **A NEW CAPTURE'S NAME COLLIDES WITH AN OLD ONE'S PREFIX, and a gate now
  scores the wrong capture.** `deadlift_160x6_20260825` (2026-08-25, one set, no
  index) sorts BEFORE `deadlift_160x6_2_20260804` and matches the prefix
  `deadlift_160x6_2`, so `test_the_three_deadlifts_H8_and_H9_were_built_for`
  silently scores the 2026-08-25 capture in place of the 2026-08-04 one it was
  written for, and fails. Found 2026-08-25 (H47).

  The mechanism is `next(p for p in CAPTURES if p.stem.startswith(stem))`, and
  the same `startswith` idiom is used in `WRONG_REP_COUNT`,
  `KNOWN_ROM_FAILURES`, `CAMERA_SIDE_EXCEPTIONS` and the B4 gate's exception
  tuples. **An unindexed capture name is a prefix of every indexed one that
  shares its weight and reps**, so this will happen again. Either index every
  capture (`_1` even when there is only one set) or match on the date-stripped
  stem rather than a prefix.


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

- **SQUAT'S FORE-AFT DIRECTION IS UNRESOLVED, and it is the live question.**
  The shipped constant agrees with the video on 5 of 10 squats — chance — so a
  squat path may render MIRRORED. The five it gets wrong are named in
  `test_the_fore_aft_SIGN_agrees_with_the_video_B4_closed`; deleting that tuple
  is the test that this is solved.

  **WHY NO WRIST CONVENTION CAN WORK, measured 2026-08-25 and the reason to stop
  proposing one.** The azimuth of every watch axis from the lifter's own
  ANTERIOR, as circular consistency R (1 = every set agrees, 0 = scattered):

    | axis | squat | bench |
    |---|---|---|
    | X (crown) | **0.22** | 0.80 |
    | Y (12 o'clock) | **0.26** | 0.77 |
    | Z (screen) | **0.33** | 0.77 |

  The crown's bearing across the ten squats is +4, −1, −26, −56, −73, +17, +84,
  +150, −166, −178 — the whole circle. WITHIN a set it holds to 9–13 degrees, so
  the posture is stable and the owner's description of it is right; it is
  BETWEEN sets that the bearing moves. A hand resting on a bar behind the neck
  does that; a hand gripping a straight bar does not, which is why bench sits at
  0.80.

  **FIVE explanations are ELIMINATED. Do not re-open them.** The crown
  convention (tried, 6 of 10, rejected); camera side (owner-confirmed 2026-08-25
  — every squat from the right except `squat_145x4_2_20260817`); a mirrored clip
  (owner: clips are never flipped); synchronisation (the half-rep lag that lifts
  the horizontal to +0.61…+0.84 takes the VERTICAL from 2–4 cm to 51–86 cm, so
  τ=0 is right); and a stale tracker cache (all thirteen tracked on one commit).

  **What is left.** A capture-time sign calibration — a deliberate known-direction
  move during the opening hold — is the only route that recovers the direction
  without the video. The walkout will NOT serve: pre-rep integration drift is
  9.5–22 m over 25–32 s, burying a ~1 m signal. The SSB squats are the natural
  experiment for whether GRIP is the variable, and they are recoverable once the
  tracker handles 720p.

- **Should `deadlift_160x6_1_20260818` be excluded from scoring IN CODE?**- **Should `deadlift_160x6_1_20260818` be excluded from scoring IN CODE?** It is
  the only strapped capture in the corpus, the watch moved, and it should
  referee nothing. Excluding it changes what every corpus-wide median means, so
  it is a decision and not a tidy-up. Until it is taken, exclude it by hand and
  say so. See H20 and the *Reading a number* section of `CLAUDE.md`.
- **Wire `capture.fore_aft_flags` in, or delete it?** See above.
- **`metrics.vs_truth` still chooses the axis sign by correlating with the
  video**, so no score it reports can penalise a mirrored set — which is half of
  why H44's defect survived so long, the other half being that a near-
  perpendicular axis FLATTENS the curve and rms rewards that. The owner has asked
  for "report both": keep the fitted flip so every existing number stays
  comparable, and report the shipped-sign error and the video in anatomical
  coordinates alongside it. **Not yet built** — `metrics.py` is a `main` module
  and was out of scope for H44's branch. Until it is, the gallery is showing a
  BETTER sign than the pipeline ships, because it draws `curve_pipeline` after
  the flip, and every camera-left capture (all ten deadlifts, plus
  `squat_145x4_2`) is drawn mirrored against every camera-right one.

## Measurement debt

- **Nothing has been re-measured on 36 captures.** Every corpus-wide median in
  these docs — H17's scorecard included — is the 29-capture figure from
  2026-08-17. Five captures arrived on 2026-08-20 and all five track at 100%
  coverage; two are among the best-conditioned in the project.
- **C28b and C29 have never been re-run with step 6 applied.** Every number in
  P6 was measured with `d` off, and `d` is the term that recovers most of the
  deadlift horizontal *acceleration* channel. Do the two compose, or correct the
  same thing twice? This was `analysis/C31b_STATE.md` item B until that file was
  deleted on 2026-08-25; its substance is the two sentences above, and
  `git show c29ec71:analysis/C31b_STATE.md` has the rest.
- **`bench_spoto_95x5_2` is the capture to explain, and this entry named the
  WRONG ONE until 2026-08-26.** Measured through the shipped pipeline, `_1`
  beats the flat-line null at 1.25 and `_2` is the only capture in the corpus
  that does not, at 0.75 on 5.11 cm. H40's quadratic takes `_2` to 1.81 on 2.12
  cm, so it no longer loses — and that is not an explanation: it is still the
  worst bench in the corpus by 40%. The referee half of the old note stands and
  is not reassigned here, because the capture it was written about may be a v1
  name and v1 cannot be re-run: one of the pair reproduced the old referee to
  0.01 when its session-mate crossed, so half of P2's referee-versus-pause
  tension was a referee artefact and half is real. Which capture that was needs
  re-deriving before it is quoted again.
- **The suite's standing baseline is 33 failures, and nothing in these docs said
  so.** Measured 2026-08-26 on `df5607f`: 33 failed, 667 passed, 32 skipped, 1
  xfailed. Several commit messages through H40 report "20 failures, unchanged
  from main", which is stale — quote 33 and re-measure before quoting it again,
  because an unrecorded baseline is how a new failure hides in an old number.
  Nobody has triaged the 33.
- **`README.md`'s layout table has two stale lines**, both older than H43 and
  neither caught by `tests/test_docs.py`. It lists `src/truth.py` as a live
  module — it was deleted at H21 and the gate deliberately exempts the name, so
  a live pointer in a layout table slips through — and it calls step 8 the "PCA
  display axis", which H9 replaced with the attitude-derived axis. Recorded, not
  fixed: neither is what H43 changed.
- **`deadlift_190x3_20260818` improves under every arm of H27's correction**,
  reaching `beats_null` 1.69, the highest any deadlift has scored here. It is
  also the capture H20 left open as elevated. n = 1, on the one capture that was
  already anomalous. The thing to ask is whether its error really is closer to
  uniform, which would make it a different failure rather than the same one
  inverted.

## The binding constraint

**The horizontal spec needs the attitude 2.7x tighter than Core Motion gives.**
Established 2026-08-26 (H42) and it reframes what is left to do. The mid-rep
bump implies a tilt of 0.13 deg median; P5 measured attitude error at a still
hold at 0.05-0.14 deg; 1 cm of bump at a 3.1 s rep needs 0.049 deg. Those are
the same quantity, measured three ways, and the reconstruction is already close
to what the attitude permits.

So the remaining horizontal error is **not a modelling problem**, and no step
downstream of the attitude can remove it. What is still worth doing:

- estimate the per-rep bump where an anchor exists and subtract it. **Done for
  bench and LANDED** (H40/H43, `correct.QUAD_LIFTS`): 1.81 -> 1.30 cm and 7 of 7
  beating the null. Squat is a wash and deadlift is refused, so this route is
  spent unless a better anchor appears;
- anything that improves the ATTITUDE itself, which needs information the watch
  does not have during motion — P4/P5 close the obvious routes;
- and accept that squat and deadlift are anchor-limited, not model-limited.

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
- **The lockout-anchor bump correction on bench is BUILT and LANDED**, and this
  entry is kept only because the numbers it used to carry are quoted elsewhere.
  It shipped as step 7's quadratic term restricted to bench's fore-aft axis
  (`correct.QUAD_LIFTS`), reaching **1.81 -> 1.30 cm** and taking bench from six
  of seven captures beating the flat-line null to seven of seven. The 2.09 ->
  0.98 cm this entry once promised was measured through a harness with an
  intercept and is withdrawn. Squat is a wash and deadlift is refused, so the
  route is spent unless a better anchor turns up. See `analysis/90`.

- **The rest-ZUPT bump correction, ready to build and not built.** H36/H37: the
  rest-to-rest velocity change predicts the mid-rep bump at Pearson +0.59, and
  applied with its calibrated gain of 0.173 takes deadlift 3.10 -> 2.66 cm under
  leave-one-capture-out, against an oracle ceiling of 1.88. The gain is
  understood — it is the least-squares attenuation `r*sd_o/sd_e`, verified as an
  identity — and stable at 0.157-0.218 across held-out captures. **What is not
  settled is whether it should ship**, because it improves the median while
  helping only 48% of reps, and because it introduces a calibrated constant into
  `correct.py`. That is a decision, not a measurement. **And it is near its
  ceiling**: the parabola is only 44% of deadlift's post-closure error, so
  r = 0.594 is close to what the model allows and better estimation will not
  pay. See `FINDINGS.md` and `analysis/86`, `87`, `88`.

- **B6 / P3 / P6 — a deadlift correction that meets all three requirements at
  once.** **Now sized (2026-08-24):** the term B6 is chasing is 56% of
  deadlift's post-closure error energy, concentrated in the k = 3 mode of
  `sin(kπs)` — the signature of something localised, i.e. the landing. Bench
  carries 6% and squat 17% in the same modes, which is why B6 has always been a
  deadlift problem. Local in time (B7, B6, C19 and C28b each failed this); boundaries not
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

- **MARK AN UNUSUAL CAMERA SIDE IN THE FILENAME. Owner's convention,
  2026-08-25.** Normal is bench and squat from the lifter's RIGHT and deadlift
  from their LEFT. When a clip is filmed from the other side, put a bare `l` or
  `r` token in the stem — `squat_140x4_1_l_20260901.mov`. `tracked.camera_side`
  reads it LITERALLY and it outranks `CAMERA_SIDE_EXCEPTIONS`, so a redundant
  marker is harmless and can never invert anything; a MISSING one on an unusual
  clip scores it mirrored with nothing to say so, which is why this is a capture
  rule and not a code rule. Before this the side lived in a hardcoded dict that
  only the repo knew about.

- **NO LIFTING STRAPS. Owner's decision, 2026-08-19, and it is the only rule
  here that has already cost a capture.** Straps put
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

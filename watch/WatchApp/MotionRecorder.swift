import Foundation
import CoreMotion
import HealthKit
import WatchConnectivity
import WatchKit

/// Records device-motion at 100 Hz to a CSV matching src/io.py COLUMNS, holds
/// the HealthKit workout session that keeps it running with the wrist down, and
/// ships finished logs to the paired iPhone over WatchConnectivity.
///
/// C16 — THE WORKOUT SESSION IS BACK, because C7's premise was falsified in the
/// gym. The whole argument is worth keeping, because it went wrong in both
/// directions and the shape of the mistake is the useful part.
///
/// The app originally held an `HKWorkoutSession` for the duration of a
/// recording, on the documented belief that Core Motion stops delivering once
/// watchOS suspends the app, that it suspends seconds after the wrist drops, and
/// that a workout session with the Workout Processing background mode is Apple's
/// way to prevent it. Every line of that was read off the documentation. None of
/// it was measured, and it cost the owner their own workout: watchOS permits
/// exactly one PRIMARY session per device, so pressing Calibrate silently ended
/// whatever the Workout app was running.
///
/// C7 measured it, on 2026-07-30, with no session at all:
///
///   drop_test_20260730_183925          47.08 s, 100.06 Hz, zero gaps > 15 ms
///   better_drop_test_20260730_184839   58.78 s, 100.06 Hz, ZERO gaps at any
///                                      threshold, including a 19.9 s and a
///                                      16.5 s span with the wrist still and
///                                      the screen dimmed
///
/// and deleted the session on that evidence. **Both the measurement and the
/// deletion were wrong about the case that matters, and C7 said so itself.** It
/// named its own falsifier — "the app being genuinely REPLACED mid-capture, for
/// longer than the ~6.5 s the first drop test covered" — and `TASKS.md` and
/// `HANDOFF.md` both carried it on the shot list as never collected. It has now
/// been collected, by accident, in a real session:
///
///   * captures stopped surviving the wrist going down, and
///   * a workout already running in the Workout app took priority while the
///     wrist was down, so this app was the one that got suspended,
///
/// leaving too few samples to use. That session's raw data is unusable.
///
/// WHAT THE DROP TESTS ACTUALLY PROVED, which is narrower than what was
/// concluded from them. Both were taken with the app FRONTMOST and the screen
/// merely dimmed. That is a real state and Core Motion does keep streaming
/// through it — the numbers above are not in dispute. It is not the gym state.
/// In the gym the wrist drops, watchOS returns to the clock or hands the
/// foreground to whichever app has a live workout, and a backgrounded app with
/// no session of its own is suspended. "Frontmost-and-dimmed" and "replaced"
/// are different cases, and only the first was ever tested.
///
/// The lesson is this project's recurring one: an aggregate that passes while
/// the thing fails exactly where it matters. C7 is the same shape as
/// `truth.validate` checking a whole-clip median while the tracker was lost at
/// lockout — measure the case you actually care about, not a neighbouring one
/// that is easier to stage.
///
/// SO THE SESSION RETURNS, AND WITH IT THE REASON IT HAD TO BE THE WORKOUT OF
/// RECORD. One primary session per device means this app and the Workout app
/// cannot both hold one; there is no way to share, join or even detect the
/// other's. If we take it quietly we end the owner's workout, which was the
/// original bug report. So this app does not compete with the Workout app — it
/// replaces it for a lifting session. The session drives an
/// `HKLiveWorkoutBuilder`, the Workout screen shows what the Workout app would
/// show, `endWorkout` saves to Health with ring credit, and an effort rating
/// goes on afterwards. Start the workout here and there is no second session
/// left to preempt.
///
/// WHAT WAS TRIED AND DOES NOT EXIST — do not re-propose these:
///
///   * Attaching to the Workout app's session. There is no such API.
///     `recoverActiveWorkoutSession` is documented as "Recovers an active
///     workout session after a client crash" — it hands YOUR app back YOUR
///     session, not another app's. `workoutSessionMirroringStartHandler` is
///     cross-DEVICE within one app, not cross-app. Nothing in HealthKit even
///     reports whether another app currently holds a session, so the app cannot
///     detect the collision, let alone join it.
///
///   * Starting no session and letting the lifter's Workout-app session keep the
///     watch busy. Background execution on watchOS is granted per app, not per
///     device: their session keeps THEIR app alive, not ours. This is precisely
///     what the failed gym session did — it bought nothing and cost the data.
///
///   * `WKExtendedRuntimeSession` as a substitute keep-alive. It needs a
///     `WKBackgroundModes` key Apple gates to mindfulness / physical-therapy
///     apps; the ungated session types are invalidated on `resignedFrontmost`,
///     which is exactly the wrist-drop case we need to survive.
///
/// WHAT WOULD FALSIFY THE RESTORATION, stated plainly so it is not left to the
/// next accident. If a capture taken with a session of ours running still
/// truncates when the wrist drops, the session is not what keeps Core Motion
/// alive and the problem is elsewhere. Check `dt` for gaps, not the sample
/// counter — a dropout is a gap in the timestamps and the counter rises either
/// way.
///
/// Two things the Python side asked for, both about measuring error rather than
/// about lifting:
///
/// C1 — a stillness hold AFTER the last rep as well as before the first. Zero
/// of the first thirteen captures had any end-of-record stillness, so every bias
/// estimate came from a single 1-3 s window at the start, where the residual
/// gyro bias (0.1-0.9 deg/s) is smaller than the physiological tremor it sits in
/// (~7 deg/s p-p). Two anchors ~40 s apart measure DRIFT over a long baseline
/// instead, where real wrist rotation largely cancels and bias does not. See
/// CLAUDE.md P4 — and note C6 has since measured that baseline: the effective
/// drift is 0.014 deg/s, so the pause estimate stays unapplied.
///
/// C3 — a `phase` column, so the Python side is TOLD where the anchors are
/// instead of searching for stillness. `calibrate.stillest_window` hunts the
/// quietest second in the opening 3 s, which is exactly when a finger is on the
/// Calibrate button; on a stationary test capture it picked a window with 1.8x
/// the motion of the genuinely quiet part. The cleanest window in any capture is
/// the TAIL of the closing hold, because that one is not followed by a screen
/// tap — the hold saves itself.
///
/// C2 is ABANDONED. It logged raw `CMGyroData` next to the bias-corrected
/// `deviceMotion.rotationRate` so their difference would expose Core Motion's
/// internal estimate (CLAUDE.md P5). `CMMotionManager.isGyroAvailable` returns
/// FALSE on watchOS — the raw gyro service is not offered, on one motion manager
/// or two — so there is no route to it with public API. It costs little: a
/// stationary capture measured the residual AFTER Core Motion at 0.002 deg/s.
final class MotionRecorder: NSObject, ObservableObject {

    /// `settling` is C1: still recording, holding for the closing anchor.
    enum Phase { case idle, calibrating, recording, settling }

    @Published var phase: Phase = .idle
    @Published var sampleCount = 0
    @Published var elapsed: TimeInterval = 0
    @Published var settleRemaining: TimeInterval = 0
    @Published var status = ""

    /// True while this app holds the primary workout session. The Capture screen
    /// warns when it is false and a recording is running, because that is the
    /// state a whole session's data was lost to.
    @Published var workoutActive = false

    var logName = "log"

    // Live workout metrics, so the Workout screen shows what the Workout app
    // would and the lifter gives nothing up by starting the workout here. All of
    // it comes from HKLiveWorkoutBuilder's statistics; none of it touches the
    // CSV, and a denied HealthKit type leaves the field at zero rather than
    // failing anything.
    @Published var heartRate: Double = 0        // bpm, most recent sample
    @Published var avgHeartRate: Double = 0     // bpm, workout mean
    @Published var maxHeartRate: Double = 0     // bpm, workout peak
    @Published var activeEnergy: Double = 0     // kcal
    @Published var totalEnergy: Double = 0      // kcal, active + basal
    @Published var workoutStart: Date?          // drives the elapsed clock

    /// Captures saved during this workout. Shown on the Workout screen because
    /// it is the one workout statistic this app has that the Workout app does
    /// not, and because a count that is not rising across a session is the
    /// visible sign that something is wrong with the recording path.
    @Published var capturesThisWorkout = 0

    /// Set when a workout finishes, so the effort rating has something to attach
    /// to. `relateWorkoutEffortSample` needs the saved `HKWorkout`, which only
    /// exists once `finishWorkout` has returned it.
    @Published var finishedWorkout: HKWorkout?

    /// How long to hold still after the last rep. Three seconds is the same ask
    /// as the opening pause, and what matters is the ~40 s BASELINE between the
    /// two anchors, not the length of either.
    let settleDuration: TimeInterval = 3.0

    private let sampleRate = 100.0

    private let motion = CMMotionManager()
    private let queue: OperationQueue = {
        let q = OperationQueue(); q.maxConcurrentOperationCount = 1; return q
    }()

    /// Deadline for the closing hold, in `dm.timestamp` units. Written on the
    /// main queue before entering `.settling`, read on the motion queue.
    private var settleDeadline: TimeInterval?

    /// C3. Mirrors `phase` as the integer written to the CSV, because the motion
    /// callback runs off the main queue and `phase` is `@Published`.
    ///   0 opening hold   1 reps   2 closing hold
    private var phaseCode = 0

    // HealthKit workout session. Two jobs, and they had to become one: keep us
    // running when the wrist drops, AND be the workout the lifter would
    // otherwise start in the Workout app. See the class docstring.
    private let healthStore = HKHealthStore()
    private var workout: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?

    // In-memory CSV rows. A set is a few thousand rows — trivial.
    private var rows: [String] = []
    private var t0: TimeInterval = 0

    override init() {
        super.init()
        // SwiftUI previews run in a sandbox with no HealthKit or
        // WatchConnectivity, and activating those sessions there crashes the
        // canvas.
        if ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1" { return }
        activateSession()
        requestHealthAuth()
        recoverWorkout()
    }

    // MARK: - Control (the capture screen's buttons)

    /// Start the pre-set pause capture. Recording begins here; the first seconds
    /// must be held still for calibration.
    func startCalibration() {
        guard phase == .idle else { return }
        rows.removeAll(); sampleCount = 0; elapsed = 0; t0 = 0
        settleDeadline = nil; settleRemaining = settleDuration
        status = ""

        // Auto-start the session if the lifter went straight to Calibrate
        // without visiting the Workout screen. This is the belt to the Workout
        // screen's braces, and it is not tidiness: a capture recorded with no
        // session of ours is exactly what was lost, and the loss is invisible
        // until the CSV is on the Mac. Idempotent — an already-running session
        // is reused, never doubled.
        startWorkout()

        phaseCode = 0
        startMotion()
        phase = .calibrating
    }

    /// Calibration pause is done — begin the reps. Recording is continuous; this
    /// only flips the UI prompt.
    func startSet() {
        guard phase == .calibrating else { return }
        phaseCode = 1
        phase = .recording
    }

    /// Last rep done — hold still for the closing anchor (C1). Recording
    /// continues; `save()` fires automatically when the hold completes.
    func endSet() {
        guard phase == .recording else { return }
        settleDeadline = nil          // the next sample sets it
        settleRemaining = settleDuration
        phaseCode = 2
        phase = .settling
    }

    /// Stop, write the CSV, and send it to the phone. Does NOT end the workout
    /// session — the lifter stays in one workout across many sets, so the
    /// session persists until they explicitly end it on the Workout screen.
    func save() {
        guard phase != .idle else { return }
        let held = phase == .settling && settleRemaining <= 0
        stopMotion()
        phase = .idle
        guard let url = writeCSV() else { status = "write failed"; return }
        transfer(url)
        capturesThisWorkout += 1
        if !held {
            status += " — NO closing hold, single-anchor capture"
        }
    }

    /// Throw the capture away. Distinct from `save()`, which the Discard button
    /// used to call — so "Discard" wrote a CSV, which is not what it says.
    func discard() {
        guard phase != .idle else { return }
        stopMotion()
        rows.removeAll()
        phase = .idle
        status = "discarded"
    }

    // MARK: - Motion capture

    private func startMotion() {
        guard motion.isDeviceMotionAvailable else { status = "no device motion"; return }

        motion.deviceMotionUpdateInterval = 1.0 / sampleRate
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: queue) { [weak self] dm, err in
            guard let self, let dm else { return }
            if self.t0 == 0 { self.t0 = dm.timestamp }
            let q = dm.attitude.quaternion   // w, x, y, z (body -> world)
            let a = dm.userAcceleration      // g, gravity already removed
            let g = dm.rotationRate          // rad/s, ALREADY bias-corrected

            // Raw Core Motion timestamp: io.load_log rebases to zero and keeps
            // the true spacing. %.9g matches io.save_log's precision.
            self.rows.append(String(
                format: "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%d",
                dm.timestamp, q.w, q.x, q.y, q.z, a.x, a.y, a.z, g.x, g.y, g.z,
                self.phaseCode))

            // C1: run the closing hold off the motion stream rather than a
            // Timer, because this callback keeps firing when the screen dims and
            // a main-run-loop timer may not.
            // Reads phaseCode, not `phase` — `phase` is @Published and owned by
            // the main queue, and this closure runs on the motion queue.
            var remaining: TimeInterval?
            if self.phaseCode == 2 {
                if self.settleDeadline == nil {
                    self.settleDeadline = dm.timestamp + self.settleDuration
                }
                remaining = max(0, (self.settleDeadline ?? dm.timestamp) - dm.timestamp)
            }

            let n = self.rows.count
            let e = dm.timestamp - self.t0
            DispatchQueue.main.async {
                self.sampleCount = n
                self.elapsed = e
                if let rem = remaining, self.phase == .settling {
                    self.settleRemaining = rem
                    if rem <= 0 { self.save() }
                }
            }
        }
    }

    private func stopMotion() { motion.stopDeviceMotionUpdates() }

    // MARK: - HealthKit workout (keep-alive, and the workout of record)

    private func requestHealthAuth() {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        // Read is what HKLiveWorkoutDataSource collects; share is what the
        // builder writes back as part of the saved workout, plus the effort
        // score. A denied type is not fatal — the workout still saves, just
        // thinner — so nothing here gates recording, and the CSV never depends
        // on any of it.
        //
        // `workoutEffortScore` is the "Rate your effort" sample watchOS 11
        // added. The watch target's minimum deployment is watchOS 11.0, so it
        // needs no availability guard. Note WHY that is the rule: availability
        // is checked against the DEPLOYMENT TARGET, not against the watch you
        // install on — a watchOS 26 wrist does not make a watchOS 11 symbol
        // legal in a target that says 10.0. Guarding these symbols while the
        // target said 10.0 is what an earlier build did; raising the target is
        // the cleaner answer now that watchOS 11 is the floor we support.
        var share: Set<HKSampleType> = [HKObjectType.workoutType()]
        var read: Set<HKObjectType> = [HKObjectType.workoutType()]
        let ids: [HKQuantityTypeIdentifier] = [.heartRate, .activeEnergyBurned,
                                               .basalEnergyBurned,
                                               .distanceWalkingRunning,
                                               .workoutEffortScore]
        for id in ids {
            guard let type = HKObjectType.quantityType(forIdentifier: id) else { continue }
            share.insert(type)
            read.insert(type)
        }
        healthStore.requestAuthorization(toShare: share, read: read) { _, _ in }
    }

    /// Re-attach to a session this app left running — after a crash, or after
    /// watchOS killed us between sets. This is the *only* thing HealthKit offers
    /// resembling "join a session you did not just create", and it is scoped to
    /// our own app: it will never return the Workout app's session. Without it,
    /// relaunching mid-gym-session would create a second session and strand the
    /// first workout's record unsaved.
    private func recoverWorkout() {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        healthStore.recoverActiveWorkoutSession { [weak self] session, _ in
            guard let self, let session else { return }
            DispatchQueue.main.async {
                // Only one primary session can exist, so if we already hold one
                // this callback is stale — keep what we have.
                guard self.workout == nil else { return }
                session.delegate = self
                let live = session.associatedWorkoutBuilder()
                live.delegate = self
                self.workout = session
                self.builder = live
                self.workoutActive = session.state == .running
                self.workoutStart = session.startDate
                self.status = "rejoined workout in progress"
            }
        }
    }

    /// Start the session, which is both the keep-alive and the workout that gets
    /// saved. One session spans the whole gym session, not one set, so this is
    /// idempotent — an already-running session is reused, never doubled.
    func startWorkout() {
        guard HKHealthStore.isHealthDataAvailable() else {
            setStatus("no HealthKit — recording will stop when the wrist drops")
            return
        }
        guard workout == nil else { return }
        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor
        do {
            let session = try HKWorkoutSession(healthStore: healthStore, configuration: config)
            // Delegate BEFORE startActivity, or a session refused or stolen in
            // the first instants reports it to nobody. That silence is how the
            // original collision went unnoticed for the life of the app.
            session.delegate = self
            let live = session.associatedWorkoutBuilder()
            live.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore,
                                                      workoutConfiguration: config)
            // The builder's delegate is what feeds the Workout screen. Without
            // it the session still keeps us alive and still saves — the app just
            // has nothing to show, which is the state C7 inherited and deleted.
            live.delegate = self
            let now = Date()
            session.startActivity(with: now)
            workoutStart = now
            heartRate = 0; avgHeartRate = 0; maxHeartRate = 0
            activeEnergy = 0; totalEnergy = 0
            capturesThisWorkout = 0
            finishedWorkout = nil
            // Best effort. If collection never begins we lose the Health record,
            // not the capture — the CSV is written from Core Motion and touches
            // none of this.
            live.beginCollection(withStart: now) { _, _ in }
            workout = session
            builder = live
            workoutActive = true
            setStatus("workout started here — don't start one in the Workout app")
        } catch {
            setStatus("workout session failed — recording will suspend")
        }
    }

    /// End the session and save the workout to Health. Called only by the
    /// explicit End Workout control on the Workout screen, never by `save()` —
    /// one workout spans many sets.
    ///
    /// Saving is the whole point of taking the device's only session: the lifter
    /// gave up starting a workout in the Workout app, so this has to give them
    /// the record back, ring credit included.
    func endWorkout() {
        guard let session = workout else { return }
        let live = builder
        workout = nil
        builder = nil
        workoutActive = false
        let end = Date()
        session.end()
        guard let live else { workoutStart = nil; return }
        live.endCollection(withEnd: end) { [weak self] _, _ in
            live.finishWorkout { saved, error in
                DispatchQueue.main.async {
                    self?.workoutStart = nil
                    // Kept so the effort rating has something to attach to:
                    // relateWorkoutEffortSample needs the SAVED HKWorkout, which
                    // does not exist until this callback hands it back. Left nil
                    // when the save failed, so the rating screen never appears
                    // with nothing to attach itself to.
                    self?.finishedWorkout = saved
                    self?.status = error == nil ? "workout saved to Health"
                                                : "workout ended, save failed"
                }
            }
        }
    }

    /// Attach a 1-10 "Rate your effort" score to the workout just finished.
    ///
    /// Two steps, and the second is the one that is easy to miss: saving the
    /// sample puts a number in Health, and `relateWorkoutEffortSample` is what
    /// makes it that WORKOUT's effort rather than a free-floating reading. Skip
    /// the relate and the Fitness app shows nothing.
    ///
    /// Best effort throughout. A failure here costs a rating, never a capture.
    /// Either way `finishedWorkout` is cleared, because it is what holds the
    /// rating screen up — leaving it set on a failure would strand the lifter
    /// on a screen whose only button does not work.
    func saveEffort(_ score: Int) {
        guard let workout = finishedWorkout,
              let type = HKObjectType.quantityType(forIdentifier: .workoutEffortScore)
        else { return }
        let sample = HKQuantitySample(
            type: type,
            quantity: HKQuantity(unit: .appleEffortScore(), doubleValue: Double(score)),
            start: workout.startDate,
            end: workout.endDate)
        healthStore.save(sample) { [weak self] ok, _ in
            guard ok else {
                DispatchQueue.main.async {
                    self?.status = "effort not saved"
                    self?.finishedWorkout = nil
                }
                return
            }
            self?.healthStore.relateWorkoutEffortSample(sample, with: workout,
                                                        activity: nil) { _, _ in
                DispatchQueue.main.async {
                    self?.finishedWorkout = nil
                    self?.status = "effort \(score)/10 saved"
                }
            }
        }
    }

    /// Dismiss the rating without saving one. An unrated workout is still a
    /// saved workout — forcing a rating would make the effort score the price of
    /// the Health record.
    func skipEffort() { finishedWorkout = nil }

    /// Apple's own wording for the 1-10 scale, so the rating means the same
    /// thing here as it does in the Workout app.
    static func effortLabel(_ score: Int) -> String {
        switch score {
        case ...3: return "Easy"
        case 4...6: return "Moderate"
        case 7...8: return "Hard"
        default: return "All Out"
        }
    }

    /// `status` is `@Published`, so it must be touched on the main queue — and
    /// HealthKit's delegate and completion callbacks arrive on arbitrary
    /// background queues. Stays synchronous when already on main so that
    /// `save()`'s `status += ...` still appends to the message before it.
    private func setStatus(_ text: String) {
        if Thread.isMainThread { status = text }
        else { DispatchQueue.main.async { self.status = text } }
    }

    // MARK: - CSV

    private func writeCSV() -> URL? {
        // `phase` is C3 and is OPTIONAL on the Python side, so every capture
        // recorded before it still loads. See src/io.py PHASE_COLUMN.
        let header = "t,qw,qx,qy,qz,ax,ay,az,gx,gy,gz,phase"
        let body = ([header] + rows).joined(separator: "\n") + "\n"
        let safe = (logName.isEmpty ? "log" : logName)
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: " ", with: "_")
        let stamp = Self.stamp.string(from: Date())
        let url = FileManager.default
            .urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("\(safe)_\(stamp).csv")
        do {
            try body.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            return nil
        }
    }

    private static let stamp: DateFormatter = {
        let f = DateFormatter(); f.dateFormat = "yyyyMMdd_HHmmss"; return f
    }()

    // MARK: - WatchConnectivity

    private func activateSession() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    private func transfer(_ url: URL) {
        let name = url.lastPathComponent
        guard WCSession.default.activationState == .activated else {
            status = "saved on watch (phone not linked)"; return
        }
        WCSession.default.transferFile(url, metadata: ["name": name])
        status = "sent \(name) — \(sampleCount) samples"
    }
}

/// The session ran with no delegate at all in the original build, which meant
/// losing it was completely silent: `workoutActive` stayed true, the UI stayed
/// green, and the capture just stopped part way through a set with no
/// explanation. Since only one primary session exists per device, "lost" is the
/// normal outcome of the lifter opening the Workout app mid-session — and that
/// is not hypothetical, it is what happened. It cannot be prevented. It can be
/// announced, which is all these two methods do, with a haptic because the
/// screen is dark and on a wrist at the time.
///
/// Both are called on an anonymous background queue, so every line here hops to
/// main before touching `@Published` state.
extension MotionRecorder: HKWorkoutSessionDelegate {

    func workoutSession(_ session: HKWorkoutSession,
                        didChangeTo toState: HKWorkoutSessionState,
                        from fromState: HKWorkoutSessionState,
                        date: Date) {
        guard toState == .ended || toState == .stopped else { return }
        DispatchQueue.main.async {
            // endWorkout() clears `workout` first, so a session we ended
            // ourselves fails this check and stays quiet.
            guard self.workout === session else { return }
            self.workout = nil
            self.builder = nil
            self.workoutActive = false
            self.workoutStart = nil
            self.status = self.phase != .idle
                ? "WORKOUT LOST — capture will stop when your wrist drops"
                : "workout ended by another app"
            WKInterfaceDevice.current().play(.failure)
        }
    }

    func workoutSession(_ session: HKWorkoutSession, didFailWithError error: Error) {
        let taken = (error as NSError).domain == HKErrorDomain
            && (error as NSError).code == HKError.Code.errorAnotherWorkoutSessionStarted.rawValue
        DispatchQueue.main.async {
            self.workoutActive = false
            self.status = taken
                ? "the Workout app took the session — end it there"
                : "workout error: \(error.localizedDescription)"
            WKInterfaceDevice.current().play(.failure)
        }
    }
}

/// Live metrics for the Workout screen. Everything the Workout app would show
/// for a strength session comes from here, so that starting the workout in this
/// app is not a downgrade — which it was, for exactly as long as the original
/// session existed with nothing displaying it.
///
/// `HKLiveWorkoutDataSource` decides WHICH types arrive; this only reads the
/// running statistics for whatever did. A type the lifter denied simply never
/// appears and its field stays at zero.
extension MotionRecorder: HKLiveWorkoutBuilderDelegate {

    func workoutBuilder(_ builder: HKLiveWorkoutBuilder,
                        didCollectDataOf collectedTypes: Set<HKSampleType>) {
        // Snapshot on the calling queue, publish once on main. Reading the
        // statistics is cheap; hopping per type would not be.
        var hr: Double?, hrAvg: Double?, hrMax: Double?, active: Double?, basal: Double?

        for type in collectedTypes {
            guard let quantity = type as? HKQuantityType,
                  let stats = builder.statistics(for: quantity) else { continue }
            switch quantity.identifier {
            case HKQuantityTypeIdentifier.heartRate.rawValue:
                let bpm = HKUnit.count().unitDivided(by: .minute())
                hr = stats.mostRecentQuantity()?.doubleValue(for: bpm)
                hrAvg = stats.averageQuantity()?.doubleValue(for: bpm)
                hrMax = stats.maximumQuantity()?.doubleValue(for: bpm)
            case HKQuantityTypeIdentifier.activeEnergyBurned.rawValue:
                active = stats.sumQuantity()?.doubleValue(for: .kilocalorie())
            case HKQuantityTypeIdentifier.basalEnergyBurned.rawValue:
                basal = stats.sumQuantity()?.doubleValue(for: .kilocalorie())
            default:
                continue
            }
        }

        DispatchQueue.main.async {
            if let hr { self.heartRate = hr }
            if let hrAvg { self.avgHeartRate = hrAvg }
            if let hrMax { self.maxHeartRate = hrMax }
            if let active { self.activeEnergy = active }
            // Total is what the Workout app calls "Total Calories": active plus
            // resting. Basal can arrive on its own, so recompute from whichever
            // of the two is current rather than from this callback's set.
            let a = active ?? self.activeEnergy
            let b = basal ?? max(self.totalEnergy - self.activeEnergy, 0)
            self.totalEnergy = a + b
        }
    }

    func workoutBuilderDidCollectEvent(_ builder: HKLiveWorkoutBuilder) {}
}

extension MotionRecorder: WCSessionDelegate {
    // watchOS needs only this delegate method.
    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}
}

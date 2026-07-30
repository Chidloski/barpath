import Foundation
import CoreMotion
import HealthKit
import WatchConnectivity
import WatchKit

/// Records device-motion at 100 Hz to a CSV matching src/io.py COLUMNS, keeps
/// the app alive with a HealthKit workout session, and ships finished logs to
/// the paired iPhone over WatchConnectivity.
///
/// C4 — the workout session is now the workout OF RECORD, not a hidden
/// keep-alive. watchOS allows exactly one primary workout session on the
/// device, so the old code's "start a session whenever you press Calibrate"
/// silently ended whatever the Workout app was running. It now starts on an
/// explicit button, saves itself to Health so there is no reason to run the
/// Workout app alongside, and has a delegate so a session lost to another app
/// is visible instead of silently truncating a capture. The full reasoning,
/// including the three coexistence routes that do not exist, is in the
/// HealthKit section below.
///
/// Two additions the Python side asked for, both about measuring error rather
/// than about lifting:
///
/// C1 — a stillness hold AFTER the last rep as well as before the first. Zero
/// of the first thirteen captures had any end-of-record stillness, so every
/// bias estimate came from a single 1-3 s window at the start, where the
/// residual gyro bias (0.1-0.9 deg/s) is smaller than the physiological tremor
/// it sits in (~7 deg/s p-p). Two anchors ~40 s apart measure DRIFT over a long
/// baseline instead, where real wrist rotation largely cancels and bias does
/// not. See CLAUDE.md P4.
///
/// C3 — a `phase` column, so the Python side is TOLD where the anchors are
/// instead of searching for stillness. `calibrate.stillest_window` currently
/// hunts the quietest second in the opening 3 s, which is exactly when a finger
/// is on the Calibrate button; on a stationary test capture it picked a window
/// with 1.8x the motion of the genuinely quiet part. The cleanest window in any
/// capture is the TAIL of the closing hold, because that one is not followed by
/// a screen tap — the hold saves itself. You cannot find that without knowing
/// which phase each sample belongs to.
///
/// C2 is ABANDONED. It logged raw `CMGyroData` next to the bias-corrected
/// `deviceMotion.rotationRate` so their difference would expose Core Motion's
/// internal estimate (CLAUDE.md P5). `CMMotionManager.isGyroAvailable` returns
/// FALSE on watchOS — the raw gyro service is not offered, on one manager or
/// two — so there is no route to it with public API. It costs little: a
/// stationary capture measured the residual AFTER Core Motion at 0.002 deg/s,
/// so there was never much for its estimate to explain.
final class MotionRecorder: NSObject, ObservableObject {

    /// `settling` is C1: still recording, holding for the closing anchor.
    enum Phase { case idle, calibrating, recording, settling }

    @Published var phase: Phase = .idle
    @Published var sampleCount = 0
    @Published var elapsed: TimeInterval = 0
    @Published var settleRemaining: TimeInterval = 0
    @Published var status = ""

    @Published var workoutActive = false   // keep-alive session is running
    var logName = "log"

    /// Record with NO workout session, deliberately. The whole C4 workflow
    /// change — start your workout here, not in the Workout app — rests on one
    /// untested assumption: that an HKWorkoutSession is what keeps Core Motion
    /// delivering once the wrist drops. That is Apple's documented mechanism
    /// and it is why this code exists, but nobody has ever measured what
    /// happens WITHOUT one on this watch, this watchOS, this app.
    ///
    /// If a wrist-down set holds ~100 Hz with this on, the session is not
    /// load-bearing, the collision with the Workout app never mattered, and the
    /// right change is to stop starting one at all — deleting the workflow
    /// change, the delegate, and most of the HealthKit section below.
    ///
    /// Costs one set to find out. The capture is expected to truncate; that IS
    /// the result, so name it something you will recognise and do not use it as
    /// lifting data.
    @Published var sessionlessTest = false

    // Live workout metrics, so this app can show what the Workout app would and
    // the lifter is not giving anything up by starting the workout here. All of
    // it comes from HKLiveWorkoutBuilder's statistics; none of it touches the
    // CSV, and a denied HealthKit type leaves the field at zero rather than
    // failing anything.
    @Published var heartRate: Double = 0        // bpm, most recent sample
    @Published var avgHeartRate: Double = 0     // bpm, workout mean
    @Published var activeEnergy: Double = 0     // kcal
    @Published var totalEnergy: Double = 0      // kcal, active + basal
    @Published var workoutStart: Date?          // drives the elapsed clock

    /// Set when a workout finishes, so the effort rating has something to
    /// attach to. `relateWorkoutEffortSample` needs the saved HKWorkout, which
    /// only exists once `finishWorkout` has returned it.
    @Published var finishedWorkout: HKWorkout?
    @Published var effortSaved = false

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

    // HealthKit workout session. Two jobs now: keep us running when the wrist
    // drops, AND be the workout the lifter would otherwise start in the Workout
    // app. See the HealthKit section below for why those had to become one job.
    private let healthStore = HKHealthStore()
    private var workout: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?

    // In-memory CSV rows. A set is a few thousand rows — trivial.
    private var rows: [String] = []
    private var t0: TimeInterval = 0

    override init() {
        super.init()
        // SwiftUI previews run in a sandbox that has no HealthKit or
        // WatchConnectivity — activating those sessions there crashes the
        // canvas. Skip session setup in previews; the real app still does it.
        if ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1" { return }
        activateSession()
        requestHealthAuth()
        recoverWorkout()
    }

    // MARK: - Control (the three buttons)

    /// Start the pre-set pause capture. Recording begins here; the first
    /// seconds must be held still for calibration.
    func startCalibration() {
        guard phase == .idle else { return }
        rows.removeAll(); sampleCount = 0; elapsed = 0; t0 = 0
        settleDeadline = nil; settleRemaining = settleDuration
        status = ""
        // Auto-start the keep-alive if the lifter did not press Start Workout.
        // Losing a gym capture to a suspended app is worse than taking over the
        // device's workout session, so this stays automatic — but startWorkout()
        // now says on screen that it took the session, rather than doing it
        // invisibly the way this line used to.
        //
        // `sessionlessTest` is the one exception, and it exists to run the
        // experiment that could delete all of this. See its declaration.
        if !sessionlessTest { startWorkout() }
        phaseCode = 0
        startMotion()
        phase = .calibrating
    }

    /// Calibration pause is done — begin the reps. Recording is continuous;
    /// this only flips the UI prompt.
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
    /// keep-alive session persists until they explicitly end it.
    func save() {
        guard phase != .idle else { return }
        let held = phase == .settling && settleRemaining <= 0
        stopMotion()
        phase = .idle
        guard let url = writeCSV() else { status = "write failed"; return }
        transfer(url)
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
            // Timer, because this callback keeps firing when the screen sleeps
            // and a main-run-loop timer may not.
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
    //
    // WHY A WORKOUT SESSION AT ALL. Core Motion stops delivering the moment
    // watchOS suspends the app, and it suspends the app seconds after the wrist
    // drops. An HKWorkoutSession — with the Workout Processing background mode —
    // is the one mechanism Apple documents for keeping a watch app and its
    // sensors running with the screen off. Without it a capture silently stops
    // part way through a set. That is not theory; it is why this code exists.
    //
    // WHY IT USED TO KILL THE LIFTER'S OWN WORKOUT. watchOS permits exactly one
    // PRIMARY workout session on the device. HKError's own wording:
    // errorAnotherWorkoutSessionStarted is "Another primary workout session has
    // started or is already ongoing by this or another application."
    // startCalibration() created one unconditionally, so pressing Calibrate
    // ended the session the Workout app was running — reported by the owner as
    // "logging data stops my workout". Nothing in this file noticed, because no
    // delegate was ever attached to the session.
    //
    // WHAT WAS TRIED AND DOES NOT EXIST — do not re-propose these:
    //
    //   * Attaching to the Workout app's session. There is no such API.
    //     `recoverActiveWorkoutSession` is documented as "Recovers an active
    //     workout session after a client crash" — it hands YOUR app back YOUR
    //     session, not another app's. `workoutSessionMirroringStartHandler` is
    //     cross-DEVICE within one app, not cross-app. Nothing in HealthKit even
    //     reports whether another app currently holds a session, so the app
    //     cannot detect the collision, let alone join it.
    //
    //   * Starting no session and letting the lifter's Workout-app session keep
    //     the watch busy. Background execution on watchOS is granted per app,
    //     not per device: their session keeps THEIR app alive, not ours. This
    //     buys nothing and costs the capture.
    //
    //   * WKExtendedRuntimeSession as a substitute keep-alive. Rejected without
    //     testing, deliberately. It needs a WKBackgroundModes plist key this app
    //     does not have and that Apple gates to mindfulness / physical-therapy
    //     apps; the ungated session types are invalidated with
    //     `resignedFrontmost`, which is exactly the wrist-drop case we need to
    //     survive; and nothing documents that Core Motion keeps streaming at
    //     100 Hz under one. Trading a keep-alive that demonstrably works for one
    //     that might risks a whole gym capture, and gym captures are the
    //     expensive thing in this project.
    //
    // SO THE FIX RUNS THE OTHER WAY: stop competing with the Workout app and BE
    // the workout. The session drives an HKLiveWorkoutBuilder, and endWorkout()
    // finishes and saves it, so the strength-training workout lands in Health
    // with heart rate and energy and earns its ring credit. The lifter starts
    // the workout here instead of in the Workout app, and there is no second
    // session left to preempt.
    //
    // THE TRADEOFF, PLAINLY. The workflow changes: start the workout in this app.
    // If the Workout app is opened first it still loses its session, and if it
    // is opened DURING a recording it now preempts US and the capture can
    // truncate. watchOS gives no way to prevent either — only to notice, which
    // is what the delegate at the bottom of this file is for.
    //
    // WHAT WOULD FALSIFY THIS. If a capture holds ~100 Hz through a wrist-down
    // set with no workout session of ours running, then the session is not
    // load-bearing, none of the above matters, and the right fix is simply to
    // stop starting one. That test costs one set and has never been run.

    private func requestHealthAuth() {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        // Read is what HKLiveWorkoutDataSource collects; share is what the
        // builder writes back as part of the saved workout. A denied type is not
        // fatal — the workout still saves, just thinner — so nothing here gates
        // recording, and the CSV never depends on any of it.
        var share: Set<HKSampleType> = [HKObjectType.workoutType()]
        var read: Set<HKObjectType> = [HKObjectType.workoutType()]
        var ids: [HKQuantityTypeIdentifier] = [.heartRate, .activeEnergyBurned,
                                              .basalEnergyBurned,
                                              .distanceWalkingRunning]
        // workoutEffortScore is the "Rate your effort" sample watchOS 11 added.
        // Guarded rather than raising the project's minimum deployment target,
        // because the compiler checks availability against THAT, not against the
        // watch you install on — a watchOS 26 device does not make a watchOS 11
        // symbol legal in a target that says 10.0. See `effortAvailable`.
        if #available(watchOS 11.0, *) { ids.append(.workoutEffortScore) }
        for id in ids {
            guard let type = HKObjectType.quantityType(forIdentifier: id) else { continue }
            share.insert(type)
            read.insert(type)
        }
        healthStore.requestAuthorization(toShare: share, read: read) { _, _ in }
    }

    /// Re-attach to a session this app left running — after a crash, or after
    /// watchOS killed us between sets. This is the *only* thing HealthKit offers
    /// that resembles "join a session you did not just create", and it is scoped
    /// to our own app: it will never return the Workout app's session. Without
    /// it, relaunching mid-gym-session would create a second session and strand
    /// the first workout's record unsaved.
    private func recoverWorkout() {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        healthStore.recoverActiveWorkoutSession { [weak self] session, _ in
            guard let self, let session else { return }
            DispatchQueue.main.async {
                // Only one primary session can exist, so if we already hold one
                // this callback is stale — keep what we have.
                guard self.workout == nil else { return }
                session.delegate = self
                self.workout = session
                self.builder = session.associatedWorkoutBuilder()
                self.workoutActive = session.state == .running
                self.status = "rejoined workout in progress"
            }
        }
    }

    /// Start the keep-alive session, which is also the workout that gets saved.
    /// One session spans the whole gym session, not one set, so this is
    /// idempotent — an already-running session is reused, never doubled.
    func startWorkout() {
        guard HKHealthStore.isHealthDataAvailable() else {
            setStatus("no HealthKit — recording may stop when the screen sleeps")
            return
        }
        guard workout == nil else { return }
        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor
        do {
            let session = try HKWorkoutSession(healthStore: healthStore, configuration: config)
            // Delegate BEFORE startActivity, or a session that is refused or
            // stolen in the first instants reports it to nobody.
            session.delegate = self
            let live = session.associatedWorkoutBuilder()
            live.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore,
                                                      workoutConfiguration: config)
            // The builder's delegate is what feeds the metrics screen. Without
            // it the session still keeps us alive and still saves — the app just
            // has nothing to show, which is the state this replaced.
            live.delegate = self
            let now = Date()
            session.startActivity(with: now)
            workoutStart = now
            heartRate = 0; avgHeartRate = 0; activeEnergy = 0; totalEnergy = 0
            finishedWorkout = nil; effortSaved = false
            // Best effort. If collection never begins we lose the Health record,
            // not the capture — the CSV is written from Core Motion and touches
            // none of this.
            live.beginCollection(withStart: now) { _, _ in }
            workout = session
            builder = live
            workoutActive = true
            setStatus("workout started here — don't start one in the Workout app")
        } catch {
            setStatus("workout session failed (recording may suspend)")
        }
    }

    /// End the session and save the workout to Health. Called only by the
    /// explicit End Workout control, never by save() — one workout spans many
    /// sets. No-op if we hold no session.
    ///
    /// Saving is the whole point of the C4 change: the lifter gave up starting a
    /// workout in the Workout app, so this has to give them the record back.
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
                    // where the OS cannot rate, so the rating screen never
                    // appears with no way to complete it.
                    self?.finishedWorkout = MotionRecorder.effortAvailable ? saved : nil
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
    func saveEffort(_ score: Int) {
        guard #available(watchOS 11.0, *) else { finishedWorkout = nil; return }
        guard let workout = finishedWorkout,
              let type = HKObjectType.quantityType(forIdentifier: .workoutEffortScore)
        else { return }
        let sample = HKQuantitySample(
            type: type,
            quantity: HKQuantity(unit: .appleEffortScore(), doubleValue: Double(score)),
            start: workout.startDate,
            end: workout.endDate)
        healthStore.save(sample) { [weak self] ok, _ in
            guard ok else { self?.setStatus("effort not saved"); return }
            self?.healthStore.relateWorkoutEffortSample(sample, with: workout,
                                                        activity: nil) { _, _ in
                DispatchQueue.main.async {
                    self?.effortSaved = true
                    self?.finishedWorkout = nil
                    self?.status = "effort \(score)/10 saved"
                }
            }
        }
    }

    /// Whether this OS can record an effort score at all.
    ///
    /// The effort APIs are watchOS 11. Swift checks availability against the
    /// project's MINIMUM DEPLOYMENT TARGET, not against the watch the build
    /// lands on, so a watchOS 26 wrist does not make them legal in a target set
    /// to 10.0 — that mismatch is what broke the build. Everything else here
    /// works at 10.0, so the rating is gated rather than the whole app being
    /// held to 11.0. On an older target the workout still saves; only the
    /// rating screen is absent.
    static var effortAvailable: Bool {
        if #available(watchOS 11.0, *) { return true }
        return false
    }

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
    /// save()'s `status += ...` still appends to the message before it.
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

/// The session used to run with no delegate at all, which meant losing it was
/// completely silent: `workoutActive` stayed true, the UI stayed green, and the
/// capture just stopped part way through a set with no explanation. Since only
/// one primary workout session exists per device, "lost" is the normal outcome
/// of the lifter opening the Workout app mid-set — the same collision that used
/// to run in our favour, now running against us. It cannot be prevented. It can
/// be announced, which is all these two methods do.
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
            if self.phase != .idle {
                self.status = "WORKOUT LOST — capture may stop early"
                WKInterfaceDevice.current().play(.failure)
            }
        }
    }

    func workoutSession(_ session: HKWorkoutSession, didFailWithError error: Error) {
        let taken = (error as NSError).domain == HKErrorDomain
            && (error as NSError).code == HKError.Code.errorAnotherWorkoutSessionStarted.rawValue
        DispatchQueue.main.async {
            self.workoutActive = false
            self.status = taken
                ? "another app took the workout session"
                : "workout error: \(error.localizedDescription)"
            if self.phase != .idle { WKInterfaceDevice.current().play(.failure) }
        }
    }
}

/// Live metrics for the workout screen. Everything the Workout app would show
/// for a strength session comes from here, so that starting the workout in this
/// app is not a downgrade — which it was, for exactly as long as C4's session
/// existed with nothing displaying it.
///
/// `HKLiveWorkoutDataSource` decides WHICH types arrive; this only reads the
/// running statistics for whatever did. A type the lifter denied simply never
/// appears and its field stays at zero.
extension MotionRecorder: HKLiveWorkoutBuilderDelegate {

    func workoutBuilder(_ builder: HKLiveWorkoutBuilder,
                        didCollectDataOf collectedTypes: Set<HKSampleType>) {
        // Snapshot on the calling queue, publish once on main. Reading the
        // statistics is cheap; hopping per type would not be.
        var hr: Double?, hrAvg: Double?, active: Double?, basal: Double?

        for type in collectedTypes {
            guard let quantity = type as? HKQuantityType,
                  let stats = builder.statistics(for: quantity) else { continue }
            switch quantity.identifier {
            case HKQuantityTypeIdentifier.heartRate.rawValue:
                let bpm = HKUnit.count().unitDivided(by: .minute())
                hr = stats.mostRecentQuantity()?.doubleValue(for: bpm)
                hrAvg = stats.averageQuantity()?.doubleValue(for: bpm)
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

import Foundation
import CoreMotion
import HealthKit
import WatchConnectivity

/// Records device-motion at 100 Hz to a CSV matching src/io.py COLUMNS, keeps
/// the app alive with a HealthKit workout session, and ships finished logs to
/// the paired iPhone over WatchConnectivity.
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
/// C2 — raw `CMGyroData` alongside `deviceMotion.rotationRate`. Core Motion has
/// already bias-corrected the latter using an opaque, time-varying internal
/// estimate, so what we currently log is only the residual after it. Logging
/// both exposes that estimate directly by difference. See CLAUDE.md P5.
final class MotionRecorder: NSObject, ObservableObject {

    /// `settling` is C1: still recording, holding for the closing anchor.
    enum Phase { case idle, calibrating, recording, settling }

    @Published var phase: Phase = .idle
    @Published var sampleCount = 0
    @Published var elapsed: TimeInterval = 0
    @Published var settleRemaining: TimeInterval = 0
    /// True once a raw-gyro sample has actually arrived (C2). Surfaced on screen
    /// during recording, because the alternative is finding out that the C2
    /// columns are empty tomorrow evening after the session — the same class of
    /// mistake as the acceleration sign, which stayed invisible for months by
    /// only ever being checked where it could not be seen.
    @Published var rawGyroOK = false
    @Published var status = ""
    @Published var workoutActive = false   // keep-alive session is running
    var logName = "log"

    /// How long to hold still after the last rep. Three seconds is the same ask
    /// as the opening pause, and what matters is the ~40 s BASELINE between the
    /// two anchors, not the length of either.
    let settleDuration: TimeInterval = 3.0

    private let sampleRate = 100.0

    private let motion = CMMotionManager()
    private let queue: OperationQueue = {
        let q = OperationQueue(); q.maxConcurrentOperationCount = 1; return q
    }()

    /// Latest raw gyro sample, paired with device-motion on arrival (C2). Both
    /// streams run at 100 Hz but on separate callbacks, so the pairing is within
    /// roughly one sample. Its timestamp is logged too, so the Python side can
    /// check the lag rather than assume it: the quantity of interest is
    /// `rotationRate - raw`, and if the two samples are far apart in time that
    /// difference is real rotation rather than Core Motion's bias estimate.
    private var lastRawGyro: (t: TimeInterval, x: Double, y: Double, z: Double)?

    /// Deadline for the closing hold, in `dm.timestamp` units. Written on the
    /// main queue before entering `.settling`, read on the motion queue.
    private var settleDeadline: TimeInterval?

    // HealthKit workout session — its only job is to keep us running when the
    // wrist drops. We never save the workout.
    private let healthStore = HKHealthStore()
    private var workout: HKWorkoutSession?

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
    }

    // MARK: - Control (the three buttons)

    /// Start the pre-set pause capture. Recording begins here; the first
    /// seconds must be held still for calibration.
    func startCalibration() {
        guard phase == .idle else { return }
        rows.removeAll(); sampleCount = 0; elapsed = 0; t0 = 0
        settleDeadline = nil; settleRemaining = settleDuration
        lastRawGyro = nil; rawGyroOK = false
        status = ""
        startWorkout()
        startMotion()
        phase = .calibrating
    }

    /// Calibration pause is done — begin the reps. Recording is continuous;
    /// this only flips the UI prompt.
    func startSet() {
        guard phase == .calibrating else { return }
        phase = .recording
    }

    /// Last rep done — hold still for the closing anchor (C1). Recording
    /// continues; `save()` fires automatically when the hold completes.
    func endSet() {
        guard phase == .recording else { return }
        settleDeadline = nil          // the next sample sets it
        settleRemaining = settleDuration
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

        // C2: raw gyro, started first so a sample is already waiting when the
        // first device-motion callback lands. Unavailable is not fatal — the
        // extra columns are optional in io.load_log and the capture is still
        // usable without them.
        if motion.isGyroAvailable {
            motion.gyroUpdateInterval = 1.0 / sampleRate
            motion.startGyroUpdates(to: queue) { [weak self] data, _ in
                guard let self, let d = data else { return }
                let r = d.rotationRate
                self.lastRawGyro = (d.timestamp, r.x, r.y, r.z)
                if !self.rawGyroOK { DispatchQueue.main.async { self.rawGyroOK = true } }
            }
        } else {
            status = "no raw gyro — capture is still fine, C2 columns will be blank"
        }

        motion.deviceMotionUpdateInterval = 1.0 / sampleRate
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: queue) { [weak self] dm, err in
            guard let self, let dm else { return }
            if self.t0 == 0 { self.t0 = dm.timestamp }
            let q = dm.attitude.quaternion   // w, x, y, z (body -> world)
            let a = dm.userAcceleration      // g, gravity already removed
            let g = dm.rotationRate          // rad/s, ALREADY bias-corrected
            let raw = self.lastRawGyro       // rad/s, not corrected (C2)

            // Raw Core Motion timestamp: io.load_log rebases to zero and keeps
            // the true spacing. %.9g matches io.save_log's precision. Empty
            // fields where raw gyro is unavailable — genfromtxt reads those as
            // nan, which is the honest value.
            var row = String(
                format: "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g",
                dm.timestamp, q.w, q.x, q.y, q.z, a.x, a.y, a.z, g.x, g.y, g.z)
            if let r = raw {
                row += String(format: ",%.9g,%.9g,%.9g,%.9g", r.t, r.x, r.y, r.z)
            } else {
                row += ",,,,"
            }
            self.rows.append(row)

            // C1: run the closing hold off the motion stream rather than a
            // Timer, because this callback keeps firing when the screen sleeps
            // and a main-run-loop timer may not.
            var remaining: TimeInterval?
            if self.phase == .settling {
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

    private func stopMotion() {
        motion.stopDeviceMotionUpdates()
        motion.stopGyroUpdates()
    }

    // MARK: - HealthKit workout (keep-alive only)

    private func requestHealthAuth() {
        guard HKHealthStore.isHealthDataAvailable() else { return }
        let types: Set = [HKObjectType.workoutType()]
        healthStore.requestAuthorization(toShare: types, read: types) { _, _ in }
    }

    // The keep-alive session spans the whole logging session, not one set.
    // Starting is idempotent: if we already own a running session (from an
    // earlier set), reuse it rather than spawning a second. We only ever end a
    // session we started here — never one the Workout app owns.
    private func startWorkout() {
        guard HKHealthStore.isHealthDataAvailable(), workout == nil else { return }
        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor
        do {
            let session = try HKWorkoutSession(healthStore: healthStore, configuration: config)
            session.startActivity(with: Date())
            workout = session
            DispatchQueue.main.async { self.workoutActive = true }
        } catch {
            status = "workout session failed (recording may suspend)"
        }
    }

    /// End the keep-alive workout. Called only by the explicit End Workout
    /// control, never by finish(). No-op if we do not own a session.
    func endWorkout() {
        guard workout != nil else { return }
        workout?.end()
        workout = nil
        DispatchQueue.main.async { self.workoutActive = false }
    }

    // MARK: - CSV

    private func writeCSV() -> URL? {
        // The four trailing columns are C2 and are OPTIONAL on the Python side,
        // so the ten captures recorded before this change still load.
        let header = "t,qw,qx,qy,qz,ax,ay,az,gx,gy,gz,rgt,rgx,rgy,rgz"
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

extension MotionRecorder: WCSessionDelegate {
    // watchOS needs only this delegate method.
    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}
}

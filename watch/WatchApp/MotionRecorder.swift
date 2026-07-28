import Foundation
import CoreMotion
import HealthKit
import WatchConnectivity

/// Records device-motion at 100 Hz to a CSV matching src/io.py COLUMNS, keeps
/// the app alive with a HealthKit workout session, and ships finished logs to
/// the paired iPhone over WatchConnectivity.
final class MotionRecorder: NSObject, ObservableObject {

    enum Phase { case idle, calibrating, recording }

    @Published var phase: Phase = .idle
    @Published var sampleCount = 0
    @Published var elapsed: TimeInterval = 0
    @Published var status = ""
    @Published var workoutActive = false   // keep-alive session is running
    var logName = "log"

    private let sampleRate = 100.0

    private let motion = CMMotionManager()
    private let queue: OperationQueue = {
        let q = OperationQueue(); q.maxConcurrentOperationCount = 1; return q
    }()

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

    /// Stop, write the CSV, and send it to the phone. Does NOT end the workout
    /// session — the lifter stays in one workout across many sets, so the
    /// keep-alive session persists until they explicitly end it.
    func finish() {
        guard phase != .idle else { return }
        stopMotion()
        phase = .idle
        if let url = writeCSV() { transfer(url) }
        else { status = "write failed" }
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
            let g = dm.rotationRate          // rad/s
            // Raw Core Motion timestamp: io.load_log rebases to zero and keeps
            // the true spacing. %.9g matches io.save_log's precision.
            self.rows.append(String(
                format: "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g",
                dm.timestamp, q.w, q.x, q.y, q.z, a.x, a.y, a.z, g.x, g.y, g.z))
            let n = self.rows.count
            let e = dm.timestamp - self.t0
            DispatchQueue.main.async { self.sampleCount = n; self.elapsed = e }
        }
    }

    private func stopMotion() { motion.stopDeviceMotionUpdates() }

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
        let header = "t,qw,qx,qy,qz,ax,ay,az,gx,gy,gz"
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

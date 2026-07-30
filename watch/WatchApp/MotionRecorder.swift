import Foundation
import CoreMotion
import WatchConnectivity

/// Records device-motion at 100 Hz to a CSV matching src/io.py COLUMNS, and
/// ships finished logs to the paired iPhone over WatchConnectivity.
///
/// C7 — THE WORKOUT SESSION WAS REMOVED, and the reason is worth keeping.
///
/// This app used to hold an `HKWorkoutSession` for the duration of a recording.
/// The stated reason, believed for as long as the app existed: Core Motion
/// stops delivering the moment watchOS suspends the app, watchOS suspends it
/// seconds after the wrist drops, and an HKWorkoutSession with the Workout
/// Processing background mode is Apple's documented way to prevent that. Every
/// line of it was reasoning from the docs. None of it was measured.
///
/// It had a real cost. watchOS permits exactly one PRIMARY workout session per
/// device — `HKErrorAnotherWorkoutSessionStarted` is "by this or another
/// application" — so taking one ended whatever the owner had started in the
/// Workout app before walking into the gym. Reported as "logging data stops my
/// workout". The first fix ran the other way: keep the session, save it to
/// Health, and have this app REPLACE the Workout app, with live metrics and an
/// effort rating so nothing was lost. That worked, and it was a workflow change
/// imposed to solve a problem nobody had checked was real.
///
/// So it was checked, on 2026-07-30, with no session at all:
///
///   drop_test_20260730_183925          47.08 s, 100.06 Hz, zero gaps > 15 ms
///   better_drop_test_20260730_184839   58.78 s, 100.06 Hz, ZERO gaps at any
///                                      threshold, including a 19.9 s and a
///                                      16.5 s span with the wrist still and
///                                      the screen dimmed, and a notification
///                                      raised and dismissed mid-capture
///
/// Zero repeated rows in either, unit quaternions, `io.check_log` clean. The
/// premise was false for the case that matters: a capture is 40-60 s, the app
/// stays frontmost for that long, and Core Motion keeps streaming at 100 Hz
/// while it is frontmost-and-dimmed.
///
/// WHAT WOULD BRING IT BACK. The untested case is the app being genuinely
/// REPLACED mid-capture — the watch face returning, or another app opened — for
/// longer than the ~6.5 s the first test covered. watchOS's Return to Clock
/// default will not fire inside a single set, which is why this is judged safe.
/// If captures ever start truncating, check that first, and read this comment
/// before re-adding a session: the fix is not automatically a workout session.
///
/// Two things the Python side asked for, both about measuring error rather
/// than about lifting:
///
/// C1 — a stillness hold AFTER the last rep as well as before the first. Zero
/// of the first thirteen captures had any end-of-record stillness, so every
/// bias estimate came from a single 1-3 s window at the start, where the
/// residual gyro bias (0.1-0.9 deg/s) is smaller than the physiological tremor
/// it sits in (~7 deg/s p-p). Two anchors ~40 s apart measure DRIFT over a long
/// baseline instead, where real wrist rotation largely cancels and bias does
/// not. See CLAUDE.md P4 — and note C6 has since measured that baseline: the
/// effective drift is 0.014 deg/s, so the pause estimate stays unapplied.
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

    /// Deadline for the closing hold, in `dm.timestamp` units. Written on the
    /// main queue before entering `.settling`, read on the motion queue.
    private var settleDeadline: TimeInterval?

    /// C3. Mirrors `phase` as the integer written to the CSV, because the motion
    /// callback runs off the main queue and `phase` is `@Published`.
    ///   0 opening hold   1 reps   2 closing hold
    private var phaseCode = 0

    // In-memory CSV rows. A set is a few thousand rows — trivial.
    private var rows: [String] = []
    private var t0: TimeInterval = 0

    override init() {
        super.init()
        // SwiftUI previews run in a sandbox with no WatchConnectivity, and
        // activating a session there crashes the canvas.
        if ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] == "1" { return }
        activateSession()
    }

    // MARK: - Control (the three buttons)

    /// Start the pre-set pause capture. Recording begins here; the first
    /// seconds must be held still for calibration.
    func startCalibration() {
        guard phase == .idle else { return }
        rows.removeAll(); sampleCount = 0; elapsed = 0; t0 = 0
        settleDeadline = nil; settleRemaining = settleDuration
        status = ""
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

    /// Stop, write the CSV, and send it to the phone.
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
            // Timer, because this callback keeps firing when the screen dims
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

extension MotionRecorder: WCSessionDelegate {
    // watchOS needs only this delegate method.
    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}
}

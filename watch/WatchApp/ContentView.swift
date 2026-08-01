import SwiftUI
import HealthKit

/// Two screens paged with the crown, plus an effort rating at the end.
///
/// C16 put the workout session back (see `MotionRecorder`), and that decides
/// this file's shape. watchOS allows exactly one workout session per device, so
/// holding it means the lifter cannot use the Workout app during a gym session
/// — the app has to give back what the Workout app gave, or the fix for the
/// wrist-down data loss is a downgrade everywhere else.
///
/// Hence a screen reserved purely for the workout, showing what the Workout app
/// shows for a strength session, and a separate screen for captures. Paged
/// rather than one long scroll because the two serve different moments: between
/// sets you want the workout at a glance and nothing to press; during a set you
/// want one large button and no distraction. Scrolling past a heart rate to
/// reach "Finish Set" mid-effort is exactly the wrong shape.
///
/// There is deliberately no pause control, though the Workout app has one. A
/// paused session is not a running session, and "the session is running" is the
/// entire reason this app can record with the wrist down. A pause button is a
/// one-tap way to silently break the capture, which is the failure C16 exists to
/// fix.
struct ContentView: View {
    @StateObject private var rec = MotionRecorder()

    /// Start on the Workout screen. That is the deliberate change from the old
    /// paged build, which opened on Record: the recurring failure is a capture
    /// taken with no session, so the first thing the app shows is the state of
    /// the workout. It pages itself to Capture once one is running.
    @State private var page = 0

    var body: some View {
        if rec.finishedWorkout != nil {
            EffortView(rec: rec)
        } else {
            TabView(selection: $page) {
                WorkoutView(rec: rec).tag(0)
                CaptureView(rec: rec).tag(1)
            }
            .tabViewStyle(.verticalPage)
            .onChange(of: rec.workoutActive) { _, active in
                // Starting the workout is a means, not an end — move to the
                // screen the lifter actually came to use.
                if active { page = 1 }
            }
        }
    }
}

// MARK: - The workout screen

/// Purely the workout: what the Workout app would show for a strength session,
/// and the two controls that bracket it. Nothing about captures appears here
/// except the count, which is a workout statistic in its own right.
///
/// Laid out for a glance between sets — one dominant number and supporting rows
/// — rather than the Workout app's four co-equal metrics, because the elapsed
/// clock is the one you look for when deciding whether to start the next set.
struct WorkoutView: View {
    @ObservedObject var rec: MotionRecorder

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {

                if let start = rec.workoutStart {
                    // `style: .timer` keeps counting without a Timer of our own,
                    // which matters because a run-loop timer may not fire once
                    // the screen sleeps and the motion callback is busy.
                    Text(start, style: .timer)
                        .font(.system(size: 44, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.green)
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                } else {
                    Text("--:--")
                        .font(.system(size: 44, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }

                Text("TRADITIONAL STRENGTH TRAINING · INDOOR")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)

                Divider()

                Metric(icon: "heart.fill", tint: .red,
                       value: rec.heartRate > 0 ? "\(Int(rec.heartRate))" : "--",
                       unit: "BPM",
                       caption: heartCaption)

                Metric(icon: "flame.fill", tint: .orange,
                       value: "\(Int(rec.activeEnergy.rounded()))",
                       unit: "ACTIVE KCAL",
                       caption: "\(Int(rec.totalEnergy.rounded())) total")

                Metric(icon: "waveform.path.ecg", tint: .blue,
                       value: "\(rec.capturesThisWorkout)",
                       unit: "CAPTURES",
                       caption: rec.phase != .idle ? "recording now" : nil)

                Divider()

                if rec.workoutActive {
                    Button("End Workout & Save", role: .destructive) { rec.endWorkout() }
                        .frame(maxWidth: .infinity)
                        // Ending mid-capture would drop the keep-alive with the
                        // recording still running, which is the exact failure
                        // this build exists to prevent.
                        .disabled(rec.phase != .idle)
                    Text(rec.phase != .idle
                         ? "finish the capture first"
                         : "saves to Health, then rate your effort")
                        .font(.caption2).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .multilineTextAlignment(.center)
                } else {
                    Button {
                        rec.startWorkout()
                    } label: {
                        Label("Start Workout",
                              systemImage: "figure.strengthtraining.traditional")
                            .frame(maxWidth: .infinity)
                    }
                    .tint(.pink)
                    // Not a style note. One session exists per device, so a
                    // workout started in the Workout app takes ours and the
                    // capture truncates when the wrist drops — which is how a
                    // whole session's data was lost.
                    Text("start it here, not in the Workout app")
                        .font(.caption2).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .multilineTextAlignment(.center)
                }

                if !rec.status.isEmpty {
                    Text(rec.status).font(.caption2).foregroundStyle(.secondary)
                }

                Label("swipe down for captures", systemImage: "chevron.down")
                    .font(.caption2).foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal)
        }
    }

    /// Average and peak, the two the Workout app's summary carries. Only shown
    /// once there is a reading, so a denied heart-rate permission reads as "--"
    /// rather than as a resting 0.
    private var heartCaption: String? {
        guard rec.avgHeartRate > 0 else { return nil }
        var s = "avg \(Int(rec.avgHeartRate))"
        if rec.maxHeartRate > 0 { s += " · max \(Int(rec.maxHeartRate))" }
        return s
    }
}

/// One metric: a large value, its unit, and an optional secondary line.
struct Metric: View {
    let icon: String
    let tint: Color
    let value: String
    let unit: String
    var caption: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: icon).foregroundStyle(tint).font(.footnote)
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(value)
                        .font(.system(size: 28, weight: .medium, design: .rounded))
                        .monospacedDigit()
                    Text(unit).font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                if let caption {
                    Text(caption).font(.caption2).foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
    }
}

// MARK: - The capture screen

/// The capture protocol, unchanged: name it, anchor at the start, anchor at the
/// end. Four states, one button that matters in each.
struct CaptureView: View {
    @ObservedObject var rec: MotionRecorder
    @State private var name = ""

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                switch rec.phase {

                case .idle:
                    TextField("movement", text: $name)
                        .textInputAutocapitalization(.never)
                    Button {
                        rec.logName = name
                        rec.startCalibration()
                    } label: {
                        Label("Calibrate", systemImage: "circle.dashed")
                            .frame(maxWidth: .infinity)
                    }
                    .tint(.blue)

                    if !rec.status.isEmpty {
                        Text(rec.status).font(.footnote).foregroundStyle(.secondary)
                    }

                case .calibrating:
                    Text("HOLD STILL").font(.headline).foregroundStyle(.yellow)
                    Text("opening anchor").font(.caption2).foregroundStyle(.secondary)
                    Text("\(rec.sampleCount) samples").font(.caption).foregroundStyle(.secondary)
                    Button("Start Set") { rec.startSet() }
                        .frame(maxWidth: .infinity).tint(.green)
                    // Discard used to call finish(), which WROTE the CSV.
                    Button("Discard") { rec.discard() }
                        .frame(maxWidth: .infinity).tint(.red)

                case .recording:
                    Text("RECORDING").font(.headline).foregroundStyle(.green)
                    Text(String(format: "%.0f s · %d", rec.elapsed, rec.sampleCount))
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Finish Set") { rec.endSet() }
                        .frame(maxWidth: .infinity).tint(.orange)

                case .settling:
                    // C1. Saves itself when the countdown reaches zero, so the
                    // lifter can rack the bar and leave the wrist alone rather
                    // than reaching for the watch — which would ruin the anchor.
                    Text("HOLD STILL").font(.headline).foregroundStyle(.yellow)
                    Text("closing anchor").font(.caption2).foregroundStyle(.secondary)
                    Text(String(format: "%.1f s", rec.settleRemaining))
                        .font(.system(.title2, design: .rounded)).monospacedDigit()
                    Text("saves itself").font(.caption2).foregroundStyle(.secondary)
                    Button("Save now") { rec.save() }
                        .frame(maxWidth: .infinity).tint(.gray)
                }

                // The keep-alive can vanish mid-set — opening the Workout app
                // during a recording preempts our session, and watchOS offers no
                // way to stop it. Core Motion then stops as soon as the wrist
                // drops and the capture truncates with no other sign, which is
                // how a session's worth of data was lost with nothing on screen
                // to say so.
                if !rec.workoutActive {
                    Label(rec.phase == .idle
                          ? "no workout — Calibrate will start one"
                          : "NO WORKOUT — will stop when your wrist drops",
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.caption2)
                        // `Color.secondary`, not `.secondary`: the bare form is
                        // a HierarchicalShapeStyle and will not unify with
                        // `.red` across a ternary.
                        .foregroundStyle(rec.phase == .idle ? Color.secondary : Color.red)
                        .multilineTextAlignment(.center)
                }
            }
            .padding()
        }
    }
}

// MARK: - Rate your effort

/// watchOS 11's workout effort score, 1-10, on Apple's own wording so the rating
/// means the same thing here as it does in the Fitness app.
///
/// Shown as a full screen rather than a sheet because it is the last thing that
/// happens in a gym session and there is nothing to go back to. Skip is a first
/// class option — an unrated workout is still a saved workout, and forcing a
/// rating would make the effort score the price of the Health record.
struct EffortView: View {
    @ObservedObject var rec: MotionRecorder
    @State private var crown = 5.0
    @FocusState private var crownFocused: Bool

    private var score: Int { Int(crown.rounded()) }

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Text("How hard was that?")
                    .font(.headline).multilineTextAlignment(.center)

                Text("\(score)")
                    .font(.system(size: 48, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(tint)
                Text(MotionRecorder.effortLabel(score))
                    .font(.caption).foregroundStyle(tint)

                // Slider AND crown, because the two suit different moments: the
                // crown without looking, the slider with sweaty hands the crown
                // will not grip. There is no TabView on this screen, so the
                // crown is free to drive the dial rather than paging.
                Slider(value: $crown, in: 1...10, step: 1)
                    .tint(tint)

                Button("Save Effort") { rec.saveEffort(score) }
                    .frame(maxWidth: .infinity).tint(.green)
                Button("Skip") { rec.skipEffort() }
                    .frame(maxWidth: .infinity).tint(.gray)
            }
            .padding()
        }
        .focusable(true)
        .focused($crownFocused)
        .digitalCrownRotation($crown, from: 1, through: 10, by: 1,
                              sensitivity: .low, isContinuous: false)
        .onAppear { crownFocused = true }
    }

    private var tint: Color {
        switch score {
        case ...3: return .blue
        case 4...6: return .green
        case 7...8: return .orange
        default: return .red
        }
    }
}

#Preview { ContentView() }

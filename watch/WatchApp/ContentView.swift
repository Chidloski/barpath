import SwiftUI
import HealthKit

/// Three screens, paged with the crown, plus an effort rating at the end.
///
/// C4 moved the workout session into this app, which meant the lifter gave up
/// starting one in the Workout app. This is the other half of that trade: if
/// they cannot use the Workout app, this has to show what the Workout app
/// showed — elapsed, heart rate, calories — and let them rate their effort
/// afterwards, or the change is a straight downgrade.
///
/// Paged rather than one long scroll because the two screens serve different
/// moments. Between sets you want the workout at a glance and nothing to press;
/// during a set you want one large button and no distraction. Scrolling past
/// live metrics to reach "Finish Set" mid-effort is exactly the wrong shape.
struct ContentView: View {
    @StateObject private var rec = MotionRecorder()
    @State private var page = 1        // start on Record: it is why the app exists

    var body: some View {
        if rec.finishedWorkout != nil {
            EffortView(rec: rec)
        } else if rec.workoutActive {
            TabView(selection: $page) {
                MetricsView(rec: rec).tag(0)
                RecordView(rec: rec).tag(1)
            }
            .tabViewStyle(.verticalPage)
        } else {
            // No session yet, so there are no metrics to page to.
            RecordView(rec: rec)
        }
    }
}

// MARK: - The workout screen

/// What the Workout app would show for a strength session, laid out for a
/// glance between sets: one dominant number (elapsed) and three supporting
/// ones, rather than the Workout app's four co-equal rows.
struct MetricsView: View {
    @ObservedObject var rec: MotionRecorder

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if let start = rec.workoutStart {
                    // `style: .timer` keeps counting without a Timer of our
                    // own, which matters because a run-loop timer may not fire
                    // once the screen sleeps and the motion callback is busy.
                    Text(start, style: .timer)
                        .font(.system(size: 44, weight: .semibold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.green)
                        .minimumScaleFactor(0.6)
                        .lineLimit(1)
                }
                Text("TRADITIONAL STRENGTH TRAINING")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)

                Divider()

                Metric(icon: "heart.fill", tint: .red,
                       value: rec.heartRate > 0 ? "\(Int(rec.heartRate))" : "--",
                       unit: "BPM", caption: rec.avgHeartRate > 0
                           ? "avg \(Int(rec.avgHeartRate))" : nil)
                Metric(icon: "flame.fill", tint: .orange,
                       value: "\(Int(rec.activeEnergy.rounded()))",
                       unit: "ACTIVE KCAL",
                       caption: "\(Int(rec.totalEnergy.rounded())) total")

                if rec.phase != .idle {
                    Divider()
                    Label("recording — swipe down", systemImage: "record.circle")
                        .font(.caption2).foregroundStyle(.green)
                }
            }
            .padding(.horizontal)
        }
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
                        .font(.system(size: 30, weight: .medium, design: .rounded))
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

// MARK: - The recording screen

struct RecordView: View {
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

                    // C4. watchOS allows exactly one workout session on the
                    // device, so this app and the Workout app cannot both hold
                    // one — starting ours used to end theirs, invisibly, on
                    // every Calibrate. The session is now started here on
                    // purpose and saved to Health on End, so it replaces the
                    // Workout app for a lifting session rather than fighting it.
                    // See the HealthKit section of MotionRecorder.swift.
                    if rec.workoutActive {
                        Button("End Workout & Save", role: .destructive) { rec.endWorkout() }
                            .frame(maxWidth: .infinity)
                        Text("swipe up for heart rate and calories")
                            .font(.caption2).foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    } else {
                        Button {
                            rec.startWorkout()
                        } label: {
                            Label("Start Workout", systemImage: "figure.strengthtraining.traditional")
                                .frame(maxWidth: .infinity)
                        }
                        .tint(.pink)
                        Text("start it here, not in the Workout app")
                            .font(.caption2).foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }

                    if !rec.status.isEmpty {
                        Text(rec.status).font(.footnote).foregroundStyle(.secondary)
                    }

                    // The experiment that could delete the whole C4 workflow
                    // change. Off by default and last on the screen, because
                    // switching it on is expected to ruin the capture — see
                    // MotionRecorder.sessionlessTest.
                    Divider()
                    Toggle(isOn: $rec.sessionlessTest) {
                        Text("Test: no workout session")
                            .font(.caption2)
                    }
                    .tint(.orange)
                    if rec.sessionlessTest {
                        Text("Calibrate will NOT keep the app alive. Expect the "
                             + "capture to truncate when your wrist drops — that "
                             + "is the result. Do not use it as lifting data.")
                            .font(.caption2).foregroundStyle(.orange)
                            .multilineTextAlignment(.center)
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

                // The keep-alive can vanish mid-set — the Workout app being
                // opened during a recording preempts our session, and watchOS
                // offers no way to stop it. Core Motion then stops as soon as
                // the wrist drops and the capture truncates with no other sign.
                // Before the session had a delegate this was completely silent.
                if rec.phase != .idle && !rec.workoutActive {
                    Text("NO WORKOUT — may stop early")
                        .font(.caption2).foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                }
            }
            .padding()
        }
    }
}

// MARK: - Rate your effort

/// watchOS 11's workout effort score, 1-10, on Apple's own wording so the
/// rating means the same thing here as it does in the Fitness app.
///
/// Shown as a full screen rather than a sheet because it is the last thing that
/// happens in a gym session and there is nothing to go back to. Skip is a first
/// class option — an unrated workout is still a saved workout, and forcing a
/// rating would make the effort score the price of the Health record.
struct EffortView: View {
    @ObservedObject var rec: MotionRecorder
    @State private var score = 5
    @State private var crown = 5.0
    @FocusState private var crownFocused: Bool

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text("How hard was that?")
                    .font(.headline).multilineTextAlignment(.center)

                Text("\(score)")
                    .font(.system(size: 52, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(tint)
                Text(MotionRecorder.effortLabel(score))
                    .font(.caption).foregroundStyle(tint)

                // Slider AND crown, because the two suit different moments: the
                // crown without looking, the slider with sweaty hands that the
                // crown will not grip. There is no TabView on this screen, so
                // the crown is free to drive the dial rather than paging.
                Slider(value: $crown, in: 1...10, step: 1)
                    .tint(tint)

                Button("Save Effort") { rec.saveEffort(score) }
                    .frame(maxWidth: .infinity).tint(.green)
                Button("Skip") { rec.finishedWorkout = nil }
                    .frame(maxWidth: .infinity).tint(.gray)
            }
            .padding()
        }
        .focusable(true)
        .focused($crownFocused)
        .digitalCrownRotation($crown, from: 1, through: 10, by: 1,
                              sensitivity: .low, isContinuous: false)
        .onAppear { crownFocused = true }
        .onChange(of: crown) { _, new in score = Int(new.rounded()) }
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

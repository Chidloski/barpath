import SwiftUI

struct ContentView: View {
    @StateObject private var rec = MotionRecorder()
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
                        Text("workout running — this app owns it")
                            .font(.caption2).foregroundStyle(.green)
                        Button("End Workout & Save", role: .destructive) { rec.endWorkout() }
                            .frame(maxWidth: .infinity)
                    } else {
                        Button("Start Workout") { rec.startWorkout() }
                            .frame(maxWidth: .infinity).tint(.pink)
                        Text("start it here, not in the Workout app")
                            .font(.caption2).foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }

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

#Preview { ContentView() }

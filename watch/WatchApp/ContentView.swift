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
                    if rec.workoutActive {
                        Button("End Workout", role: .destructive) { rec.endWorkout() }
                            .frame(maxWidth: .infinity)
                    }
                    if !rec.status.isEmpty {
                        Text(rec.status).font(.footnote).foregroundStyle(.secondary)
                    }

                case .calibrating:
                    Text("HOLD STILL").font(.headline).foregroundStyle(.yellow)
                    Text("opening anchor").font(.caption2).foregroundStyle(.secondary)
                    Text("\(rec.sampleCount) samples").font(.caption).foregroundStyle(.secondary)
                    RawGyroBadge(ok: rec.rawGyroOK)
                    Button("Start Set") { rec.startSet() }
                        .frame(maxWidth: .infinity).tint(.green)
                    // Discard used to call finish(), which WROTE the CSV.
                    Button("Discard") { rec.discard() }
                        .frame(maxWidth: .infinity).tint(.red)

                case .recording:
                    Text("RECORDING").font(.headline).foregroundStyle(.green)
                    Text(String(format: "%.0f s · %d", rec.elapsed, rec.sampleCount))
                        .font(.caption).foregroundStyle(.secondary)
                    RawGyroBadge(ok: rec.rawGyroOK)
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
            }
            .padding()
        }
    }
}

/// Whether C2's raw-gyro stream is actually delivering. Shown while recording so
/// a silent failure is visible in the gym rather than discovered in the CSV that
/// evening — the four raw columns are optional on the Python side, so nothing
/// downstream would complain about their absence either.
private struct RawGyroBadge: View {
    let ok: Bool
    var body: some View {
        Label(ok ? "raw gyro" : "NO raw gyro",
              systemImage: ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
            .font(.caption2)
            .foregroundStyle(ok ? .green : .orange)
    }
}

#Preview { ContentView() }

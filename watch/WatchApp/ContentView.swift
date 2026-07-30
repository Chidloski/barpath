import SwiftUI

/// One screen. Four states, one button that matters in each.
///
/// This briefly grew a paged TabView with a live workout screen and an effort
/// rating, because holding an `HKWorkoutSession` meant taking the device's only
/// one and the app had to give back what the Workout app provided. Measurement
/// removed the session (see `MotionRecorder`, C7), and the screens went with it:
/// they existed to compensate for a cost that turned out not to be necessary,
/// not because a barbell logger needs to show a heart rate.
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
            }
            .padding()
        }
    }
}

#Preview { ContentView() }

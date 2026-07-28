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
                    Text("\(rec.sampleCount) samples").font(.caption).foregroundStyle(.secondary)
                    Button("Start Set") { rec.startSet() }
                        .frame(maxWidth: .infinity).tint(.green)
                    Button("Discard") { rec.finish() }
                        .frame(maxWidth: .infinity).tint(.red)

                case .recording:
                    Text("RECORDING").font(.headline).foregroundStyle(.green)
                    Text(String(format: "%.0f s · %d", rec.elapsed, rec.sampleCount))
                        .font(.caption).foregroundStyle(.secondary)
                    Button("Finish Set") { rec.finish() }
                        .frame(maxWidth: .infinity).tint(.red)
                }
            }
            .padding()
        }
    }
}

#Preview { ContentView() }

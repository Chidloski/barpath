import SwiftUI

struct ContentView: View {
    @StateObject private var conn = PhoneConnectivity()

    var body: some View {
        NavigationStack {
            List {
                if conn.logs.isEmpty {
                    Text("No logs yet.\nRecord a set on the watch — it appears here, and in Files → On My iPhone → BarpathLogger.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(conn.logs, id: \.self) { url in
                        ShareLink(item: url) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(url.lastPathComponent).font(.body)
                                Text(sizeString(url)).font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .navigationTitle("barpath logs")
            .toolbar {
                Button {
                    conn.refresh()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
    }

    private func sizeString(_ url: URL) -> String {
        let bytes = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        return ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }
}

#Preview { ContentView() }

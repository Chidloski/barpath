import Foundation
import WatchConnectivity

/// Receives finished logs from the watch and writes them into Documents,
/// which (with UIFileSharingEnabled) is exposed to the Files app.
final class PhoneConnectivity: NSObject, ObservableObject, WCSessionDelegate {

    @Published var logs: [URL] = []

    override init() {
        super.init()
        // Skip WatchConnectivity in SwiftUI previews (no session there).
        if ProcessInfo.processInfo.environment["XCODE_RUNNING_FOR_PREVIEWS"] != "1",
           WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        refresh()
    }

    private var documents: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    func refresh() {
        let found = (try? FileManager.default.contentsOfDirectory(
            at: documents, includingPropertiesForKeys: nil)) ?? []
        logs = found.filter { $0.pathExtension == "csv" }
            .sorted { $0.lastPathComponent > $1.lastPathComponent }
    }

    // MARK: WCSessionDelegate

    func session(_ session: WCSession,
                 activationDidCompleteWith state: WCSessionActivationState,
                 error: Error?) {}

    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        // Reactivate to keep receiving after a watch switch.
        WCSession.default.activate()
    }

    func session(_ session: WCSession, didReceive file: WCSessionFile) {
        // file.fileURL is a temporary location — copy it out synchronously,
        // here, before this method returns, or the system reclaims it.
        let name = (file.metadata?["name"] as? String) ?? file.fileURL.lastPathComponent
        let dest = documents.appendingPathComponent(name)
        try? FileManager.default.removeItem(at: dest)
        do {
            try FileManager.default.copyItem(at: file.fileURL, to: dest)
        } catch {
            print("failed to save received log: \(error)")
        }
        DispatchQueue.main.async { self.refresh() }
    }
}

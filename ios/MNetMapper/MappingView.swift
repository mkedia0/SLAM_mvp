import SwiftUI

struct MappingView: View {
    @EnvironmentObject private var store: MappingStore
    @State private var mapName = "Roborock warehouse lap"

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    hero
                    arCapturePanel
                    currentStats
                    mapHistory
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Mapping")
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("ARKit-first warehouse proof of concept")
                .font(.title2.bold())
            Text("Mount the iPhone on the roborock, start a lap, and repeat the same environment as many times as needed for loop closure confidence.")
                .foregroundStyle(.secondary)
            HStack {
                TextField("Environment name", text: $mapName)
                    .textFieldStyle(.roundedBorder)
                Button {
                    store.startNewMap(named: mapName)
                } label: {
                    Label("Start", systemImage: "record.circle")
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
    }

    private var arCapturePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading) {
                    Text(store.isMapping ? "Live AR capture" : "Ready to map")
                        .font(.headline)
                    Text(store.activeMap?.name ?? "No active lap")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if store.isMapping {
                    Button(role: .destructive) {
                        store.stopMapping()
                    } label: {
                        Label("Stop", systemImage: "stop.circle")
                    }
                    .buttonStyle(.bordered)
                }
            }

            ZStack(alignment: .bottomLeading) {
                ARWarehouseCaptureView()
                    .environmentObject(store)
                    .frame(height: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                HStack(spacing: 10) {
                    StatusBadge(title: "Queued", value: "\(store.frameQueue.count)")
                    StatusBadge(title: "Tracking", value: store.frameQueue.last?.trackingState ?? "waiting")
                }
                .padding(12)
            }
        }
    }

    private var currentStats: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
            MetricTile(title: "Frames", value: "\(store.activeMap?.frameCount ?? store.frameQueue.count)", symbol: "photo.stack")
            MetricTile(title: "Passes", value: "\(store.activeMap?.passes ?? 0)", symbol: "arrow.triangle.2.circlepath")
            MetricTile(title: "Distance", value: String(format: "%.1f m", store.activeMap?.distanceMeters ?? 0), symbol: "ruler")
            MetricTile(title: "Loops", value: "\(store.activeMap?.loopClosures ?? 0)", symbol: "point.3.connected.trianglepath.dotted")
        }
    }

    private var mapHistory: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Environment maps")
                .font(.headline)
            ForEach(store.maps) { map in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(map.name).font(.headline)
                        Spacer()
                        Text(map.status.rawValue).foregroundStyle(statusColor(map.status))
                    }
                    HStack {
                        Label("\(map.passes) passes", systemImage: "arrow.triangle.2.circlepath")
                        Label("\(map.frameCount) frames", systemImage: "photo.stack")
                        Label(String(format: "%.1f m", map.distanceMeters), systemImage: "ruler")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    HStack {
                        Button("Repeat Map") { store.repeatMap(map) }
                        Button("Queue Processing") { store.queueProcessing(for: map) }
                    }
                    .buttonStyle(.bordered)
                }
                .padding()
                .background(.background, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func statusColor(_ status: MapStatus) -> Color {
        switch status {
        case .queued: return .secondary
        case .mapping: return .blue
        case .processing: return .orange
        case .complete: return .green
        }
    }
}

struct MetricTile: View {
    let title: String
    let value: String
    let symbol: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: symbol).foregroundStyle(.blue)
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.bold()).monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.background, in: RoundedRectangle(cornerRadius: 8))
    }
}

struct StatusBadge: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption2).foregroundStyle(.white.opacity(0.75))
            Text(value).font(.caption.bold()).foregroundStyle(.white)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(.black.opacity(0.6), in: Capsule())
    }
}

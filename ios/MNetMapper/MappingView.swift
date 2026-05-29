import SwiftUI

struct MappingView: View {
    @EnvironmentObject private var store: MappingStore
    @State private var mapName = "New environment"

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("Map name", text: $mapName)
                    Button {
                        store.startNewMap(named: mapName)
                    } label: {
                        Label("Start Mapping", systemImage: "record.circle")
                    }
                }

                Section("Environment Maps") {
                    ForEach(store.maps) { map in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(map.name)
                                    .font(.headline)
                                Spacer()
                                Text(map.status.rawValue)
                                    .foregroundStyle(statusColor(map.status))
                            }
                            HStack {
                                Label("\(map.passes) passes", systemImage: "arrow.triangle.2.circlepath")
                                Label("\(map.frameCount) frames", systemImage: "photo.stack")
                                Label("\(map.loopClosures) loops", systemImage: "point.3.connected.trianglepath.dotted")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            HStack {
                                Button("Repeat Map") {
                                    store.repeatMap(map)
                                }
                                Button("Queue Processing") {
                                    store.queueProcessing(for: map)
                                }
                            }
                            .buttonStyle(.bordered)
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
            .navigationTitle("Mapping")
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

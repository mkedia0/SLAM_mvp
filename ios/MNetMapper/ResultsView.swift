import SwiftUI

struct ResultsView: View {
    @EnvironmentObject private var store: MappingStore

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Tracked item coordinates")
                            .font(.title2.bold())
                        Text("Every detected item is reported with label, confidence, timestamp, map name, and XYZ position in meters relative to the AR world origin.")
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 12)], spacing: 12) {
                        ForEach(store.trackedItems) { item in
                            VStack(alignment: .leading, spacing: 10) {
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(item.label).font(.headline)
                                        Text(item.mapName).font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text("\(Int(item.confidence * 100))%")
                                        .font(.headline.monospacedDigit())
                                }
                                HStack {
                                    CoordinateBadge(axis: "x", value: item.x)
                                    CoordinateBadge(axis: "y", value: item.y)
                                    CoordinateBadge(axis: "z", value: item.z)
                                }
                                Text(item.timestamp, format: .dateTime.hour().minute().second())
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding()
                            .background(.background, in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Results")
        }
    }
}

struct CoordinateBadge: View {
    let axis: String
    let value: Double

    var body: some View {
        Text("\(axis): \(value, specifier: "%.2f") m")
            .font(.caption)
            .monospacedDigit()
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(.gray.opacity(0.14), in: Capsule())
    }
}

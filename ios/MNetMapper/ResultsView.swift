import SwiftUI

struct ResultsView: View {
    @EnvironmentObject private var store: MappingStore

    var body: some View {
        NavigationStack {
            List {
                Section("Tracked Items") {
                    ForEach(store.trackedItems) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(item.label)
                                    .font(.headline)
                                Spacer()
                                Text("\(Int(item.confidence * 100))%")
                                    .monospacedDigit()
                            }
                            Text(item.mapName)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack {
                                CoordinateBadge(axis: "x", value: item.x)
                                CoordinateBadge(axis: "y", value: item.y)
                                CoordinateBadge(axis: "z", value: item.z)
                            }
                            Text(item.timestamp, style: .time)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
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

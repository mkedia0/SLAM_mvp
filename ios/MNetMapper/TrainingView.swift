import SwiftUI

struct TrainingView: View {
    @EnvironmentObject private var store: MappingStore
    @State private var newLabel = ""

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Teach any warehouse object")
                            .font(.title2.bold())
                        Text("Create niche labels for mock inventory, shelf markers, totes, bins, or any odd-shaped item. Demo capture increments examples now; model training can later plug into Create ML/Core ML.")
                            .foregroundStyle(.secondary)
                        HStack {
                            TextField("New label", text: $newLabel)
                                .textFieldStyle(.roundedBorder)
                            Button {
                                let label = newLabel.trimmingCharacters(in: .whitespacesAndNewlines)
                                guard !label.isEmpty else { return }
                                store.addTrainingLabel(label)
                                newLabel = ""
                            } label: {
                                Label("Add", systemImage: "plus.circle")
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))

                    ForEach(store.trainingSets) { set in
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(set.label).font(.headline)
                                    Text("Updated \(set.updatedAt, style: .relative) ago")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text("\(set.examples)")
                                    .font(.title2.bold())
                                    .monospacedDigit()
                            }
                            ProgressView(value: min(1, Double(set.examples) / 50.0))
                            HStack {
                                Label("\(Int(set.confidenceTarget * 100))% target", systemImage: "scope")
                                Spacer()
                                Button("Capture Example") { store.addTrainingExample(for: set) }
                                Button("Train") { }
                            }
                            .font(.caption)
                            .buttonStyle(.bordered)
                        }
                        .padding()
                        .background(.background, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Training")
        }
    }
}

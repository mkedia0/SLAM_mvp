import SwiftUI

struct TrainingView: View {
    @EnvironmentObject private var store: MappingStore
    @State private var newLabel = ""

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("Object label", text: $newLabel)
                    Button {
                        guard !newLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                        store.addTrainingLabel(newLabel)
                        newLabel = ""
                    } label: {
                        Label("Create Object Class", systemImage: "plus.circle")
                    }
                }

                Section("Trainable Objects") {
                    ForEach(store.trainingSets) { set in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(set.label)
                                .font(.headline)
                            HStack {
                                Label("\(set.examples) examples", systemImage: "camera.viewfinder")
                                Label("\(Int(set.confidenceTarget * 100))% target", systemImage: "scope")
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            HStack {
                                Button("Capture Examples") {}
                                Button("Import Photos") {}
                                Button("Train") {}
                            }
                            .buttonStyle(.bordered)
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
            .navigationTitle("Training")
        }
    }
}

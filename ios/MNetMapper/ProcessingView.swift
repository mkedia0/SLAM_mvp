import SwiftUI

struct ProcessingView: View {
    @EnvironmentObject private var store: MappingStore

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Frame queue and reconstruction")
                            .font(.title2.bold())
                        Text("ARKit feeds live poses and scene depth. Frames are queued so the roborock lap can finish cleanly even when labeling and map fusion run behind capture.")
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))

                    WarehouseMapPreview(samples: store.frameQueue, labels: store.warehouseLabels)

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Processing jobs")
                            .font(.headline)
                        ForEach(store.jobs) { job in
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Text(job.mapName).font(.headline)
                                    Spacer()
                                    Text("\(job.processedFrames)/\(job.queuedFrames)")
                                        .monospacedDigit()
                                        .foregroundStyle(.secondary)
                                }
                                ProgressView(value: job.progress)
                                LabelCloud(labels: job.detectedLabels)
                            }
                            .padding()
                            .background(.background, in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Processing")
        }
    }
}

struct LabelCloud: View {
    let labels: [String]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 112), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(labels, id: \.self) { label in
                Text(label)
                    .font(.caption)
                    .lineLimit(1)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .background(.blue.opacity(0.12), in: Capsule())
            }
        }
    }
}

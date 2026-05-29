import SwiftUI

struct ProcessingView: View {
    @EnvironmentObject private var store: MappingStore

    var body: some View {
        NavigationStack {
            List {
                Section("Frame Queue") {
                    ForEach(store.jobs) { job in
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Text(job.mapName)
                                    .font(.headline)
                                Spacer()
                                Text("\(job.processedFrames)/\(job.queuedFrames)")
                                    .monospacedDigit()
                                    .foregroundStyle(.secondary)
                            }
                            ProgressView(value: job.progress)
                            if job.detectedLabels.isEmpty {
                                Text("No labels identified yet")
                                    .foregroundStyle(.secondary)
                            } else {
                                LabelCloud(labels: job.detectedLabels)
                            }
                        }
                        .padding(.vertical, 6)
                    }
                }

                Section("3D Map Preview") {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(.black.opacity(0.88))
                            .frame(height: 260)
                        VStack(spacing: 10) {
                            Image(systemName: "cube.transparent")
                                .font(.system(size: 42))
                            Text("Point cloud and labeled item preview")
                                .font(.headline)
                            Text("ARKit path can stream live depth; non-ARKit path queues RGB/depth frames for backend processing.")
                                .multilineTextAlignment(.center)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal)
                        }
                        .foregroundStyle(.white)
                    }
                }
            }
            .navigationTitle("Processing")
        }
    }
}

struct LabelCloud: View {
    let labels: [String]

    var body: some View {
        FlowLayout(items: labels) { label in
            Text(label)
                .font(.caption)
                .padding(.horizontal, 8)
                .padding(.vertical, 5)
                .background(.blue.opacity(0.12), in: Capsule())
        }
    }
}

struct FlowLayout<Data: RandomAccessCollection, Content: View>: View where Data.Element: Hashable {
    let items: Data
    let content: (Data.Element) -> Content

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], alignment: .leading, spacing: 8) {
            ForEach(Array(items), id: \.self) { item in
                content(item)
            }
        }
    }
}

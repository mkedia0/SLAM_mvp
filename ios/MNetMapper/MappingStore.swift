import Foundation

@MainActor
final class MappingStore: ObservableObject {
    @Published var maps: [EnvironmentMap] = [
        EnvironmentMap(name: "Grocery aisle pass A", status: .complete, passes: 2, frameCount: 270, loopClosures: 1),
        EnvironmentMap(name: "Stock room baseline", status: .processing, passes: 1, frameCount: 118, loopClosures: 0)
    ]

    @Published var trainingSets: [ObjectTrainingSet] = [
        ObjectTrainingSet(label: "Organic Fuji Apple", examples: 42),
        ObjectTrainingSet(label: "Shelf tag - weekly sale", examples: 18),
        ObjectTrainingSet(label: "Private-label oat milk", examples: 31)
    ]

    @Published var jobs: [ProcessingJob] = [
        ProcessingJob(
            id: UUID(),
            mapName: "Stock room baseline",
            queuedFrames: 180,
            processedFrames: 118,
            detectedLabels: ["cart", "case stack", "pallet label"]
        )
    ]

    @Published var trackedItems: [TrackedItem] = [
        TrackedItem(id: UUID(), label: "Organic Fuji Apple", timestamp: Date(), x: 1.24, y: 0.82, z: -3.18, confidence: 0.93, mapName: "Grocery aisle pass A"),
        TrackedItem(id: UUID(), label: "Private-label oat milk", timestamp: Date(), x: -0.38, y: 1.12, z: -4.41, confidence: 0.88, mapName: "Grocery aisle pass A"),
        TrackedItem(id: UUID(), label: "Shelf tag - weekly sale", timestamp: Date(), x: 0.92, y: 1.46, z: -2.74, confidence: 0.91, mapName: "Grocery aisle pass A")
    ]

    func startNewMap(named name: String) {
        maps.insert(EnvironmentMap(name: name, status: .mapping), at: 0)
    }

    func repeatMap(_ map: EnvironmentMap) {
        guard let index = maps.firstIndex(where: { $0.id == map.id }) else { return }
        maps[index].passes += 1
        maps[index].status = .mapping
    }

    func addTrainingLabel(_ label: String) {
        trainingSets.insert(ObjectTrainingSet(label: label, examples: 0), at: 0)
    }

    func queueProcessing(for map: EnvironmentMap) {
        jobs.insert(
            ProcessingJob(id: UUID(), mapName: map.name, queuedFrames: map.frameCount, processedFrames: 0, detectedLabels: []),
            at: 0
        )
    }
}

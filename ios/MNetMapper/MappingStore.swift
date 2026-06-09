import Foundation
import SwiftUI
import simd

@MainActor
final class MappingStore: ObservableObject {
    @Published var maps: [EnvironmentMap] = [
        EnvironmentMap(name: "Mock warehouse loop", status: .complete, passes: 2, frameCount: 270, loopClosures: 1, distanceMeters: 8.6, lastPose: Vector3(x: 0.18, y: 0.93, z: -0.22)),
        EnvironmentMap(name: "Shelf aisle baseline", status: .processing, passes: 1, frameCount: 118, loopClosures: 0, distanceMeters: 3.4, lastPose: Vector3(x: -0.42, y: 0.91, z: -2.9))
    ]

    @Published var trainingSets: [ObjectTrainingSet] = [
        ObjectTrainingSet(label: "Red cube bin", examples: 42),
        ObjectTrainingSet(label: "Blue cylinder tote", examples: 18),
        ObjectTrainingSet(label: "Yellow pallet block", examples: 31)
    ]

    @Published var jobs: [ProcessingJob] = [
        ProcessingJob(
            id: UUID(),
            mapName: "Shelf aisle baseline",
            queuedFrames: 180,
            processedFrames: 118,
            detectedLabels: ["red cube bin", "blue cylinder tote", "yellow pallet block"]
        )
    ]

    @Published var trackedItems: [TrackedItem] = [
        TrackedItem(id: UUID(), label: "Red cube bin", timestamp: Date(), x: 1.24, y: 0.82, z: -3.18, confidence: 0.93, mapName: "Mock warehouse loop"),
        TrackedItem(id: UUID(), label: "Blue cylinder tote", timestamp: Date(), x: -0.38, y: 1.12, z: -4.41, confidence: 0.88, mapName: "Mock warehouse loop"),
        TrackedItem(id: UUID(), label: "Yellow pallet block", timestamp: Date(), x: 0.92, y: 1.46, z: -2.74, confidence: 0.91, mapName: "Mock warehouse loop")
    ]

    @Published var currentMapID: EnvironmentMap.ID?
    @Published var isMapping = false
    @Published var frameQueue: [ARFrameSample] = []
    @Published var warehouseLabels: [WarehouseLabel] = [
        WarehouseLabel(title: "Red cube bin", position: Vector3(x: 1.24, y: 0.82, z: -3.18), confidence: 0.93, color: .red),
        WarehouseLabel(title: "Blue cylinder tote", position: Vector3(x: -0.38, y: 1.12, z: -4.41), confidence: 0.88, color: .blue),
        WarehouseLabel(title: "Yellow pallet block", position: Vector3(x: 0.92, y: 1.46, z: -2.74), confidence: 0.91, color: .yellow)
    ]

    var activeMap: EnvironmentMap? {
        guard let currentMapID else { return nil }
        return maps.first { $0.id == currentMapID }
    }

    func startNewMap(named name: String) {
        let map = EnvironmentMap(name: name, status: .mapping)
        maps.insert(map, at: 0)
        currentMapID = map.id
        isMapping = true
        frameQueue.removeAll()
    }

    func repeatMap(_ map: EnvironmentMap) {
        guard let index = maps.firstIndex(where: { $0.id == map.id }) else { return }
        maps[index].passes += 1
        maps[index].status = .mapping
        currentMapID = map.id
        isMapping = true
        frameQueue.removeAll()
    }

    func stopMapping() {
        guard let id = currentMapID, let index = maps.firstIndex(where: { $0.id == id }) else {
            isMapping = false
            return
        }
        maps[index].status = .processing
        queueProcessing(for: maps[index])
        isMapping = false
    }

    func addTrainingLabel(_ label: String) {
        trainingSets.insert(ObjectTrainingSet(label: label, examples: 0), at: 0)
    }

    func addTrainingExample(for set: ObjectTrainingSet) {
        guard let index = trainingSets.firstIndex(where: { $0.id == set.id }) else { return }
        trainingSets[index].examples += 1
        trainingSets[index].updatedAt = Date()
    }

    func queueProcessing(for map: EnvironmentMap) {
        jobs.insert(
            ProcessingJob(
                id: UUID(),
                mapName: map.name,
                queuedFrames: max(map.frameCount, frameQueue.count),
                processedFrames: min(frameQueue.count, max(map.frameCount, frameQueue.count)),
                detectedLabels: trainingSets.map(\.label)
            ),
            at: 0
        )
    }

    func recordARFrame(cameraTransform: simd_float4x4, trackingState: String) {
        guard isMapping, let id = currentMapID, let index = maps.firstIndex(where: { $0.id == id }) else { return }
        let translation = SIMD3<Float>(
            cameraTransform.columns.3.x,
            cameraTransform.columns.3.y,
            cameraTransform.columns.3.z
        )
        let pose = Vector3(translation)
        let sample = ARFrameSample(pose: pose, trackingState: trackingState)
        frameQueue.append(sample)
        maps[index].frameCount += 1
        maps[index].lastPose = pose
        maps[index].distanceMeters = estimatedDistance()
        if maps[index].frameCount > 120 && abs(pose.x) < 0.35 && abs(pose.z) < 0.35 {
            maps[index].loopClosures = max(maps[index].loopClosures, 1)
        }
        synthesizeDetectionIfNeeded(from: pose, mapName: maps[index].name)
    }

    private func estimatedDistance() -> Double {
        guard frameQueue.count > 1 else { return 0 }
        let points = frameQueue.map(\.pose)
        return zip(points, points.dropFirst()).reduce(0) { total, pair in
            let dx = pair.1.x - pair.0.x
            let dy = pair.1.y - pair.0.y
            let dz = pair.1.z - pair.0.z
            return total + sqrt(dx * dx + dy * dy + dz * dz)
        }
    }

    private func synthesizeDetectionIfNeeded(from pose: Vector3, mapName: String) {
        guard frameQueue.count % 45 == 0, let label = trainingSets.randomElement()?.label else { return }
        let item = TrackedItem(
            id: UUID(),
            label: label,
            timestamp: Date(),
            x: pose.x + Double.random(in: -0.35...0.35),
            y: max(0.15, pose.y + Double.random(in: -0.12...0.12)),
            z: pose.z - Double.random(in: 0.4...1.2),
            confidence: Double.random(in: 0.82...0.96),
            mapName: mapName
        )
        trackedItems.insert(item, at: 0)
        warehouseLabels.insert(
            WarehouseLabel(
                title: item.label,
                position: Vector3(x: item.x, y: item.y, z: item.z),
                confidence: item.confidence,
                color: [.red, .blue, .yellow, .green, .purple].randomElement() ?? .cyan
            ),
            at: 0
        )
    }
}

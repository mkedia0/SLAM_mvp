import Foundation
import SwiftUI
import simd

struct EnvironmentMap: Identifiable, Hashable {
    let id: UUID
    var name: String
    var startedAt: Date
    var status: MapStatus
    var passes: Int
    var frameCount: Int
    var loopClosures: Int
    var distanceMeters: Double
    var lastPose: Vector3

    init(
        id: UUID = UUID(),
        name: String,
        startedAt: Date = Date(),
        status: MapStatus = .queued,
        passes: Int = 1,
        frameCount: Int = 0,
        loopClosures: Int = 0,
        distanceMeters: Double = 0,
        lastPose: Vector3 = .zero
    ) {
        self.id = id
        self.name = name
        self.startedAt = startedAt
        self.status = status
        self.passes = passes
        self.frameCount = frameCount
        self.loopClosures = loopClosures
        self.distanceMeters = distanceMeters
        self.lastPose = lastPose
    }
}

enum MapStatus: String, CaseIterable {
    case queued = "Queued"
    case mapping = "Mapping"
    case processing = "Processing"
    case complete = "Complete"
}

struct ObjectTrainingSet: Identifiable, Hashable {
    let id: UUID
    var label: String
    var examples: Int
    var confidenceTarget: Double
    var updatedAt: Date

    init(id: UUID = UUID(), label: String, examples: Int, confidenceTarget: Double = 0.85, updatedAt: Date = Date()) {
        self.id = id
        self.label = label
        self.examples = examples
        self.confidenceTarget = confidenceTarget
        self.updatedAt = updatedAt
    }
}

struct ProcessingJob: Identifiable, Hashable {
    let id: UUID
    var mapName: String
    var queuedFrames: Int
    var processedFrames: Int
    var detectedLabels: [String]

    var progress: Double {
        guard queuedFrames > 0 else { return 0 }
        return min(1, Double(processedFrames) / Double(queuedFrames))
    }
}

struct TrackedItem: Identifiable, Hashable {
    let id: UUID
    var label: String
    var timestamp: Date
    var x: Double
    var y: Double
    var z: Double
    var confidence: Double
    var mapName: String
}

struct Vector3: Hashable {
    var x: Double
    var y: Double
    var z: Double

    static let zero = Vector3(x: 0, y: 0, z: 0)

    init(x: Double, y: Double, z: Double) {
        self.x = x
        self.y = y
        self.z = z
    }

    init(_ value: SIMD3<Float>) {
        self.x = Double(value.x)
        self.y = Double(value.y)
        self.z = Double(value.z)
    }
}

struct ARFrameSample: Identifiable, Hashable {
    let id: UUID
    var timestamp: Date
    var pose: Vector3
    var trackingState: String
    var queuedForProcessing: Bool

    init(id: UUID = UUID(), timestamp: Date = Date(), pose: Vector3, trackingState: String, queuedForProcessing: Bool = true) {
        self.id = id
        self.timestamp = timestamp
        self.pose = pose
        self.trackingState = trackingState
        self.queuedForProcessing = queuedForProcessing
    }
}

struct WarehouseLabel: Identifiable, Hashable {
    let id: UUID
    var title: String
    var position: Vector3
    var confidence: Double
    var color: Color

    init(id: UUID = UUID(), title: String, position: Vector3, confidence: Double, color: Color = .cyan) {
        self.id = id
        self.title = title
        self.position = position
        self.confidence = confidence
        self.color = color
    }
}

import Foundation
import SwiftUI

struct EnvironmentMap: Identifiable, Hashable {
    let id: UUID
    var name: String
    var startedAt: Date
    var status: MapStatus
    var passes: Int
    var frameCount: Int
    var loopClosures: Int

    init(
        id: UUID = UUID(),
        name: String,
        startedAt: Date = Date(),
        status: MapStatus = .queued,
        passes: Int = 1,
        frameCount: Int = 0,
        loopClosures: Int = 0
    ) {
        self.id = id
        self.name = name
        self.startedAt = startedAt
        self.status = status
        self.passes = passes
        self.frameCount = frameCount
        self.loopClosures = loopClosures
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

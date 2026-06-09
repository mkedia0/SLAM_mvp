import ARKit
import RealityKit
import SwiftUI

struct ARWarehouseCaptureView: UIViewRepresentable {
    @EnvironmentObject private var store: MappingStore

    func makeCoordinator() -> Coordinator {
        Coordinator(store: store)
    }

    func makeUIView(context: Context) -> ARView {
        let view = ARView(frame: .zero)
        view.automaticallyConfigureSession = false
        view.session.delegate = context.coordinator
        runSession(on: view)
        return view
    }

    func updateUIView(_ view: ARView, context: Context) {
        context.coordinator.store = store
        if store.isMapping && view.session.currentFrame == nil {
            runSession(on: view)
        }
    }

    private func runSession(on view: ARView) {
        let configuration = ARWorldTrackingConfiguration()
        configuration.planeDetection = [.horizontal, .vertical]
        configuration.environmentTexturing = .automatic
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            configuration.frameSemantics.insert(.sceneDepth)
        }
        if ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) {
            configuration.sceneReconstruction = .mesh
        }
        view.session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
        view.debugOptions = [.showFeaturePoints, .showSceneUnderstanding]
    }

    final class Coordinator: NSObject, ARSessionDelegate {
        var store: MappingStore
        private var lastTimestamp: TimeInterval = 0

        init(store: MappingStore) {
            self.store = store
        }

        func session(_ session: ARSession, didUpdate frame: ARFrame) {
            guard frame.timestamp - lastTimestamp > 0.2 else { return }
            lastTimestamp = frame.timestamp
            let state: String
            switch frame.camera.trackingState {
            case .normal:
                state = "normal"
            case .notAvailable:
                state = "not available"
            case .limited(let reason):
                state = "limited: \(reason)"
            }
            let transform = frame.camera.transform
            Task { @MainActor in
                store.recordARFrame(cameraTransform: transform, trackingState: state)
            }
        }
    }
}

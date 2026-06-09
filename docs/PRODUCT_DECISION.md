# Product Direction: ARKit-First Proof Of Concept

Decision: focus on ARKit integration for the App Store proof of concept.

Reasoning:

- The demo hardware is an iPhone mounted on a roborock, so ARKit world tracking and scene depth are the fastest way to capture a usable lap.
- App Store review needs a complete, understandable app. A polished ARKit demo with local queueing is more reviewable than a backend-dependent research system.
- The Python backend remains useful for offline processing, but the iOS app should not depend on RTAB-Map or Linux infrastructure for its first release.

First releasable scope:

- Mapping: start a named roborock lap, record ARKit poses/depth, repeat the same environment for better coverage.
- Training: create niche object labels and collect example counts for a future Core ML/Create ML detector.
- Processing: queue frames, show map reconstruction, and overlay labels in a top-down 3D-ish view.
- Results: list every tracked item with label, confidence, timestamp, map name, and XYZ coordinates.

Deferred scope:

- Full backend compatibility with RTAB-Map/ORB-SLAM3.
- Production object detector training pipeline.
- Server-side multi-session fusion.
- Dense mesh export and large warehouse-scale persistence.

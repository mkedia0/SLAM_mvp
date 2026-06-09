# mNET RGBD-SLAM MVP

This is a 24-hour MVP for testing Record3D/iPhone LiDAR-style RGBD runs and robot RGBD runs through one shared pipeline.

It is intentionally backend-swappable:

- Current backend: CPU Python/OpenCV RGBD visual odometry, keyframes, confidence-weighted depth correspondences, visual place recognition, loop edges, lightweight pose-graph relaxation.
- Intended production backend: RTAB-Map on Linux when available, or ORB-SLAM3/OpenVSLAM style wrappers behind the same `GraphSLAMBackend.process(frame)` contract.


## App Store Proof Of Concept

The first releasable product direction is ARKit-first. The iOS app is designed for an iPhone mounted on a roborock driving laps through a small mock warehouse.

The app has four tabs:

- Mapping: start new environments, capture ARKit poses/depth, and repeat-map the same environment for more coverage.
- Training: create niche object labels and collect examples for future Core ML/Create ML training.
- Processing: queue frames, show reconstruction progress, and visualize a labeled top-down 3D map.
- Results: show every tracked item with label, confidence, timestamp, map name, and XYZ coordinates.

Current iOS source lives in `ios/MNetMapper`. See `docs/PRODUCT_DECISION.md`, `docs/ROBOROCK_DEMO_RUNBOOK.md`, and `docs/APP_STORE_PLAN.md`.

## Run The Included Sample

```bash
python3 -m mnet_slam.cli --input data/sample_run --output runs/sample.sqlite --stride 5 --max-frames 120 --no-drop
```

The output is a SQLite session database. It uses WAL mode, so another process can open the same file read-only while the pipeline is writing.

Inspect the run and write a trajectory plot:

```bash
python3 -m mnet_slam.inspect runs/sample.sqlite --plot runs/trajectory.png
```

## Multi-Source Input

Use repeated `--input` arguments:

```bash
python3 -m mnet_slam.cli \
  --input data/iphone_recording \
  --input data/robot_recording.jsonl \
  --output runs/fused.sqlite
```

Manifest rows can look like:

```json
{
  "source_id": "iphone_14_pro",
  "frame_id": 123,
  "timestamp": 1234567890.123,
  "rgb": "rgb/frame_000123.png",
  "depth": "depth/depth_000123.exr",
  "confidence": "confidence/conf_000123.png",
  "intrinsics": {"fx": 600.0, "fy": 600.0, "cx": 320.0, "cy": 240.0, "width": 640, "height": 480},
  "imu": {"timestamp": 1234567890.120, "accel": [0, 0, -9.8], "gyro": [0, 0, 0]}
}
```

IMU is stored and carried through the frame model, but this MVP does not fuse IMU yet. Confidence maps are used as correspondence weights during RGBD pose estimation.

## Manifest Workflow

Build a portable JSONL manifest from a Record3D-style folder:

```bash
python3 -m mnet_slam.manifest build \
  --input data/sample_run2 \
  --output manifests/sample_run2.jsonl \
  --source-id iphone_walk_01
```

Validate a manifest before running SLAM:

```bash
python3 -m mnet_slam.manifest validate manifests/sample_run2.jsonl
```

Run SLAM from one or more manifests/folders:

```bash
python3 -m mnet_slam.cli \
  --input manifests/sample_run2.jsonl \
  --output runs/sample_run2_manifest.sqlite \
  --no-drop
```

## Folder Ingest

For a recording folder that is still receiving frames, use the ingest runner:

```bash
python3 -m mnet_slam.ingest \
  --input data/live_recording \
  --output runs/live.sqlite \
  --idle-timeout-s -1
```

Use `--idle-timeout-s 5` for export folders where the run should stop after a few idle seconds.

## Dashboard

Serve a local dashboard over any session database:

```bash
python3 -m mnet_slam.dashboard \
  --session runs/sample_run2_manifest.sqlite \
  --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

## iOS App Scaffold

The SwiftUI App Store-facing shell lives in `ios/MNetMapper`.

It has four tabs:

- Mapping: record new maps and repeat-map the same environment.
- Training: create niche object classes and collect examples.
- Processing: queue RGB/depth frames and preview labeled 3D reconstruction.
- Results: inspect item labels, XYZ coordinates, confidence, and timestamps.

See `ios/README.md` and `docs/APP_STORE_PLAN.md` for the Xcode/App Store path.

## Session Schema

- `frames`: source id, frame id, timestamps, RGB/depth paths, intrinsics.
- `poses`: latest camera-to-world pose and tracking diagnostics.
- `edges`: odometry and loop closure graph edges with relative transforms.

This gives you the shared file you asked for: iPhone and robot recordings can be fed into the same run, and analysis/visualization processes can open the same SQLite file concurrently.

## Notes

RTAB-Map remains the best production-grade choice for robust RGBD loop closure. The MVP keeps that path open by making the backend a single class boundary. On Linux/NVIDIA, the next step is an `RTABMapBackend` that writes the same `poses` and `edges` tables.

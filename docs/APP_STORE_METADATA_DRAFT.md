# App Store Metadata Draft

## Working Name

mNET Mapper

## Subtitle

LiDAR inventory mapping demo

## Description Draft

mNET Mapper is an experimental warehouse mapping tool for LiDAR-capable iPhones. Mount the iPhone on a small robot platform, record repeatable laps through a mock warehouse, queue RGBD frames for processing, train niche object labels, and inspect tracked item coordinates in meters.

The app is organized into four tabs: Mapping, Training, Processing, and Results. Mapping captures new environments and supports repeated passes. Training lets users define specialized object labels. Processing shows queued frames and a labeled 3D map preview. Results reports item labels, confidence, timestamps, and XYZ positions.

## Keywords Draft

LiDAR, mapping, inventory, warehouse, object detection, ARKit, 3D scan, RGBD, SLAM

## Privacy Draft

The first App Store proof of concept should keep camera/depth recordings on-device unless the user explicitly exports or connects to a local processor. If any cloud/backend upload is added, update the privacy policy and App Store privacy nutrition answers before submission.

## Required Permission Copy Drafts

`NSCameraUsageDescription`

```text
mNET Mapper uses the camera and LiDAR depth sensor to map mock warehouse environments and locate tracked objects.
```

`NSLocalNetworkUsageDescription`

```text
mNET Mapper can connect to a local processing service you control for queued RGBD frame processing.
```

`NSPhotoLibraryUsageDescription`

```text
mNET Mapper can import or export recordings, map snapshots, and training examples when you choose.
```

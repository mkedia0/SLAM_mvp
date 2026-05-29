# App Store Metadata Draft

## Working Name

mNET Mapper

## Subtitle

LiDAR mapping and item tracking

## Description Draft

mNET Mapper helps teams record RGBD walks, build reusable 3D maps, train niche object detectors, process queued depth frames, and export item positions with timestamps.

Designed for environments such as grocery stores, stock rooms, labs, and warehouses, the app separates mapping, training, processing, and results so users can repeatedly scan the same environment and compare tracked object positions over time.

## Keywords Draft

LiDAR, mapping, inventory, object detection, AR, 3D scan, RGBD, grocery, SLAM

## Privacy Draft

The app uses camera and depth data to construct maps and identify object locations. The production privacy policy must state whether recordings are stored only on-device, synced to user-controlled storage, or uploaded to a backend for processing.

## Required Permission Copy Drafts

`NSCameraUsageDescription`

```text
mNET Mapper uses the camera and depth sensor to build 3D maps and locate tracked objects.
```

`NSLocalNetworkUsageDescription`

```text
mNET Mapper can stream RGBD frames to a local processing service you control.
```

`NSPhotoLibraryUsageDescription`

```text
mNET Mapper can import or export recordings and map snapshots from your photo library when you choose.
```

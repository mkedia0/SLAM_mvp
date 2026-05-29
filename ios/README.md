# mNET Mapper iOS App Scaffold

This folder contains the SwiftUI source scaffold for the App Store-facing iOS app.

The current machine only has Apple Command Line Tools selected, not full Xcode, so this is source-ready but not archived or signed yet.

## Create The Xcode Target

1. Install/open Xcode 26 or later.
2. Create a new iOS App project named `MNetMapper`.
3. Use SwiftUI, Swift, iPhone/iPad as needed.
4. Set bundle identifier, for example `com.yourcompany.mnetmapper`.
5. Add the files in `ios/MNetMapper/` to the app target.
6. Add these capabilities/usage descriptions when implementation reaches device capture:
   - Camera permission: `NSCameraUsageDescription`
   - LiDAR/depth via ARKit camera access
   - Local network permission if streaming to the Python processing backend
   - Photo Library permission only if importing/exporting recordings there

## Product Tabs

- Mapping: start/repeat environment maps.
- Training: teach niche objects from examples.
- Processing: queue RGB/depth frames and inspect map reconstruction.
- Results: item tracks with XYZ coordinates and timestamps.

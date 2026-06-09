# App Store Plan

## Current Direction

The first release should be ARKit-first. The app can run as a complete proof of concept on LiDAR-capable iPhones without a Linux SLAM backend. Backend compatibility remains a later roadmap item.

## Current Status

- Python RGBD-SLAM MVP exists and can process Record3D-style folders/manifests.
- Local dashboard exists for session database visualization.
- iOS SwiftUI app scaffold exists under `ios/MNetMapper`.
- ARKit capture source has been added for camera pose/scene depth capture.
- Full Xcode is not active on this Mac, so archive/sign/upload cannot happen here yet.

## App Store Readiness Steps

1. Confirm Apple Developer Program team access.
2. Install full Xcode and select it with `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
3. Generate/open the iOS project:
   - Option A: create a new Xcode iOS App target and add `ios/MNetMapper` sources.
   - Option B: install XcodeGen and run `xcodegen generate` from `ios/`.
4. Configure bundle ID, signing team, app icon, launch screen, and usage descriptions.
5. Test on a LiDAR iPhone mounted on the roborock.
6. Verify the app has a built-in demo mode and does not need unavailable backend services.
7. Prepare screenshots for all four tabs.
8. Upload to TestFlight first.
9. Submit for App Review after fixing device-test crashes and privacy metadata.

## App Review Notes To Prepare

- Explain that camera/depth data is used to build approximate 3D maps and item positions.
- State whether data stays on-device for the first release. If backend upload is added, provide a privacy policy URL.
- Avoid positioning this as safety-critical robotics or autonomous navigation.
- Include review instructions for the four tabs and built-in sample/demo data.

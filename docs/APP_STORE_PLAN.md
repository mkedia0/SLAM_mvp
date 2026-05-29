# App Store Plan

## Current Status

- Python RGBD-SLAM MVP exists and can process Record3D-style folders/manifests.
- Local dashboard exists for session database visualization.
- iOS SwiftUI app scaffold exists under `ios/MNetMapper`.
- Full Xcode is not active on this Mac, so archive/sign/upload cannot happen yet.

## App Store Readiness Steps

1. Enroll in the Apple Developer Program or confirm team access.
2. Install Xcode 26 or later and select it with `xcode-select`.
3. Create the Xcode iOS app target and add `ios/MNetMapper` sources.
4. Configure bundle ID, signing team, app icon, launch screen, and usage descriptions.
5. Implement device capture:
   - ARKit/SceneDepth path for supported iPhone/iPad Pro devices.
   - Non-ARKit queued RGB/depth upload path for processing.
6. Add model/object training storage and export format.
7. Test on real LiDAR iPhone hardware.
8. Use TestFlight for internal and external beta feedback.
9. Prepare App Store metadata:
   - Name, subtitle, keywords, description.
   - Screenshots and optional preview video.
   - Privacy Nutrition Label.
   - Accessibility information.
   - Age rating.
10. Archive in Xcode and upload to App Store Connect.

## App Review Notes To Prepare

- Explain that camera/depth data is used to build spatial maps and object positions.
- Document whether data stays on-device or is uploaded to a backend.
- If any backend processing is used, provide a privacy policy URL.
- Avoid claiming production-grade navigation/safety until validated.

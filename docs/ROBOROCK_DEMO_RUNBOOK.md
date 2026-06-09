# Roborock Mock Warehouse Demo Runbook

## Physical Setup

1. Build a small mock warehouse with visible aisles, bins, boxes, and distinct colored/shaped items.
2. Mount the iPhone rigidly on top of the roborock with the rear camera facing forward.
3. Keep the phone high enough that LiDAR sees shelves/items instead of only the floor.
4. Add visual texture to plain walls or boxes if tracking is unstable.
5. Keep lighting consistent and avoid reflective packaging for the first demo.

## Demo Flow

1. Open the Mapping tab.
2. Name the environment, for example `Warehouse lap 01`.
3. Tap Start and let the roborock drive one slow lap.
4. Return near the starting point to exercise loop closure behavior.
5. If coverage is sparse, tap Repeat Map and run the same lap again.
6. Stop mapping and queue processing.
7. In Training, add labels for the mock items such as `red cube bin`, `blue cylinder tote`, and `yellow pallet block`.
8. In Processing, watch the queued frame count and labeled map preview.
9. In Results, export or copy the item coordinates for each tracked object.

## Review-Friendly Framing

Describe this as experimental inventory mapping, not autonomous navigation or safety-critical robotics. The app measures approximate item positions in a controlled mock warehouse.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @property
    def matrix(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )


@dataclass
class IMUSample:
    timestamp: float
    accel: tuple[float, float, float] | None = None
    gyro: tuple[float, float, float] | None = None
    pose: np.ndarray | None = None


@dataclass
class FrameRef:
    source_id: str
    frame_id: int
    timestamp: float
    rgb_path: Path
    depth_path: Path
    confidence_path: Path | None
    intrinsics: CameraIntrinsics
    imu: IMUSample | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RGBDFrame:
    ref: FrameRef
    rgb: np.ndarray
    depth_m: np.ndarray
    confidence: np.ndarray | None = None

    @property
    def key(self) -> str:
        return f"{self.ref.source_id}:{self.ref.frame_id}"


@dataclass
class PoseResult:
    frame_key: str
    pose_c2w: np.ndarray
    tracking_ok: bool
    matches: int = 0
    inliers: int = 0
    loop_closed: bool = False
    loop_with: str | None = None
    place_score: float = 0.0
    map_points: int = 0
    latency_s: float = 0.0

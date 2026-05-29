from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np
from PIL import Image

from .types import CameraIntrinsics, FrameRef, IMUSample, RGBDFrame


def _load_cv2():
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    import cv2

    return cv2


def read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def read_depth_m(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        depth = np.load(path)
    elif suffix == ".npz":
        with np.load(path) as data:
            depth = data["depth"] if "depth" in data else data[data.files[0]]
    elif suffix in {".png", ".tif", ".tiff"}:
        arr = np.asarray(Image.open(path))
        depth = arr.astype(np.float32)
        if np.nanmax(depth) > 100.0:
            depth /= 1000.0
    else:
        cv2 = _load_cv2()
        depth = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if depth is None:
            raise ValueError(f"Could not read depth image: {path}")
        depth = depth.astype(np.float32)
        if depth.ndim == 3:
            valid_counts = [
                int(np.isfinite(depth[..., c]).sum() and np.count_nonzero(np.nan_to_num(depth[..., c]) > 0.05))
                for c in range(depth.shape[2])
            ]
            depth = depth[..., int(np.argmax(valid_counts))]
    depth = np.nan_to_num(depth.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    depth[(depth < 0.05) | (depth > 20.0)] = 0.0
    return depth


def read_confidence(path: Path | None, shape: tuple[int, int]) -> np.ndarray | None:
    if path is None or not path.exists():
        return None
    if path.suffix.lower() == ".npy":
        conf = np.load(path)
    else:
        conf = np.asarray(Image.open(path))
    conf = conf.astype(np.float32)
    if conf.shape != shape:
        cv2 = _load_cv2()
        conf = cv2.resize(conf, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    if conf.max(initial=0.0) > 1.0:
        conf /= conf.max()
    return conf.clip(0.0, 1.0)


class RGBDDataset:
    """Record3D-style dataset or JSON/JSONL manifest.

    A single manifest can include frames from multiple devices by setting
    ``source_id`` per row. This is the common format for iPhone + robot sessions.
    """

    def __init__(self, refs: list[FrameRef]):
        self.refs = sorted(refs, key=lambda r: (r.timestamp, r.source_id, r.frame_id))

    @classmethod
    def open(cls, path: str | Path, source_id: str | None = None) -> "RGBDDataset":
        path = Path(path)
        if path.is_dir():
            return cls._from_record3d_dir(path, source_id or path.name)
        if path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            return cls._from_manifest_rows(rows, path.parent, source_id)
        rows = json.loads(path.read_text())
        if isinstance(rows, dict) and "frames" in rows:
            rows = rows["frames"]
        if not isinstance(rows, list):
            raise ValueError("Manifest JSON must be a list or contain a 'frames' list.")
        return cls._from_manifest_rows(rows, path.parent, source_id)

    @classmethod
    def open_many(cls, inputs: Iterable[str | Path]) -> "RGBDDataset":
        refs: list[FrameRef] = []
        for input_path in inputs:
            refs.extend(cls.open(input_path).refs)
        return cls(refs)

    @classmethod
    def _from_record3d_dir(cls, root: Path, source_id: str) -> "RGBDDataset":
        meta_path = root / "metadata.json"
        if not meta_path.exists() and (root / "metadata2.json").exists():
            meta_path = root / "metadata2.json"
        if not meta_path.exists() and (root.parent / "metadata.json").exists():
            meta_path = root.parent / "metadata.json"
        if not meta_path.exists() and (root.parent.parent / "metadata.json").exists():
            meta_path = root.parent.parent / "metadata.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        rgb_dir, depth_dir = root / "rgb", root / "depth"
        if not rgb_dir.exists() and (root / "rgb2").exists():
            rgb_dir = root / "rgb2"
        if not depth_dir.exists() and (root / "depth2").exists():
            depth_dir = root / "depth2"
        if not rgb_dir.exists() and (root / "sample_run" / "rgb").exists():
            rgb_dir, depth_dir = root / "sample_run" / "rgb", root / "sample_run" / "depth"
        rgb_files = sorted(rgb_dir.glob("*"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem)
        timestamps = meta.get("frameTimestamps", [])
        per_frame_k = meta.get("perFrameIntrinsicCoeffs", [])
        width = int(meta.get("w", meta.get("width", 0)) or 0)
        height = int(meta.get("h", meta.get("height", 0)) or 0)
        dw = int(meta.get("dw", width) or width)
        dh = int(meta.get("dh", height) or height)
        refs: list[FrameRef] = []
        for idx, rgb_path in enumerate(rgb_files):
            frame_id = int(rgb_path.stem) if rgb_path.stem.isdigit() else idx
            depth_path = depth_dir / f"{rgb_path.stem}.exr"
            if not depth_path.exists():
                matches = list(depth_dir.glob(f"{rgb_path.stem}.*"))
                if not matches:
                    continue
                depth_path = matches[0]
            k = per_frame_k[idx] if idx < len(per_frame_k) else meta.get("K")
            if k and len(k) == 9:
                intr = CameraIntrinsics(float(k[0]), float(k[4]), float(k[6]), float(k[7]), dw, dh)
            elif k and len(k) >= 4:
                intr = CameraIntrinsics(float(k[0]), float(k[1]), float(k[2]), float(k[3]), dw, dh)
            else:
                intr = CameraIntrinsics(600.0, 600.0, dw / 2.0, dh / 2.0, dw, dh)
            ts = float(timestamps[idx]) if idx < len(timestamps) else idx / float(meta.get("fps", 30))
            refs.append(FrameRef(source_id, frame_id, ts, rgb_path, depth_path, None, intr, metadata={"record3d": True}))
        return cls(refs)

    @classmethod
    def _from_manifest_rows(
        cls, rows: list[dict], base: Path, source_id: str | None
    ) -> "RGBDDataset":
        refs: list[FrameRef] = []
        for idx, row in enumerate(rows):
            intr = row.get("intrinsics") or {}
            rgb = base / row["rgb"]
            depth = base / row["depth"]
            conf = row.get("confidence") or row.get("confidence_map")
            imu_row = row.get("imu")
            imu = None
            if imu_row:
                imu = IMUSample(
                    timestamp=float(imu_row.get("timestamp", row.get("timestamp", 0.0))),
                    accel=tuple(imu_row["accel"]) if "accel" in imu_row else None,
                    gyro=tuple(imu_row["gyro"]) if "gyro" in imu_row else None,
                )
            refs.append(
                FrameRef(
                    source_id=str(row.get("source_id", source_id or "source0")),
                    frame_id=int(row.get("frame_id", idx)),
                    timestamp=float(row["timestamp"]),
                    rgb_path=rgb,
                    depth_path=depth,
                    confidence_path=(base / conf) if conf else None,
                    intrinsics=CameraIntrinsics(
                        float(intr["fx"]),
                        float(intr["fy"]),
                        float(intr["cx"]),
                        float(intr["cy"]),
                        int(intr.get("width", intr.get("w", 0)) or 0),
                        int(intr.get("height", intr.get("h", 0)) or 0),
                    ),
                    imu=imu,
                    metadata={k: v for k, v in row.items() if k not in {"rgb", "depth", "confidence", "imu"}},
                )
            )
        return cls(refs)

    def frames(self, stride: int = 1, max_frames: int | None = None) -> Iterator[RGBDFrame]:
        count = 0
        for ref in self.refs[:: max(1, stride)]:
            rgb = read_rgb(ref.rgb_path)
            depth = read_depth_m(ref.depth_path)
            conf = read_confidence(ref.confidence_path, depth.shape)
            yield RGBDFrame(ref=ref, rgb=rgb, depth_m=depth, confidence=conf)
            count += 1
            if max_frames is not None and count >= max_frames:
                break

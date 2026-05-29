from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import os

from .io import RGBDDataset


def _rel(path: Path, base: Path) -> str:
    return os.path.relpath(path.resolve(), base.resolve())


def build_manifest(input_dir: Path, output: Path, source_id: str | None = None) -> list[dict[str, Any]]:
    dataset = RGBDDataset.open(input_dir, source_id=source_id or input_dir.name)
    base = output.parent
    rows: list[dict[str, Any]] = []
    for ref in dataset.refs:
        intr = ref.intrinsics
        row: dict[str, Any] = {
            "source_id": ref.source_id,
            "frame_id": ref.frame_id,
            "timestamp": ref.timestamp,
            "rgb": _rel(ref.rgb_path, base),
            "depth": _rel(ref.depth_path, base),
            "intrinsics": {
                "fx": intr.fx,
                "fy": intr.fy,
                "cx": intr.cx,
                "cy": intr.cy,
                "width": intr.width,
                "height": intr.height,
            },
        }
        if ref.confidence_path is not None:
            row["confidence"] = _rel(ref.confidence_path, base)
        if ref.imu is not None:
            row["imu"] = {
                "timestamp": ref.imu.timestamp,
                "accel": ref.imu.accel,
                "gyro": ref.imu.gyro,
            }
        rows.append(row)
    return rows


def write_jsonl(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))


def validate_manifest(path: Path, sample_frames: int = 3) -> dict[str, Any]:
    dataset = RGBDDataset.open(path)
    sources = sorted({ref.source_id for ref in dataset.refs})
    missing: list[str] = []
    for ref in dataset.refs:
        if not ref.rgb_path.exists():
            missing.append(str(ref.rgb_path))
        if not ref.depth_path.exists():
            missing.append(str(ref.depth_path))
        if ref.confidence_path is not None and not ref.confidence_path.exists():
            missing.append(str(ref.confidence_path))
    loaded = 0
    for _ in dataset.frames(max_frames=sample_frames):
        loaded += 1
    return {
        "manifest": str(path.resolve()),
        "frames": len(dataset.refs),
        "sources": sources,
        "missing_files": missing[:20],
        "missing_count": len(missing),
        "sample_frames_loaded": loaded,
        "ok": len(dataset.refs) > 0 and not missing and loaded > 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or validate mNET RGBD manifests.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="Scan a Record3D-style folder and write JSONL.")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--source-id", default=None)
    validate = sub.add_parser("validate", help="Validate a JSON/JSONL manifest.")
    validate.add_argument("manifest")
    validate.add_argument("--sample-frames", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "build":
        rows = build_manifest(Path(args.input), Path(args.output), args.source_id)
        write_jsonl(rows, Path(args.output))
        print(json.dumps({"output": str(Path(args.output).resolve()), "frames": len(rows)}, indent=2))
        return 0
    report = validate_manifest(Path(args.manifest), sample_frames=args.sample_frames)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

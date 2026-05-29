from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import GraphSLAMBackend
from .io import RGBDDataset
from .pipeline import ThreadedSLAMPipeline
from .session import SessionStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="mNET RGBD-SLAM MVP runner")
    parser.add_argument("--input", action="append", required=True, help="Record3D folder or JSON/JSONL manifest. Repeat for multi-source runs.")
    parser.add_argument("--output", default="runs/session.sqlite", help="SQLite session file, readable by multiple processes via WAL.")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--queue-depth", type=int, default=4)
    parser.add_argument("--no-drop", action="store_true", help="Block instead of dropping old frames when tracking falls behind.")
    parser.add_argument("--keyframe-distance-m", type=float, default=0.12)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset = RGBDDataset.open_many(args.input)
    store = SessionStore(args.output)
    backend = GraphSLAMBackend(keyframe_distance_m=args.keyframe_distance_m)
    pipeline = ThreadedSLAMPipeline(
        dataset.frames(stride=args.stride, max_frames=args.max_frames),
        store,
        backend=backend,
        queue_depth=args.queue_depth,
        drop_on_overflow=not args.no_drop,
    )
    stats = pipeline.run()
    store.close()
    summary = {
        "session": str(Path(args.output).resolve()),
        "frames_processed": stats.frames,
        "frames_dropped": stats.dropped,
        "loop_closures": stats.loops,
        "mean_tracking_latency_ms": round(stats.mean_latency_s * 1000.0, 2),
        "backend": "GraphSLAMBackend(cpu-opencv)",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

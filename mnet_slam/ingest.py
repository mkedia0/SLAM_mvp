from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterator

from .backend import GraphSLAMBackend
from .io import RGBDDataset
from .pipeline import ThreadedSLAMPipeline
from .session import SessionStore
from .types import RGBDFrame


class FolderIngest:
    """Poll a Record3D-style folder and yield new RGBD frames as files arrive."""

    def __init__(
        self,
        path: Path,
        poll_s: float = 0.25,
        settle_s: float = 0.5,
        idle_timeout_s: float | None = None,
        max_frames: int | None = None,
        source_id: str | None = None,
    ):
        self.path = path
        self.poll_s = poll_s
        self.settle_s = settle_s
        self.idle_timeout_s = idle_timeout_s
        self.max_frames = max_frames
        self.source_id = source_id
        self.seen: set[str] = set()

    def frames(self) -> Iterator[RGBDFrame]:
        idle_start: float | None = None
        while True:
            dataset = RGBDDataset.open(self.path, source_id=self.source_id)
            emitted = False
            now = time.time()
            for ref in dataset.refs:
                key = f"{ref.source_id}:{ref.frame_id}"
                if key in self.seen:
                    continue
                newest_write = max(ref.rgb_path.stat().st_mtime, ref.depth_path.stat().st_mtime)
                if now - newest_write < self.settle_s:
                    continue
                frame = next(RGBDDataset([ref]).frames())
                self.seen.add(key)
                emitted = True
                yield frame
                if self.max_frames is not None and len(self.seen) >= self.max_frames:
                    return
            if emitted:
                idle_start = None
            else:
                idle_start = idle_start or now
                if self.idle_timeout_s is not None and now - idle_start >= self.idle_timeout_s:
                    return
                time.sleep(self.poll_s)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest RGBD frames from a growing folder into a session DB.")
    parser.add_argument("--input", required=True, help="Record3D-style folder to poll.")
    parser.add_argument("--output", default="runs/live_ingest.sqlite")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--poll-s", type=float, default=0.25)
    parser.add_argument("--settle-s", type=float, default=0.5)
    parser.add_argument("--idle-timeout-s", type=float, default=5.0, help="Stop after this many idle seconds. Use -1 to run until interrupted.")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--queue-depth", type=int, default=4)
    parser.add_argument("--keyframe-distance-m", type=float, default=0.12)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    idle_timeout = None if args.idle_timeout_s < 0 else args.idle_timeout_s
    ingest = FolderIngest(
        Path(args.input),
        poll_s=args.poll_s,
        settle_s=args.settle_s,
        idle_timeout_s=idle_timeout,
        max_frames=args.max_frames,
        source_id=args.source_id,
    )
    store = SessionStore(args.output)
    backend = GraphSLAMBackend(keyframe_distance_m=args.keyframe_distance_m)
    pipeline = ThreadedSLAMPipeline(
        ingest.frames(),
        store,
        backend=backend,
        queue_depth=args.queue_depth,
        drop_on_overflow=False,
    )
    try:
        stats = pipeline.run()
    except KeyboardInterrupt:
        stats = pipeline.stats
    finally:
        store.close()
    print(
        json.dumps(
            {
                "session": str(Path(args.output).resolve()),
                "frames_processed": stats.frames,
                "frames_dropped": stats.dropped,
                "loop_closures": stats.loops,
                "mean_tracking_latency_ms": round(stats.mean_latency_s * 1000.0, 2),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

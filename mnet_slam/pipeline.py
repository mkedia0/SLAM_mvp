from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Iterable

from .backend import GraphSLAMBackend
from .session import SessionStore
from .types import PoseResult, RGBDFrame


@dataclass
class PipelineStats:
    frames: int = 0
    dropped: int = 0
    loops: int = 0
    mean_latency_s: float = 0.0


class ThreadedSLAMPipeline:
    """Decouples RGBD input, tracking/mapping, and persistence."""

    def __init__(
        self,
        frames: Iterable[RGBDFrame],
        session: SessionStore,
        backend: GraphSLAMBackend | None = None,
        queue_depth: int = 4,
        drop_on_overflow: bool = True,
    ):
        self.frames = frames
        self.session = session
        self.backend = backend or GraphSLAMBackend()
        self.drop_on_overflow = drop_on_overflow
        self.in_q: queue.Queue[RGBDFrame | None] = queue.Queue(maxsize=queue_depth)
        self.out_q: queue.Queue[tuple[RGBDFrame, PoseResult] | None] = queue.Queue(maxsize=queue_depth)
        self.stats = PipelineStats()
        self._tracking = threading.Thread(target=self._tracking_loop, name="tracking-mapping")
        self._persist = threading.Thread(target=self._persist_loop, name="session-writer")

    def run(self) -> PipelineStats:
        self._tracking.start()
        self._persist.start()
        for frame in self.frames:
            if self.drop_on_overflow:
                try:
                    self.in_q.put_nowait(frame)
                except queue.Full:
                    try:
                        self.in_q.get_nowait()
                    except queue.Empty:
                        pass
                    self.stats.dropped += 1
                    self.in_q.put_nowait(frame)
            else:
                self.in_q.put(frame)
        self.in_q.put(None)
        self._tracking.join()
        self.out_q.put(None)
        self._persist.join()
        return self.stats

    def _tracking_loop(self) -> None:
        while True:
            frame = self.in_q.get()
            if frame is None:
                break
            result = self.backend.process(frame)
            self.out_q.put((frame, result))

    def _persist_loop(self) -> None:
        latency_sum = 0.0
        while True:
            item = self.out_q.get()
            if item is None:
                break
            frame, result = item
            self.session.add_frame(frame)
            self.session.add_pose(result)
            for edge in self.backend.consume_edges():
                self.session.add_edge(*edge)
            self.stats.frames += 1
            self.stats.loops += int(result.loop_closed)
            latency_sum += result.latency_s
            self.stats.mean_latency_s = latency_sum / max(1, self.stats.frames)

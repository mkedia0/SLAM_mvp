"""
Three-stage lock-step threaded pipeline designed for 30 fps RGB-D input.

Stage layout
------------

  ┌──────────────┐      ingest_q       ┌──────────────────┐     persist_q     ┌──────────────────┐
  │  Stage 1     │  ──────────────►   │  Stage 2          │  ────────────►   │  Stage 3          │
  │  Ingest      │                    │  Filter + SLAM    │                  │  Persist + Viz    │
  │  (main /     │                    │  (slam_thread)    │                  │  (persist_thread  │
  │   caller)    │                    │                   │                  │   + cloud_pool)   │
  └──────────────┘                    └──────────────────┘                  └──────────────────┘

Stage 1 – Ingest (caller's thread)
    Reads from the loader and puts raw RGBDFrames into ``ingest_q``.
    If the queue is full and ``drop_on_overflow=True`` the oldest frame is
    discarded; otherwise the loader is blocked (backpressure).

Stage 2 – Filter + SLAM (single dedicated thread)
    Pops frames from ``ingest_q``, runs ConfidenceFilter, then SLAMEngine.process().
    Packages results into ``persist_q``.  One thread because RTAB-Map is not
    thread-safe.  If SLAM falls behind, overflow is handled by ``ingest_q``.

Stage 3 – Persist + Visualise (dedicated persist thread + thread-pool for clouds)
    Writes frames and poses to the Session.  Point-cloud projection is
    offloaded to a ThreadPoolExecutor so it doesn't stall the persist loop.
    Pushes VizUpdates to the Renderer.

Back-pressure / timing budget
------------------------------
At 30 fps the SLAM budget is 33 ms/frame.  If Stage 2 exceeds that budget,
``ingest_q`` fills and Stage 1 blocks (or drops).  This is intentional: it
prevents memory runaway while keeping the loop as fast as SLAM allows.

Loop-closure pose corrections
------------------------------
When SLAMEngine fires ``pose_graph_updated``, the persist thread calls
``session.update_poses_bulk()`` to rewrite all corrected poses atomically.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterator, Optional

import numpy as np

from ..config import AppConfig
from ..data.frame import RGBDFrame
from ..data.filter import ConfidenceFilter
from ..session.manager import Session
from ..slam.engine import SLAMEngine, SLAMResult
from ..utils.helpers import RunningStats
from ..viz.renderer import Renderer, VizUpdate

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal packet
# ---------------------------------------------------------------------------

@dataclass
class _Packet:
    frame: RGBDFrame
    result: SLAMResult


# ---------------------------------------------------------------------------
# Threaded pipeline
# ---------------------------------------------------------------------------

class ThreadedPipeline:
    """
    Run the SLAM pipeline across three stages on separate threads.

    Parameters
    ----------
    loader:
        Any iterable of RGBDFrame (DataLoader, islice, etc.)
    config:
        Full AppConfig.
    session:
        Open Session object (caller owns lifecycle).
    engine:
        Started SLAMEngine (caller owns lifecycle).
    renderer:
        Open Renderer (caller owns lifecycle; tick() called here).
    force_mock:
        Passed through to SLAMEngine if it has not been started yet.
    """

    def __init__(
        self,
        loader: Iterator[RGBDFrame],
        config: AppConfig,
        session: Session,
        engine: SLAMEngine,
        renderer: Renderer,
    ):
        self.loader   = loader
        self.cfg      = config
        self.session  = session
        self.engine   = engine
        self.renderer = renderer

        tc = config.threading
        self._ingest_q:  queue.Queue[Optional[RGBDFrame]] = queue.Queue(maxsize=tc.ingest_queue_depth)
        self._persist_q: queue.Queue[Optional[_Packet]]   = queue.Queue(maxsize=tc.persist_queue_depth)

        self._filter = ConfidenceFilter(config.filter)
        self._cloud_pool = ThreadPoolExecutor(
            max_workers=tc.projection_workers,
            thread_name_prefix="cloud-proj",
        )

        # Statistics
        self._ingest_stats  = RunningStats()
        self._slam_stats    = RunningStats()
        self._persist_stats = RunningStats()
        self._drop_count    = 0

        self._slam_thread    = threading.Thread(target=self._slam_loop,    daemon=True, name="slam-stage2")
        self._persist_thread = threading.Thread(target=self._persist_loop, daemon=True, name="persist-stage3")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start worker threads, feed frames, then join.

        Blocks until all frames are processed or the user quits the viz window.
        tick() is called on the renderer from this thread (which must be the
        main thread for OpenCV/Open3D GUI compatibility).
        """
        self._slam_thread.start()
        self._persist_thread.start()

        log.info("ThreadedPipeline started (ingest_q=%d, persist_q=%d, cloud_workers=%d).",
                 self.cfg.threading.ingest_queue_depth,
                 self.cfg.threading.persist_queue_depth,
                 self.cfg.threading.projection_workers)

        budget_ms = self.cfg.threading.slam_budget_ms

        try:
            for frame in self.loader:
                t0 = time.perf_counter()
                self._enqueue_ingest(frame)
                self._ingest_stats.update(time.perf_counter() - t0)

                # Tick the renderer on the main thread
                if self.renderer.cfg.enabled:
                    if not self.renderer.tick():
                        log.info("Visualiser window closed – stopping pipeline.")
                        break

                # Warn if SLAM is falling behind
                if self._slam_stats.n and self._slam_stats.mean * 1000 > budget_ms:
                    log.warning(
                        "SLAM mean latency %.1f ms exceeds budget %.1f ms "
                        "(ingest_q=%d).",
                        self._slam_stats.mean * 1000, budget_ms,
                        self._ingest_q.qsize(),
                    )

        except KeyboardInterrupt:
            log.info("Interrupted.")
        finally:
            # Signal workers to finish
            self._ingest_q.put(None)
            self._slam_thread.join(timeout=10)
            self._persist_q.put(None)
            self._persist_thread.join(timeout=10)
            self._cloud_pool.shutdown(wait=False)

        self._log_stats()

    # ------------------------------------------------------------------
    # Stage 1: Ingest (caller thread)
    # ------------------------------------------------------------------

    def _enqueue_ingest(self, frame: RGBDFrame) -> None:
        tc = self.cfg.threading
        if tc.drop_on_overflow:
            try:
                self._ingest_q.put_nowait(frame)
            except queue.Full:
                # Drop oldest, push newest
                try:
                    self._ingest_q.get_nowait()
                except queue.Empty:
                    pass
                self._ingest_q.put_nowait(frame)
                self._drop_count += 1
                if self._drop_count % 30 == 1:
                    log.warning("Dropped %d frames due to SLAM backlog.", self._drop_count)
        else:
            self._ingest_q.put(frame)  # blocks until room

    # ------------------------------------------------------------------
    # Stage 2: Filter + SLAM
    # ------------------------------------------------------------------

    def _slam_loop(self) -> None:
        while True:
            frame = self._ingest_q.get()
            if frame is None:
                break

            t0 = time.perf_counter()

            # Filter
            frame = self._filter(frame)

            # SLAM
            try:
                result = self.engine.process(frame)
            except Exception as e:
                log.error("SLAM error on frame %d: %s", frame.frame_id, e)
                continue

            self._slam_stats.update(time.perf_counter() - t0)

            pkt = _Packet(frame=frame, result=result)
            try:
                self._persist_q.put_nowait(pkt)
            except queue.Full:
                # Persist queue full: drop old packet (keep latest)
                try:
                    self._persist_q.get_nowait()
                except queue.Empty:
                    pass
                self._persist_q.put_nowait(pkt)

    # ------------------------------------------------------------------
    # Stage 3: Persist + Visualise
    # ------------------------------------------------------------------

    def _persist_loop(self) -> None:
        cloud_future = None

        while True:
            pkt = self._persist_q.get()
            if pkt is None:
                break

            t0 = time.perf_counter()
            frame, result = pkt.frame, pkt.result

            # ── Session writes ────────────────────────────────────────
            self.session.add_frame(frame)
            if result.pose is not None:
                self.session.update_pose(frame.frame_id, result.pose)

            # ── Pose-graph correction (loop closure) ──────────────────
            if self.engine.pose_graph_updated.is_set():
                self.engine.pose_graph_updated.clear()
                corrected = dict(self.engine.corrected_poses)
                if corrected:
                    self.session.update_poses_bulk(corrected)
                    log.info("Pose-graph corrected %d poses.", len(corrected))

            # ── Point-cloud projection (async) ────────────────────────
            point_cloud = None
            if self.renderer.cfg.enabled and cloud_future is not None:
                if cloud_future.done():
                    try:
                        point_cloud = cloud_future.result()
                    except Exception as e:
                        log.debug("Cloud projection error: %s", e)

            # Submit new projection job every N frames
            if (frame.frame_id % self.renderer.cfg.refresh_every_n == 0
                    and result.pose is not None):
                cloud_future = self._cloud_pool.submit(
                    _project_frame_to_cloud, frame, result.pose,
                    self.cfg.camera.fx, self.cfg.camera.fy,
                    self.cfg.camera.cx, self.cfg.camera.cy,
                )

            # ── Visualiser push ───────────────────────────────────────
            if self.renderer.cfg.enabled:
                self.renderer.push(VizUpdate(
                    frame=frame,
                    result=result,
                    point_cloud=point_cloud,
                    loop_closure=result.loop_closure,
                ))

            self._persist_stats.update(time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _log_stats(self) -> None:
        log.info(
            "Pipeline stats — "
            "ingest: %.1f ms/frame | slam: %.1f ms/frame | persist: %.1f ms/frame | "
            "dropped: %d frames",
            self._ingest_stats.mean * 1000,
            self._slam_stats.mean * 1000,
            self._persist_stats.mean * 1000,
            self._drop_count,
        )


# ---------------------------------------------------------------------------
# Point-cloud projection (runs in thread-pool worker)
# ---------------------------------------------------------------------------

def _project_frame_to_cloud(
    frame: RGBDFrame,
    pose: np.ndarray,
    fx: float, fy: float, cx: float, cy: float,
    max_points: int = 50_000,
) -> np.ndarray:
    """
    Back-project a depth image into a coloured 3-D point cloud in world frame.

    Returns (N, 6) float32 with columns X, Y, Z, R, G, B.

    Designed to run in a ThreadPoolExecutor worker.  NumPy vectorisation
    keeps it under ~2 ms for a 640×480 frame on a modern CPU.
    """
    depth = frame.depth      # (H, W) float32, metres
    color = frame.color      # (H, W, 3) uint8 BGR

    # Valid pixel mask
    mask = depth > 0
    if not mask.any():
        return np.empty((0, 6), dtype=np.float32)

    ys, xs = np.where(mask)
    zs = depth[ys, xs]

    # Back-project to camera frame
    X_c = (xs - cx) * zs / fx
    Y_c = (ys - cy) * zs / fy
    Z_c = zs

    pts_c = np.column_stack([X_c, Y_c, Z_c]).astype(np.float32)

    # Subsample for display if needed
    if len(pts_c) > max_points:
        idx = np.random.choice(len(pts_c), max_points, replace=False)
        pts_c = pts_c[idx]
        ys, xs = ys[idx], xs[idx]

    # Transform to world frame
    R = pose[:3, :3].astype(np.float32)
    t = pose[:3,  3].astype(np.float32)
    pts_w = (R @ pts_c.T).T + t

    # Colours (BGR → RGB)
    bgr = color[ys, xs].astype(np.float32)
    rgb = bgr[:, ::-1]

    return np.hstack([pts_w, rgb]).astype(np.float32)

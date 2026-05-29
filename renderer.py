"""
Live visualisation renderer.

Supports two back-ends selected by VizConfig.backend:

  "open3d"  – full 3-D point cloud viewer (non-blocking, update via queue)
  "opencv"  – side-by-side colour + false-colour depth window (always available)
  "none"    – no-op (viz disabled)

Threading model
---------------
Both back-ends run their GUI on the **main thread** (Open3D and OpenCV both
require this on most platforms).  The pipeline worker threads push
VizUpdate objects into Renderer.update_queue; the main thread drains the
queue on each display tick via Renderer.tick().

If you need headless rendering (e.g. saving frames to disk), set
VizConfig.backend = "none" and consume the update_queue yourself.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from ..config import VizConfig, CameraConfig
from ..data.frame import RGBDFrame
from ..slam.engine import SLAMResult
from ..slam.loop_closure import LoopClosure

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data sent to the renderer
# ---------------------------------------------------------------------------

@dataclass
class VizUpdate:
    frame: RGBDFrame
    result: SLAMResult
    point_cloud: Optional[np.ndarray] = None    # (N, 6) XYZ-RGB, may be None
    loop_closure: Optional[LoopClosure] = None


# ---------------------------------------------------------------------------
# Base renderer
# ---------------------------------------------------------------------------

class _BaseRenderer:
    def open(self):  pass
    def update(self, vu: VizUpdate): pass
    def tick(self):  pass
    def close(self): pass


# ---------------------------------------------------------------------------
# OpenCV renderer
# ---------------------------------------------------------------------------

class _OpenCVRenderer(_BaseRenderer):
    """
    Simple side-by-side colour + depth window.

    Always available (no extra dependencies beyond OpenCV which is already
    required).  Suitable for monitoring and debugging at 30 fps.
    """

    def __init__(self, cfg: VizConfig):
        self.cfg = cfg
        self._colormap = getattr(cv2, cfg.depth_colormap, cv2.COLORMAP_TURBO)
        self._last_frame: Optional[VizUpdate] = None
        self._loop_flash_until: float = 0.0   # highlight loop closures briefly
        self._frame_count = 0
        self._t_start = time.perf_counter()

    def open(self):
        cv2.namedWindow(self.cfg.window_title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.cfg.window_title, 1280, 480)
        log.info("OpenCV visualiser window opened.")

    def update(self, vu: VizUpdate):
        self._last_frame = vu
        if vu.loop_closure is not None:
            self._loop_flash_until = time.perf_counter() + 1.0

    def tick(self) -> bool:
        """
        Render latest frame. Returns False when the user closes the window.
        Call at ~30 Hz from the main thread.
        """
        if self._last_frame is None:
            key = cv2.waitKey(1)
            return key not in (ord("q"), ord("Q"), 27)

        vu = self._last_frame
        frame = vu.frame
        result = vu.result

        # ── Colour panel ────────────────────────────────────────────────
        color_show = frame.color.copy()

        # Pose overlay
        if result.pose is not None:
            t = result.pose[:3, 3]
            cv2.putText(color_show,
                        f"x={t[0]:.2f} y={t[1]:.2f} z={t[2]:.2f}",
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

        # Loop closure flash
        if time.perf_counter() < self._loop_flash_until:
            cv2.rectangle(color_show, (0, 0),
                          (color_show.shape[1]-1, color_show.shape[0]-1),
                          (0, 0, 255), 6)
            cv2.putText(color_show, "LOOP CLOSURE",
                        (10, color_show.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Frame / FPS counter
        self._frame_count += 1
        elapsed = time.perf_counter() - self._t_start
        fps = self._frame_count / max(elapsed, 1e-6)
        cv2.putText(color_show, f"#{result.frame_id}  {fps:.1f} fps",
                    (10, color_show.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Status badges
        status = []
        if result.lost:
            status.append("LOST")
        if result.loop_closed:
            status.append("LOOP")
        if status:
            cv2.putText(color_show, " | ".join(status),
                        (color_show.shape[1] - 120, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

        # ── Depth panel ─────────────────────────────────────────────────
        depth = frame.depth
        valid = depth > 0
        depth_vis = np.zeros_like(depth)
        if valid.any():
            d_min, d_max = depth[valid].min(), depth[valid].max()
            if d_max > d_min:
                depth_vis[valid] = (depth[valid] - d_min) / (d_max - d_min) * 255
        depth_color = cv2.applyColorMap(depth_vis.astype(np.uint8), self._colormap)

        # Resize depth to match colour height if needed
        h_c, w_c = color_show.shape[:2]
        h_d, w_d = depth_color.shape[:2]
        if h_d != h_c:
            depth_color = cv2.resize(depth_color,
                                     (int(w_d * h_c / h_d), h_c))

        # Confidence overlay (if present)
        if frame.has_confidence:
            conf_norm = (frame.confidence * 255).clip(0, 255).astype(np.uint8)
            conf_color = cv2.applyColorMap(conf_norm, cv2.COLORMAP_PLASMA)
            if conf_color.shape[:2] != depth_color.shape[:2]:
                conf_color = cv2.resize(conf_color, depth_color.shape[1::-1])
            depth_color = cv2.addWeighted(depth_color, 0.6, conf_color, 0.4, 0)

        combined = np.hstack([
            cv2.resize(color_show, (w_c, h_c)),
            depth_color,
        ])
        cv2.imshow(self.cfg.window_title, combined)
        key = cv2.waitKey(1)
        return key not in (ord("q"), ord("Q"), 27)

    def close(self):
        cv2.destroyWindow(self.cfg.window_title)


# ---------------------------------------------------------------------------
# Open3D renderer
# ---------------------------------------------------------------------------

class _Open3DRenderer(_BaseRenderer):
    """
    Non-blocking Open3D point-cloud visualiser.

    The window runs on the main thread via Open3D's poll_events() / update_renderer()
    loop.  The pipeline pushes VizUpdate objects; on each tick() the latest
    point cloud is swapped in atomically.
    """

    def __init__(self, cfg: VizConfig, cam: CameraConfig):
        self.cfg = cfg
        self.cam = cam
        self._vis = None
        self._pcd = None
        self._cv_renderer: Optional[_OpenCVRenderer] = None  # 2-D overlay
        self._latest: Optional[VizUpdate] = None
        self._frame_count = 0
        self._lock = threading.Lock()

    def open(self):
        try:
            import open3d as o3d
        except ImportError:
            log.warning("open3d not installed – falling back to OpenCV renderer.")
            self._cv_renderer = _OpenCVRenderer(self.cfg)
            self._cv_renderer.open()
            return

        self._vis = o3d.visualization.Visualizer()
        self._vis.create_window(
            window_name=self.cfg.window_title,
            width=1280, height=720,
        )
        self._pcd = o3d.geometry.PointCloud()
        self._vis.add_geometry(self._pcd)

        # Rendering options
        opt = self._vis.get_render_option()
        opt.background_color = np.array([0.1, 0.1, 0.1])
        opt.point_size = 2.0

        # Also open a small 2-D window for colour+depth
        self._cv_renderer = _OpenCVRenderer(self.cfg)
        self._cv_renderer.open()
        log.info("Open3D visualiser window opened.")

    def update(self, vu: VizUpdate):
        with self._lock:
            self._latest = vu
        if self._cv_renderer:
            self._cv_renderer.update(vu)

    def tick(self) -> bool:
        """Drain latest update and refresh both windows. Returns False to quit."""
        if self._cv_renderer:
            if not self._cv_renderer.tick():
                return False

        if self._vis is None:
            return True

        with self._lock:
            vu = self._latest
            self._latest = None

        if vu is None:
            self._vis.poll_events()
            self._vis.update_renderer()
            return True

        self._frame_count += 1
        if (self._frame_count % self.cfg.refresh_every_n) != 0:
            self._vis.poll_events()
            self._vis.update_renderer()
            return True

        try:
            import open3d as o3d
            cloud = vu.point_cloud
            if cloud is not None and len(cloud) > 0:
                # Voxel-downsample for display
                pts_o3d = o3d.geometry.PointCloud()
                pts_o3d.points = o3d.utility.Vector3dVector(
                    cloud[:, :3].astype(np.float64)
                )
                if cloud.shape[1] >= 6:
                    pts_o3d.colors = o3d.utility.Vector3dVector(
                        cloud[:, 3:6].astype(np.float64) / 255.0
                    )
                if self.cfg.display_voxel_size > 0:
                    pts_o3d = pts_o3d.voxel_down_sample(self.cfg.display_voxel_size)

                self._pcd.points = pts_o3d.points
                self._pcd.colors = pts_o3d.colors
                self._vis.update_geometry(self._pcd)
        except Exception as e:
            log.debug("Open3D update error: %s", e)

        self._vis.poll_events()
        self._vis.update_renderer()
        return True

    def close(self):
        if self._vis:
            self._vis.destroy_window()
        if self._cv_renderer:
            self._cv_renderer.close()


# ---------------------------------------------------------------------------
# No-op renderer
# ---------------------------------------------------------------------------

class _NullRenderer(_BaseRenderer):
    pass


# ---------------------------------------------------------------------------
# Public Renderer
# ---------------------------------------------------------------------------

class Renderer:
    """
    Thread-safe visualisation façade.

    Worker threads call push(); the main thread calls tick() in a loop.

    Example
    -------
    >>> renderer = Renderer(config.viz, config.camera)
    >>> renderer.open()
    >>> # In main loop:
    >>> while renderer.tick():
    ...     time.sleep(1/30)
    """

    def __init__(self, cfg: VizConfig, cam: CameraConfig):
        self.cfg = cfg
        self.update_queue: queue.Queue[VizUpdate] = queue.Queue(maxsize=4)
        self._impl = self._make_impl(cfg, cam)
        self._running = False

    @staticmethod
    def _make_impl(cfg: VizConfig, cam: CameraConfig) -> _BaseRenderer:
        b = cfg.backend.lower()
        if b == "open3d":
            return _Open3DRenderer(cfg, cam)
        if b == "opencv":
            return _OpenCVRenderer(cfg)
        return _NullRenderer()

    def open(self):
        if self.cfg.enabled:
            self._impl.open()
            self._running = True

    def push(self, vu: VizUpdate, block: bool = False) -> None:
        """Push a VizUpdate from a worker thread. Drops if queue is full."""
        if not self.cfg.enabled:
            return
        try:
            self.update_queue.put(vu, block=block, timeout=0.005)
        except queue.Full:
            pass  # drop – display is non-critical

    def tick(self) -> bool:
        """
        Drain queued updates and render.  Call at display rate from main thread.
        Returns False when the user requests quit.
        """
        if not self.cfg.enabled:
            return True
        try:
            while True:
                vu = self.update_queue.get_nowait()
                self._impl.update(vu)
        except queue.Empty:
            pass
        return self._impl.tick()

    def close(self):
        self._impl.close()
        self._running = False

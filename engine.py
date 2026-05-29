"""
SLAM engine integration.

Back-ends
---------
_RTABMapBackend   Real RTAB-Map via Python bindings built from source.
                  Detected at import time; constructor raises ImportError when
                  unavailable so the façade can fall back gracefully.

_MockBackend      Deterministic identity-drift stand-in for CI and development.

Both implement the same five-method contract:
  process(frame)  → SLAMResult
  get_point_cloud() → np.ndarray (N, 6) XYZ-RGB float32
  reset()
  close()
  backend_name    property → str

RTAB-Map Python bindings
------------------------
The bindings are compiled alongside RTAB-Map when the CMake flag
``BUILD_PYTHON_BINDINGS=ON`` is set (available since RTAB-Map ≥ 0.20).
They expose the following C++ classes directly into the ``rtabmap`` module:

  rtabmap.Rtabmap        Main SLAM engine (wraps rtabmap::Rtabmap)
  rtabmap.SensorData     RGB-D frame container (wraps rtabmap::SensorData)
  rtabmap.CameraModel    Camera intrinsics  (wraps rtabmap::CameraModel)
  rtabmap.Transform      SE(3) rigid transform (wraps rtabmap::Transform)
  rtabmap.Odometry       Odometry estimator factory
  rtabmap.OdometryInfo   Per-frame odometry diagnostics
  rtabmap.Statistics     Per-frame SLAM statistics

Key API surface used here
~~~~~~~~~~~~~~~~~~~~~~~~~
``Rtabmap``
  .init(params: dict, databasePath: str = "", loadDatabaseParameters: bool = False)
  .process(data: SensorData, odomPose: Transform, [covariance: np.ndarray]) → bool
  .getStatistics() → Statistics
  .getLocalOptimizedPoses() → dict[int, Transform]
  .getLoopClosureId() → int          (0 = no loop closure this step)
  .getLoopClosureValue() → float     (hypothesis probability)
  .close(databaseSaved: bool = True, outputDatabasePath: str = "")
  .resetMemory()

``Odometry``  (created via Odometry.create(params))
  .process(data: SensorData, info: OdometryInfo) → Transform
    Returns null Transform on tracking failure.

``SensorData``  (RGB-D constructor)
  SensorData(rgb: np.ndarray,          # uint8 BGR
             depth: np.ndarray,        # float32 metres OR uint16 mm
             cameraModel: CameraModel,
             id: int,
             stamp: float)

``CameraModel``
  CameraModel(name: str, fx, fy, cx, cy, localTransform: Transform, imageSize: tuple)

``Transform``
  Transform(r11..r33, tx, ty, tz)     12-element row-major rotation+translation
  .isNull() → bool
  .toEigen4f() → np.ndarray (4,4)    NOT available in all builds
  .data() → list[float]               12-element [R|t] row-major

``Statistics``
  .data() → dict[str, float]          All named statistics as a flat dict
  Common keys used here:
    "Loop/Id"             int – node ID of the matched loop-closure node (0 = none)
    "Loop/Hypothesis"     float – loop-closure hypothesis score
    "Memory/Working_Memory_Size"  int
    "Memory/Short_Term_Memory_Size" int
    "Odometry/Translation_Std"    float
    "Odometry/Rotation_Std"       float

Loop-closure wiring
-------------------
When RTAB-Map's Rtabmap.process() returns True, getLoopClosureId() gives the
matched node ID.  We convert this to a LoopClosure event with an approximate
relative pose derived from the optimised pose graph.

Pose representation
-------------------
RTAB-Map's Transform stores a 3×4 [R|t] matrix (row-major, 12 floats).
We convert it to a homogeneous 4×4 SE(3) matrix for the rest of the framework:

    T = | R  t |
        | 0  1 |

Threading
---------
Neither Rtabmap nor Odometry is thread-safe.  Both must be called exclusively
from the SLAM stage-2 thread (enforced by ThreadedPipeline).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..config import AppConfig, SLAMConfig, CameraConfig
from ..data.frame import RGBDFrame
from .loop_closure import LoopClosureDetector, LoopClosure

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Public result type
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SLAMResult:
    """Output of a single SLAMEngine.process() call."""
    frame_id:           int
    pose:               Optional[np.ndarray] = None   # (4,4) camera-to-world SE(3)
    loop_closed:        bool = False
    loop_closure:       Optional[LoopClosure] = None
    lost:               bool = False
    map_size:           int = 0                       # nodes in working memory
    processing_time_s:  float = 0.0
    # RTAB-Map–specific diagnostics (empty for mock)
    info: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _transform_to_matrix(tf) -> Optional[np.ndarray]:
    """
    Convert an rtabmap.Transform to a (4, 4) float64 SE(3) matrix.

    The Transform.data() method returns 12 floats in row-major order:
      [r11, r12, r13, tx,
       r21, r22, r23, ty,
       r31, r32, r33, tz]

    Returns None if the transform is null / unavailable.
    """
    if tf is None:
        return None
    try:
        if tf.isNull():
            return None
        raw = tf.data()           # list or tuple of 12 floats
        if raw is None or len(raw) < 12:
            log.warning("Transform.data() returned unexpected value: %r", raw)
            return None
        mat = np.eye(4, dtype=np.float64)
        mat[0, :3] = raw[0:3];  mat[0, 3] = raw[3]
        mat[1, :3] = raw[4:7];  mat[1, 3] = raw[7]
        mat[2, :3] = raw[8:11]; mat[2, 3] = raw[11]
        return mat
    except Exception as exc:
        log.warning("Could not convert Transform to matrix: %s", exc)
        return None


def _matrix_to_transform(mat: np.ndarray, rtabmap_module):
    """
    Convert a (4, 4) SE(3) numpy matrix to an rtabmap.Transform.

    rtabmap.Transform constructor takes 12 row-major [R|t] floats.
    """
    r = mat[:3, :3]
    t = mat[:3, 3]
    return rtabmap_module.Transform(
        float(r[0,0]), float(r[0,1]), float(r[0,2]), float(t[0]),
        float(r[1,0]), float(r[1,1]), float(r[1,2]), float(t[1]),
        float(r[2,0]), float(r[2,1]), float(r[2,2]), float(t[2]),
    )


def _build_camera_model(cam: CameraConfig, rtabmap_module):
    """Build an rtabmap.CameraModel from a CameraConfig."""
    # localTransform = transform from camera optical to robot base frame.
    # We use identity: camera IS the robot frame for this framework.
    local_tf = rtabmap_module.Transform(
        1,0,0,0,
        0,1,0,0,
        0,0,1,0,
    )
    return rtabmap_module.CameraModel(
        "rgbd_slam",                    # model name (arbitrary)
        float(cam.fx), float(cam.fy),
        float(cam.cx), float(cam.cy),
        local_tf,
        (int(cam.width), int(cam.height)),
    )


def _build_sensor_data(frame: RGBDFrame, cam_model, rtabmap_module):
    """
    Package an RGBDFrame into an rtabmap.SensorData.

    RTAB-Map expects:
      rgb   – uint8 BGR, (H, W, 3)
      depth – float32 metres, (H, W)   OR uint16 mm, (H, W)
    """
    rgb   = frame.color   # already BGR uint8
    depth = frame.depth   # already float32 metres from our filter

    # Ensure depth is contiguous float32 – RTAB-Map binding requirement
    depth_f = np.ascontiguousarray(depth, dtype=np.float32)

    return rtabmap_module.SensorData(
        rgb,
        depth_f,
        cam_model,
        int(frame.frame_id),
        float(frame.timestamp),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RTAB-Map back-end
# ═══════════════════════════════════════════════════════════════════════════════

class _RTABMapBackend:
    """
    Wraps both rtabmap::Odometry (visual odometry) and rtabmap::Rtabmap
    (map/loop-closure management).

    Odometry pipeline
    -----------------
    On every frame:
      1. Build SensorData from the RGBDFrame.
      2. Run Odometry.process() → odom_transform (camera-to-origin SE(3)).
         If tracking is lost the transform is null; we propagate the last
         good pose and set result.lost = True.
      3. Feed SensorData + odom_transform to Rtabmap.process().
         Rtabmap decides whether to create a new node and runs loop-closure
         detection internally.
      4. Read back statistics; extract the optimised pose for this node from
         getLocalOptimizedPoses().

    Why separate odometry + SLAM?
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    RTAB-Map's Rtabmap class needs an *odometry pose* as input – it does not
    do frame-to-frame tracking internally in the Python binding flow.  The
    Odometry class provides that tracking.  This mirrors the typical ROS
    deployment where rtabmap_ros/rgbd_odometry publishes /odom and
    rtabmap_ros/rtabmap subscribes to it.
    """

    backend_name = "RTABMap"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, slam_cfg: SLAMConfig, cam_cfg: CameraConfig):
        log.info("── RTABMapBackend: importing rtabmap bindings ──────────────")
        try:
            import rtabmap as _rt
            self._rt = _rt
        except ImportError as exc:
            raise ImportError(
                "rtabmap Python bindings not found.\n"
                "Build RTAB-Map from source with -DBUILD_PYTHON_BINDINGS=ON\n"
                "or install via your distro's rtabmap package and ensure\n"
                "the build output directory is on PYTHONPATH.\n"
                f"Original error: {exc}"
            ) from exc

        log.info("  rtabmap module: %s", getattr(self._rt, '__file__', '<built-in>'))
        self._log_binding_version()

        self._slam_cfg  = slam_cfg
        self._cam_cfg   = cam_cfg
        self._cam_model = _build_camera_model(cam_cfg, self._rt)

        log.info("  CameraModel: fx=%.2f fy=%.2f cx=%.2f cy=%.2f  size=%dx%d",
                 cam_cfg.fx, cam_cfg.fy, cam_cfg.cx, cam_cfg.cy,
                 cam_cfg.width, cam_cfg.height)

        # ── Odometry ────────────────────────────────────────────────
        odom_params = self._build_odometry_params(slam_cfg)
        log.info("  Creating Odometry (strategy=%s, features=%s, max=%d) …",
                 slam_cfg.odom_strategy, slam_cfg.feature_type,
                 slam_cfg.feature_max_features)
        log.debug("  Odometry params: %s", odom_params)
        self._odom = self._rt.Odometry.create(odom_params)
        log.info("  Odometry created: %s", type(self._odom).__name__)

        # ── SLAM / map management ────────────────────────────────────
        slam_params = self._build_slam_params(slam_cfg)
        db_path = str(slam_cfg.database_path) if slam_cfg.database_path else ""
        log.info("  Initialising Rtabmap (db=%r) …", db_path or "<in-memory>")
        log.debug("  SLAM params: %s", slam_params)
        self._rtabmap = self._rt.Rtabmap()
        self._rtabmap.init(slam_params, db_path)
        log.info("  Rtabmap initialised.")

        # Running state
        self._last_good_odom: Optional[np.ndarray] = None   # last non-null odom matrix
        self._node_count    = 0
        self._frame_count   = 0
        self._lost_streak   = 0
        self._total_lost    = 0
        self._loop_events: List[Tuple[int, float]] = []     # (node_id, hypothesis_score)

        log.info("── RTABMapBackend ready ─────────────────────────────────────")

    # ------------------------------------------------------------------
    # Parameter construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_odometry_params(cfg: SLAMConfig) -> dict:
        """
        Build the parameter dict for rtabmap::Odometry.create().

        Key parameter names come from rtabmap/core/Parameters.h.
        All values must be strings (RTAB-Map ParametersMap = map<string,string>).
        """
        feature_strategy = {
            "SURF": "1", "SIFT": "2", "ORB": "3",
            "FAST/FREAK": "4", "FAST/BRIEF": "5", "GFTT/FREAK": "6",
            "GFTT/BRIEF": "7", "BRISK": "8", "GFTT/ORB": "9",
            "KAZE": "10",
        }.get(cfg.feature_type, "3")   # default ORB

        odom_strategy = "0" if cfg.odom_strategy == "F2M" else "1"

        return {
            # Odometry strategy: 0=F2M (frame-to-map), 1=F2F (frame-to-frame)
            "Odom/Strategy":                odom_strategy,
            # Minimum inliers to accept an odometry estimate
            "Odom/MinInliers":              "10",
            # Reset if tracking lost for this many consecutive frames
            "Odom/ResetCountdown":          "1",
            # Fill odometry info (needed for diagnostics)
            "Odom/FillInfoData":            "true",
            # Feature detector
            "Kp/DetectorStrategy":          feature_strategy,
            "Kp/MaxFeatures":               str(cfg.feature_max_features),
            # Visual odometry: minimum inliers
            "Vis/MinInliers":               str(cfg.lc_min_inliers),
            # ICP refinement of visual estimates
            "Icp/Enabled":                  "true" if cfg.icp_enabled else "false",
            "Icp/MaxCorrespondenceDistance": str(cfg.icp_max_correspondence_distance),
            # Frame-to-Map specific: map size limit
            "OdomF2M/MaxSize":              "2000",
            # Guess motion from previous frame (helps at 30 fps)
            "Odom/GuessMotion":             "true",
            "Odom/GuessSmoothingDelay":     "0",
        }

    @staticmethod
    def _build_slam_params(cfg: SLAMConfig) -> dict:
        """
        Build the parameter dict for rtabmap::Rtabmap.init().

        Parameters govern memory management, loop-closure detection, and
        graph optimisation.  All values are strings.
        """
        feature_strategy = {
            "SURF": "1", "SIFT": "2", "ORB": "3",
        }.get(cfg.feature_type, "3")

        return {
            # ── Memory management ──────────────────────────────────────
            # Short-term memory size: nodes always kept in working memory
            "Mem/STMSize":                      str(cfg.mem_stm_size),
            # Rehearsal: merge similar consecutive nodes to save memory
            "Mem/RehearsalSimilarity":          str(cfg.mem_rehearsal_similarity),
            # Keep raw images in working memory (needed for loop verification)
            "Mem/RawDescriptorsKept":           "true",
            # Reuse odometry features instead of re-extracting
            "Mem/UseOdomFeatures":              "true",

            # ── Loop-closure detection ─────────────────────────────────
            # Minimum visual inliers for a loop hypothesis to be accepted
            "Vis/MinInliers":                   str(cfg.lc_min_inliers),
            # ICP refinement of loop-closure pose
            "Icp/Enabled":                      "true" if cfg.icp_enabled else "false",
            "Icp/MaxCorrespondenceDistance":    str(cfg.lc_inlier_distance),
            # Feature type for loop-closure descriptor matching
            "Kp/DetectorStrategy":              feature_strategy,
            "Kp/MaxFeatures":                   str(cfg.feature_max_features),

            # ── RGBD mode ─────────────────────────────────────────────
            # Only add a new node when the robot has moved by this amount
            "RGBD/LinearUpdate":                "0.01",   # 1 cm
            "RGBD/AngularUpdate":               "0.01",   # ~0.6°
            # Refine odometry links with local graph neighbours
            "RGBD/NeighborLinkRefining":        "true",
            # Proximity detection in map space (spatial loop closure)
            "RGBD/ProximityBySpace":            "true",
            "RGBD/ProximityPathMaxNeighbors":   "10",

            # ── Optimiser ─────────────────────────────────────────────
            # 0=TORO, 1=g2o, 2=GTSAM, 3=Ceres (use g2o if available)
            "Optimizer/Strategy":               "1",
            "Optimizer/Iterations":             "20",
            "Optimizer/Robust":                 "false",

            # ── Grid / map ────────────────────────────────────────────
            "Grid/CellSize":                    str(cfg.map_voxel_size),

            # ── Database ──────────────────────────────────────────────
            # Time budget: 0 = no limit (process every frame)
            "Rtabmap/TimeThr":                  "0",
            # Memory threshold: 0 = no limit
            "Rtabmap/MemoryThr":                "0",
        }

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def process(self, frame: RGBDFrame) -> SLAMResult:
        t0 = time.perf_counter()
        self._frame_count += 1
        fid = frame.frame_id
        log.debug("RTABMap.process  frame_id=%d  ts=%.3f", fid, frame.timestamp)

        # ── Step 1: Package into SensorData ─────────────────────────────────
        sensor_data = _build_sensor_data(frame, self._cam_model, self._rt)
        log.debug("  SensorData created: id=%d  depth shape=%s  dtype=%s",
                  fid, frame.depth.shape, frame.depth.dtype)

        # ── Step 2: Visual odometry ──────────────────────────────────────────
        odom_info  = self._rt.OdometryInfo()
        odom_tf    = self._odom.process(sensor_data, odom_info)
        odom_lost  = odom_tf.isNull()

        if odom_lost:
            self._lost_streak += 1
            self._total_lost  += 1
            log.warning(
                "  Frame %d: odometry LOST (consecutive=%d, total=%d)",
                fid, self._lost_streak, self._total_lost,
            )
        else:
            self._lost_streak = 0
            self._last_good_odom = _transform_to_matrix(odom_tf)
            log.debug(
                "  Frame %d: odometry OK  t=[%.3f, %.3f, %.3f]",
                fid,
                self._last_good_odom[0,3] if self._last_good_odom is not None else 0,
                self._last_good_odom[1,3] if self._last_good_odom is not None else 0,
                self._last_good_odom[2,3] if self._last_good_odom is not None else 0,
            )

        # Build odometry diagnostics dict for SLAMResult.info
        odom_diag = self._extract_odom_info(odom_info)
        log.debug("  Odom diagnostics: %s", odom_diag)

        # Use last good odom if current is null (prevents Rtabmap crash on null pose)
        if odom_lost:
            if self._last_good_odom is not None:
                effective_odom_tf = _matrix_to_transform(
                    self._last_good_odom, self._rt
                )
                log.debug("  Using last good odom pose for SLAM input.")
            else:
                # No pose at all yet – return early, cannot proceed
                log.warning("  Frame %d: no valid odometry yet, skipping SLAM step.", fid)
                return SLAMResult(
                    frame_id=fid,
                    pose=None,
                    lost=True,
                    processing_time_s=time.perf_counter() - t0,
                    info={"odom": odom_diag},
                )
        else:
            effective_odom_tf = odom_tf

        # ── Step 3: SLAM update ──────────────────────────────────────────────
        # Covariance: identity means full trust in odometry; a real system
        # would fill this from odom_info.
        odom_covariance = np.eye(6, dtype=np.float64) * 0.001
        log.debug("  Calling Rtabmap.process() …")
        rtabmap_accepted = self._rtabmap.process(
            sensor_data,
            effective_odom_tf,
            odom_covariance,
        )
        log.debug("  Rtabmap.process() returned: %s", rtabmap_accepted)

        # ── Step 4: Extract results ──────────────────────────────────────────
        stats         = self._rtabmap.getStatistics()
        stats_dict    = stats.data() if hasattr(stats, "data") else {}
        loop_id       = self._rtabmap.getLoopClosureId()
        loop_value    = self._rtabmap.getLoopClosureValue()
        loop_closed   = loop_id > 0

        if loop_closed:
            log.info(
                "  *** Loop closure: query node → match node %d  (score=%.4f)",
                loop_id, loop_value,
            )
            self._loop_events.append((loop_id, loop_value))

        # Node count from working memory
        wm_size = int(stats_dict.get("Memory/Working_Memory_Size", self._node_count))
        stm_size = int(stats_dict.get("Memory/Short_Term_Memory_Size", 0))
        if rtabmap_accepted:
            self._node_count = wm_size + stm_size
        log.debug(
            "  Stats: WM=%d  STM=%d  total_nodes=%d  loop_closed=%s",
            wm_size, stm_size, self._node_count, loop_closed,
        )

        # ── Step 5: Extract optimised camera pose ────────────────────────────
        pose_matrix = self._extract_optimised_pose(stats_dict)
        if pose_matrix is None and self._last_good_odom is not None:
            # Fall back to raw odometry if graph has no optimised pose yet
            pose_matrix = self._last_good_odom.copy()
            log.debug("  Pose: using raw odometry (optimised graph empty).")
        elif pose_matrix is not None:
            log.debug(
                "  Pose (optimised): t=[%.3f, %.3f, %.3f]",
                pose_matrix[0,3], pose_matrix[1,3], pose_matrix[2,3],
            )

        dt = time.perf_counter() - t0
        log.debug("  Frame %d done in %.1f ms", fid, dt * 1000)

        # ── Step 6: Build LoopClosure object if a closure just fired ─────────
        loop_closure_obj: Optional[LoopClosure] = None
        if loop_closed and pose_matrix is not None:
            loop_closure_obj = self._build_loop_closure_event(
                query_fid=fid,
                match_node_id=loop_id,
                score=loop_value,
            )

        return SLAMResult(
            frame_id         = fid,
            pose             = pose_matrix,
            loop_closed      = loop_closed,
            loop_closure     = loop_closure_obj,
            lost             = odom_lost,
            map_size         = self._node_count,
            processing_time_s= dt,
            info             = {
                "odom":        odom_diag,
                "stats":       {k: v for k, v in stats_dict.items()
                                if k.startswith(("Loop/", "Memory/", "Odom/"))},
                "rtabmap_accepted": rtabmap_accepted,
                "wm_size":     wm_size,
                "stm_size":    stm_size,
            },
        )

    # ------------------------------------------------------------------
    # Helpers: pose extraction
    # ------------------------------------------------------------------

    def _extract_optimised_pose(self, stats_dict: dict) -> Optional[np.ndarray]:
        """
        Pull the current camera-to-world pose from the optimised pose graph.

        RTAB-Map's getLocalOptimizedPoses() returns the most recently
        optimised sub-graph as a dict[int, Transform].  The last entry
        corresponds to the most recent node.
        """
        try:
            local_poses = self._rtabmap.getLocalOptimizedPoses()
            if not local_poses:
                return None
            last_id   = max(local_poses.keys())
            last_pose = local_poses[last_id]
            mat = _transform_to_matrix(last_pose)
            if mat is None:
                log.debug("  getLocalOptimizedPoses: last pose is null.")
            return mat
        except Exception as exc:
            log.debug("  Could not read optimised poses: %s", exc)
            return None

    def _extract_odom_info(self, odom_info) -> dict:
        """Pull diagnostics from OdometryInfo into a plain dict."""
        diag: dict = {}
        try:
            diag["inliers"]      = getattr(odom_info, "reg", {}).get("inliers", -1) \
                                   if hasattr(odom_info, "reg") else -1
            diag["matches"]      = getattr(odom_info, "reg", {}).get("matches", -1) \
                                   if hasattr(odom_info, "reg") else -1
            diag["lost"]         = odom_info.lost if hasattr(odom_info, "lost") else None
            diag["features"]     = odom_info.features if hasattr(odom_info, "features") else -1
        except Exception:
            pass
        return diag

    def _build_loop_closure_event(
        self, query_fid: int, match_node_id: int, score: float
    ) -> Optional[LoopClosure]:
        """
        Create a LoopClosure descriptor from a confirmed RTAB-Map loop closure.

        The relative pose between the loop pair is approximated as the
        difference between their optimised poses in the pose graph.
        """
        try:
            local_poses = self._rtabmap.getLocalOptimizedPoses()
            if not local_poses:
                return None

            # Best-effort relative pose: T_match^{-1} @ T_query
            last_id    = max(local_poses.keys())
            T_query_tf = local_poses.get(last_id)
            T_match_tf = local_poses.get(match_node_id)

            T_rel = np.eye(4, dtype=np.float64)
            if T_query_tf is not None and T_match_tf is not None:
                T_query = _transform_to_matrix(T_query_tf)
                T_match = _transform_to_matrix(T_match_tf)
                if T_query is not None and T_match is not None:
                    T_rel = np.linalg.inv(T_match) @ T_query

            return LoopClosure(
                query_id      = query_fid,
                match_id      = match_node_id,
                relative_pose = T_rel,
                inlier_count  = self._slam_cfg.lc_min_inliers,  # approx; real count in stats
                score         = score,
            )
        except Exception as exc:
            log.debug("  Could not build LoopClosure object: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Map retrieval
    # ------------------------------------------------------------------

    def get_point_cloud(self) -> np.ndarray:
        """
        Retrieve the global point cloud from RTAB-Map.

        RTAB-Map's Python bindings expose getGraph() / get3DMap() –
        we use the optimised pose graph and assemble a cloud from stored
        node data where available.  Falls back to an empty array if
        the bindings don't expose map retrieval.
        """
        log.debug("get_point_cloud: querying RTAB-Map …")
        try:
            # Try the most common binding variant
            cloud = self._rtabmap.getGeneratedMap()
            if cloud is not None:
                arr = np.array(cloud, dtype=np.float32)
                log.debug("  getGeneratedMap: %d points", len(arr))
                return arr if arr.ndim == 2 and arr.shape[1] >= 6 \
                       else np.empty((0, 6), dtype=np.float32)
        except AttributeError:
            log.debug("  getGeneratedMap not available; trying getGraph.")
        except Exception as exc:
            log.warning("  getGeneratedMap failed: %s", exc)

        # Fallback: return empty – caller will build cloud from raw frames
        log.debug("  No cloud retrieval method available; returning empty.")
        return np.empty((0, 6), dtype=np.float32)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        log.info("RTABMapBackend.reset(): clearing memory …")
        self._rtabmap.resetMemory()
        self._odom.reset()
        self._last_good_odom = None
        self._node_count     = 0
        self._frame_count    = 0
        self._lost_streak    = 0
        self._loop_events.clear()
        log.info("  Reset complete.")

    def close(self) -> None:
        log.info("RTABMapBackend.close(): saving and shutting down …")
        db_path = str(self._slam_cfg.database_path) \
                  if self._slam_cfg.database_path else ""
        save    = bool(self._slam_cfg.database_path)
        self._rtabmap.close(save, db_path)
        log.info(
            "  Closed.  Frames processed=%d  Lost=%d  Loops=%d  Nodes=%d",
            self._frame_count, self._total_lost,
            len(self._loop_events), self._node_count,
        )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _log_binding_version(self) -> None:
        rt = self._rt
        version_attr = getattr(rt, "__version__", None) \
                    or getattr(rt, "RTABMAP_VERSION", None)
        if version_attr:
            log.info("  rtabmap version: %s", version_attr)
        else:
            log.info("  rtabmap version: (not exposed by bindings)")
        exposed = [a for a in dir(rt)
                   if not a.startswith("_") and not a.islower()]
        log.debug("  Exposed classes: %s", exposed)


# ═══════════════════════════════════════════════════════════════════════════════
# Mock back-end
# ═══════════════════════════════════════════════════════════════════════════════

class _MockBackend:
    """
    Deterministic stand-in for CI / development without RTAB-Map.

    Pose behaviour:  camera moves in a slow helix so the trajectory has
    non-trivial shape and loop-closure candidates actually make geometric
    sense.  No loop closures are emitted (use the standalone LCD layer).
    """

    backend_name = "Mock"

    def __init__(self) -> None:
        self._count = 0
        self._pose  = np.eye(4, dtype=np.float64)
        log.warning(
            "SLAMEngine: using MOCK back-end. "
            "Install rtabmap with Python bindings for real SLAM. "
            "Poses follow a deterministic helix; no real odometry is computed."
        )

    def process(self, frame: RGBDFrame) -> SLAMResult:
        self._count += 1
        fid = frame.frame_id

        # Slow helix: one full revolution every 300 frames
        angle = 2 * np.pi * fid / 300.0
        radius = 0.05   # 5 cm orbit
        self._pose[0, 3] = radius * np.cos(angle)
        self._pose[1, 3] = fid * 0.002     # 2 mm/frame rise
        self._pose[2, 3] = radius * np.sin(angle)

        return SLAMResult(
            frame_id          = fid,
            pose              = self._pose.copy(),
            loop_closed       = False,
            lost              = False,
            map_size          = self._count,
            processing_time_s = 0.001,
            info              = {"backend": "mock"},
        )

    def get_point_cloud(self) -> np.ndarray:
        return np.zeros((100, 6), dtype=np.float32)

    def reset(self) -> None:
        self._count = 0
        self._pose  = np.eye(4, dtype=np.float64)

    def close(self) -> None:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Detection helpers (module-level, called once at import / on first use)
# ═══════════════════════════════════════════════════════════════════════════════

def detect_rtabmap() -> Tuple[bool, str]:
    """
    Probe for rtabmap Python bindings without importing into __main__ state.

    Returns (available: bool, detail_message: str).
    """
    try:
        import importlib
        rt = importlib.import_module("rtabmap")
        version = getattr(rt, "__version__", None) \
               or getattr(rt, "RTABMAP_VERSION", "<unknown>")
        has_rtabmap_cls  = hasattr(rt, "Rtabmap")
        has_odometry_cls = hasattr(rt, "Odometry")
        has_sensordata   = hasattr(rt, "SensorData")
        missing = [
            n for n, ok in [
                ("Rtabmap",    has_rtabmap_cls),
                ("Odometry",   has_odometry_cls),
                ("SensorData", has_sensordata),
            ] if not ok
        ]
        if missing:
            return False, (
                f"rtabmap module found (version={version}) "
                f"but missing classes: {missing}. "
                "Recompile with BUILD_PYTHON_BINDINGS=ON."
            )
        return True, f"rtabmap version={version}  file={getattr(rt, '__file__', '<built-in>')}"
    except ImportError as exc:
        return False, f"rtabmap not importable: {exc}"
    except Exception as exc:
        return False, f"Unexpected error probing rtabmap: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# Public façade
# ═══════════════════════════════════════════════════════════════════════════════

class SLAMEngine:
    """
    Façade over an RTAB-Map back-end (real or mock) with an integrated
    standalone LoopClosureDetector.

    Hierarchy of loop-closure detection
    ------------------------------------
    Layer 1 – RTAB-Map internal:   Bayesian place recognition + ICP verification.
                                   Active only when the real back-end is used.
    Layer 2 – Standalone LCD:       ORB BoW + Essential matrix RANSAC.
                                   Always active (also augments the mock back-end).

    Both layers emit LoopClosure events into self.closure_queue.

    Thread safety
    -------------
    process() must be called from a single thread.
    closure_queue, corrected_poses, pose_graph_updated are safe from any thread.
    """

    def __init__(
        self,
        config: AppConfig,
        *,
        force_mock: bool = False,
        on_loop_closure: Optional[Callable[[LoopClosure], None]] = None,
    ) -> None:
        self.config   = config
        self._running = False

        # ── Probe and select back-end ────────────────────────────────────────
        if force_mock:
            log.info("SLAMEngine: force_mock=True → using mock back-end.")
            self._backend = _MockBackend()
            self._using_rtabmap = False
        else:
            available, detail = detect_rtabmap()
            log.info("RTAB-Map detection: available=%s  %s", available, detail)
            if available:
                try:
                    self._backend = _RTABMapBackend(config.slam, config.camera)
                    self._using_rtabmap = True
                    log.info("SLAMEngine: using RTAB-Map back-end.")
                except Exception as exc:
                    log.error(
                        "RTAB-Map back-end init failed – falling back to mock.\n%s",
                        traceback.format_exc(),
                    )
                    self._backend = _MockBackend()
                    self._using_rtabmap = False
            else:
                log.warning(
                    "RTAB-Map unavailable (%s) → using mock back-end.", detail
                )
                self._backend = _MockBackend()
                self._using_rtabmap = False

        # ── Standalone loop-closure layer (always active) ────────────────────
        self.closure_queue:      queue.Queue[LoopClosure] = queue.Queue()
        self.pose_graph_updated: threading.Event          = threading.Event()
        self.corrected_poses:    Dict[int, np.ndarray]    = {}
        self._all_poses:         Dict[int, np.ndarray]    = {}

        self._lcd = LoopClosureDetector(
            config   = config.loop,
            cam_config = config.camera,
            on_closure = self._handle_standalone_closure,
        )
        self._user_callback    = on_loop_closure
        self._frame_count      = 0
        self._lc_every_n       = max(1, int(30 / max(config.loop.top_k_candidates, 1)))

        log.info(
            "SLAMEngine init complete  backend=%s  lcd_every_n=%d  "
            "loop_closure_enabled=%s",
            self._backend.backend_name,
            self._lc_every_n,
            config.loop.enabled,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            log.debug("SLAMEngine.start() called while already running.")
            return
        self._running = True
        log.info(
            "SLAMEngine started  backend=%s  rtabmap=%s",
            self._backend.backend_name, self._using_rtabmap,
        )

    def stop(self) -> None:
        if not self._running:
            return
        self._backend.close()
        self._running = False
        log.info(
            "SLAMEngine stopped  frames=%d  poses_stored=%d",
            self._frame_count, len(self._all_poses),
        )

    def __enter__(self) -> "SLAMEngine":
        self.start()
        return self

    def __exit__(self, *_) -> bool:
        self.stop()
        return False

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def process(self, frame: RGBDFrame) -> SLAMResult:
        if not self._running:
            raise RuntimeError(
                "SLAMEngine.process() called before start(). "
                "Use 'with SLAMEngine(...) as engine:' or call engine.start()."
            )

        # Delegate to the active back-end
        result = self._backend.process(frame)
        self._frame_count += 1

        # Store pose for pose-graph optimisation
        if result.pose is not None:
            self._all_poses[frame.frame_id] = result.pose

        # Feed standalone LCD (decimated to avoid redundancy with RTAB-Map)
        if config := self.config:
            if config.loop.enabled and (self._frame_count % self._lc_every_n == 0):
                self._lcd.add_keyframe(frame, pose=result.pose)

        # Drain standalone LCD events and merge with RTAB-Map closure
        pending = self._lcd.pending_closures()
        if pending:
            if not result.loop_closed:
                result.loop_closed  = True
                result.loop_closure = pending[-1]
            for lc in pending:
                self.closure_queue.put(lc)

        # If RTAB-Map fired a closure, also push it to our queue
        if result.loop_closed and result.loop_closure is not None and not pending:
            self.closure_queue.put(result.loop_closure)

        # Verbose per-frame log (controlled by AppConfig.verbose)
        if self.config.verbose:
            log.debug(
                "Frame %5d | pose=%s | loop=%s | lost=%s | map=%d | dt=%.1f ms",
                result.frame_id,
                f"t=[{result.pose[0,3]:+.3f},{result.pose[1,3]:+.3f},{result.pose[2,3]:+.3f}]"
                    if result.pose is not None else "None",
                result.loop_closed,
                result.lost,
                result.map_size,
                result.processing_time_s * 1000,
            )

        return result

    # ------------------------------------------------------------------
    # Map / state access
    # ------------------------------------------------------------------

    def get_point_cloud(self) -> np.ndarray:
        return self._backend.get_point_cloud()

    def reset(self) -> None:
        log.info("SLAMEngine.reset()")
        self._backend.reset()
        self._all_poses.clear()
        self._frame_count = 0
        log.info("  Reset complete.")

    @property
    def using_rtabmap(self) -> bool:
        """True when the real RTAB-Map back-end is active."""
        return self._using_rtabmap

    # ------------------------------------------------------------------
    # Loop-closure internals
    # ------------------------------------------------------------------

    def _handle_standalone_closure(self, lc: LoopClosure) -> None:
        """Called by the standalone LoopClosureDetector on its own thread."""
        log.info(
            "Standalone LC: frame %d ↔ %d  inliers=%d  score=%.3f",
            lc.query_id, lc.match_id, lc.inlier_count, lc.score,
        )
        if self.config.loop.run_pose_graph_opt:
            try:
                corrected = self._lcd.optimise_poses(dict(self._all_poses))
                self.corrected_poses.update(corrected)
                self.pose_graph_updated.set()
                log.info("  Pose-graph updated with %d poses.", len(corrected))
            except Exception as exc:
                log.error("  Pose-graph optimisation failed: %s", exc)

        if self._user_callback:
            try:
                self._user_callback(lc)
            except Exception as exc:
                log.error("  on_loop_closure callback raised: %s", exc)

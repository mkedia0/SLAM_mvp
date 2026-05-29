from __future__ import annotations

import math
import time
from dataclasses import dataclass

import networkx as nx
import numpy as np

from .types import PoseResult, RGBDFrame


def _load_cv2():
    import cv2

    return cv2


def inv_t(t: np.ndarray) -> np.ndarray:
    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = t[:3, :3].T
    out[:3, 3] = -out[:3, :3] @ t[:3, 3]
    return out


def transform_points(t: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ t[:3, :3].T + t[:3, 3]


def rigid_transform(a: np.ndarray, b: np.ndarray, w: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    if len(a) < 6:
        return np.eye(4), float("inf")
    if w is None:
        w = np.ones(len(a), dtype=np.float64)
    w = w.astype(np.float64)
    w /= max(w.sum(), 1e-9)
    ca = (a * w[:, None]).sum(axis=0)
    cb = (b * w[:, None]).sum(axis=0)
    aa, bb = a - ca, b - cb
    h = (aa * w[:, None]).T @ bb
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T
    t = cb - r @ ca
    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = r
    out[:3, 3] = t
    err = np.linalg.norm(transform_points(out, a) - b, axis=1)
    return out, float(np.median(err))


def backproject_pixels(kp_xy: np.ndarray, depth: np.ndarray, intr) -> tuple[np.ndarray, np.ndarray]:
    h, w = depth.shape
    u = np.rint(kp_xy[:, 0]).astype(int)
    v = np.rint(kp_xy[:, 1]).astype(int)
    ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    z = np.zeros(len(kp_xy), dtype=np.float32)
    z[ok] = depth[v[ok], u[ok]]
    ok &= z > 0.05
    x = (u.astype(np.float64) - intr.cx) * z / intr.fx
    y = (v.astype(np.float64) - intr.cy) * z / intr.fy
    return np.column_stack([x, y, z]), ok


def visual_signature(rgb: np.ndarray) -> np.ndarray:
    cv2 = _load_cv2()
    small = cv2.resize(rgb, (96, 72), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256]).reshape(-1)
    hist = hist.astype(np.float32)
    hist /= max(float(np.linalg.norm(hist)), 1e-6)
    return hist


@dataclass
class Keyframe:
    key: str
    pose: np.ndarray
    signature: np.ndarray
    rgb_gray: np.ndarray
    depth: np.ndarray
    confidence: np.ndarray | None
    intrinsics: object
    keypoints: list
    descriptors: np.ndarray | None


class GraphSLAMBackend:
    """CPU RGBD visual odometry + lightweight pose graph loop closure backend."""

    def __init__(self, keyframe_distance_m: float = 0.12, min_loop_gap: int = 20):
        cv2 = _load_cv2()
        self.orb = cv2.ORB_create(nfeatures=1200, fastThreshold=7)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.graph = nx.Graph()
        self.keyframes: list[Keyframe] = []
        self.last_frame: RGBDFrame | None = None
        self.last_pose = np.eye(4, dtype=np.float64)
        self.keyframe_distance_m = keyframe_distance_m
        self.min_loop_gap = min_loop_gap
        self.last_edges: list[tuple[str, str, str, np.ndarray, float, float]] = []

    def process(self, frame: RGBDFrame) -> PoseResult:
        start = time.perf_counter()
        cv2 = _load_cv2()
        gray = cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2GRAY)
        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        rel = np.eye(4, dtype=np.float64)
        tracking_ok = True
        matches_n = inliers_n = 0
        if self.last_frame is not None:
            prev_gray = cv2.cvtColor(self.last_frame.rgb, cv2.COLOR_RGB2GRAY)
            prev_kp, prev_desc = self.orb.detectAndCompute(prev_gray, None)
            rel, tracking_ok, matches_n, inliers_n = self._estimate_between(
                prev_kp, prev_desc, self.last_frame.depth_m, self.last_frame.confidence, self.last_frame.ref.intrinsics,
                keypoints, descriptors, frame.depth_m, frame.confidence, frame.ref.intrinsics,
            )
            self.last_pose = self.last_pose @ rel
        self.last_frame = frame

        loop_with = None
        place_score = 0.0
        loop_closed = False
        if self._should_keyframe(frame.key, self.last_pose):
            kf = Keyframe(
                frame.key,
                self.last_pose.copy(),
                visual_signature(frame.rgb),
                gray,
                frame.depth_m.copy(),
                frame.confidence.copy() if frame.confidence is not None else None,
                frame.ref.intrinsics,
                keypoints,
                descriptors,
            )
            self._add_keyframe(kf)
            loop_with, place_score = self._try_loop_closure(kf)
            loop_closed = loop_with is not None
        result = PoseResult(
            frame_key=frame.key,
            pose_c2w=self.last_pose.copy(),
            tracking_ok=tracking_ok,
            matches=matches_n,
            inliers=inliers_n,
            loop_closed=loop_closed,
            loop_with=loop_with,
            place_score=place_score,
            map_points=sum(kf.depth.size for kf in self.keyframes),
            latency_s=time.perf_counter() - start,
        )
        return result

    def _estimate_between(
        self,
        kp_a,
        desc_a,
        depth_a,
        conf_a,
        intr_a,
        kp_b,
        desc_b,
        depth_b,
        conf_b,
        intr_b,
    ) -> tuple[np.ndarray, bool, int, int]:
        if desc_a is None or desc_b is None or len(desc_a) < 12 or len(desc_b) < 12:
            return np.eye(4), False, 0, 0
        matches = sorted(self.matcher.match(desc_a, desc_b), key=lambda m: m.distance)[:250]
        pts_a_2d = np.array([kp_a[m.queryIdx].pt for m in matches], dtype=np.float32)
        pts_b_2d = np.array([kp_b[m.trainIdx].pt for m in matches], dtype=np.float32)
        pts_a, ok_a = backproject_pixels(pts_a_2d, depth_a, intr_a)
        pts_b, ok_b = backproject_pixels(pts_b_2d, depth_b, intr_b)
        ok = ok_a & ok_b
        if ok.sum() < 8:
            return np.eye(4), False, len(matches), int(ok.sum())
        weights = np.ones(ok.sum(), dtype=np.float64)
        if conf_a is not None:
            uv = np.rint(pts_a_2d[ok]).astype(int)
            weights *= conf_a[uv[:, 1].clip(0, conf_a.shape[0] - 1), uv[:, 0].clip(0, conf_a.shape[1] - 1)]
        if conf_b is not None:
            uv = np.rint(pts_b_2d[ok]).astype(int)
            weights *= conf_b[uv[:, 1].clip(0, conf_b.shape[0] - 1), uv[:, 0].clip(0, conf_b.shape[1] - 1)]
        rel, err = rigid_transform(pts_a[ok], pts_b[ok], weights)
        residual = np.linalg.norm(transform_points(rel, pts_a[ok]) - pts_b[ok], axis=1)
        inliers = residual < max(0.08, err * 2.5)
        if inliers.sum() >= 8:
            rel, err = rigid_transform(pts_a[ok][inliers], pts_b[ok][inliers], weights[inliers])
        sane = math.isfinite(err) and err < 0.25 and np.linalg.norm(rel[:3, 3]) < 1.0
        return rel, sane, len(matches), int(inliers.sum())

    def _should_keyframe(self, key: str, pose: np.ndarray) -> bool:
        if not self.keyframes:
            return True
        if self.keyframes[-1].key == key:
            return False
        dist = np.linalg.norm(pose[:3, 3] - self.keyframes[-1].pose[:3, 3])
        return dist >= self.keyframe_distance_m or len(self.keyframes) < 5

    def _add_keyframe(self, kf: Keyframe) -> None:
        self.graph.add_node(kf.key, pose=kf.pose)
        if self.keyframes:
            prev = self.keyframes[-1]
            rel = inv_t(prev.pose) @ kf.pose
            self.graph.add_edge(prev.key, kf.key, kind="odometry", transform=rel, information=1.0, score=1.0)
            self.last_edges.append((prev.key, kf.key, "odometry", rel, 1.0, 1.0))
        self.keyframes.append(kf)

    def _try_loop_closure(self, kf: Keyframe) -> tuple[str | None, float]:
        if len(self.keyframes) < self.min_loop_gap:
            return None, 0.0
        candidates = self.keyframes[: -self.min_loop_gap]
        if not candidates:
            return None, 0.0
        scores = [(float(kf.signature @ old.signature), old) for old in candidates]
        score, old = max(scores, key=lambda s: s[0])
        if score < 0.90:
            return None, score
        rel, ok, matches, inliers = self._estimate_between(
            old.keypoints, old.descriptors, old.depth, old.confidence, old.intrinsics,
            kf.keypoints, kf.descriptors, kf.depth, kf.confidence, kf.intrinsics,
        )
        if not ok or inliers < 20:
            return None, score
        self.graph.add_edge(old.key, kf.key, kind="loop", transform=rel, information=5.0, score=score)
        self.last_edges.append((old.key, kf.key, "loop", rel, 5.0, score))
        self._relax_loop(old.key, kf.key, old.pose @ rel)
        return old.key, score

    def _relax_loop(self, from_key: str, to_key: str, target_pose: np.ndarray) -> None:
        keys = [kf.key for kf in self.keyframes]
        if from_key not in keys or to_key not in keys:
            return
        i, j = keys.index(from_key), keys.index(to_key)
        if j <= i:
            return
        current = self.keyframes[j].pose
        delta = target_pose[:3, 3] - current[:3, 3]
        span = max(1, j - i)
        for n in range(i + 1, len(self.keyframes)):
            alpha = min(1.0, max(0.0, (n - i) / span))
            self.keyframes[n].pose[:3, 3] += delta * alpha
            self.graph.nodes[self.keyframes[n].key]["pose"] = self.keyframes[n].pose
        self.last_pose = self.keyframes[-1].pose.copy()

    def consume_edges(self) -> list[tuple[str, str, str, np.ndarray, float, float]]:
        edges, self.last_edges = self.last_edges, []
        return edges

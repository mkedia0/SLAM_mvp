from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from .types import PoseResult, RGBDFrame


def _mat_to_json(mat: np.ndarray) -> str:
    return json.dumps(np.asarray(mat, dtype=float).round(8).tolist())


class SessionStore:
    """SQLite session store with WAL so multiple readers can open one run."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS frames (
              frame_key TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              frame_id INTEGER NOT NULL,
              timestamp REAL NOT NULL,
              rgb_path TEXT NOT NULL,
              depth_path TEXT NOT NULL,
              confidence_path TEXT,
              intrinsics_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS poses (
              frame_key TEXT PRIMARY KEY,
              pose_json TEXT NOT NULL,
              tracking_ok INTEGER NOT NULL,
              matches INTEGER NOT NULL,
              inliers INTEGER NOT NULL,
              loop_closed INTEGER NOT NULL,
              loop_with TEXT,
              place_score REAL,
              map_points INTEGER,
              latency_s REAL
            );
            CREATE TABLE IF NOT EXISTS edges (
              edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
              from_key TEXT NOT NULL,
              to_key TEXT NOT NULL,
              kind TEXT NOT NULL,
              transform_json TEXT NOT NULL,
              information REAL NOT NULL,
              score REAL DEFAULT 0.0
            );
            CREATE INDEX IF NOT EXISTS idx_frames_time ON frames(timestamp);
            """
        )

    def add_frame(self, frame: RGBDFrame) -> None:
        intr = frame.ref.intrinsics
        self.conn.execute(
            """
            INSERT OR REPLACE INTO frames VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                frame.key,
                frame.ref.source_id,
                frame.ref.frame_id,
                frame.ref.timestamp,
                str(frame.ref.rgb_path),
                str(frame.ref.depth_path),
                str(frame.ref.confidence_path) if frame.ref.confidence_path else None,
                json.dumps(intr.__dict__),
            ),
        )

    def add_pose(self, result: PoseResult) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO poses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.frame_key,
                _mat_to_json(result.pose_c2w),
                int(result.tracking_ok),
                result.matches,
                result.inliers,
                int(result.loop_closed),
                result.loop_with,
                result.place_score,
                result.map_points,
                result.latency_s,
            ),
        )

    def add_edge(
        self,
        from_key: str,
        to_key: str,
        kind: str,
        transform: np.ndarray,
        information: float,
        score: float = 0.0,
    ) -> None:
        self.conn.execute(
            "INSERT INTO edges(from_key, to_key, kind, transform_json, information, score) VALUES (?, ?, ?, ?, ?, ?)",
            (from_key, to_key, kind, _mat_to_json(transform), float(information), float(score)),
        )

    def close(self) -> None:
        self.conn.close()

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import numpy as np


def load_poses(conn: sqlite3.Connection) -> list[tuple[str, np.ndarray, int, int, int]]:
    rows = conn.execute(
        "SELECT frame_key, pose_json, tracking_ok, matches, inliers FROM poses ORDER BY rowid"
    ).fetchall()
    return [(key, np.array(json.loads(pose), dtype=float), ok, matches, inliers) for key, pose, ok, matches, inliers in rows]


def plot_trajectory(poses: list[tuple[str, np.ndarray, int, int, int]], output: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mnet_slam_mpl"))
    import matplotlib.pyplot as plt

    xyz = np.array([pose[:3, 3] for _, pose, *_ in poses])
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6), dpi=140)
    if len(xyz):
        ax.plot(xyz[:, 0], xyz[:, 2], "-o", markersize=2.5, linewidth=1.2)
        ax.scatter([xyz[0, 0]], [xyz[0, 2]], c="green", label="start", s=35)
        ax.scatter([xyz[-1, 0]], [xyz[-1, 2]], c="red", label="end", s=35)
    ax.set_title("mNET RGBD-SLAM Trajectory")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect an mNET SLAM SQLite session.")
    parser.add_argument("session")
    parser.add_argument("--plot", default=None, help="Write a top-down trajectory PNG.")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.session)
    poses = load_poses(conn)
    counts = {
        table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ["frames", "poses", "edges"]
    }
    edge_kinds = dict(conn.execute("SELECT kind, count(*) FROM edges GROUP BY kind").fetchall())
    tracking_ok = sum(ok for _, _, ok, _, _ in poses)
    mean_inliers = float(np.mean([inliers for *_, inliers in poses])) if poses else 0.0
    if args.plot:
        plot_trajectory(poses, Path(args.plot))
    summary = {
        "session": str(Path(args.session).resolve()),
        "counts": counts,
        "edge_kinds": edge_kinds,
        "tracking_ok": f"{tracking_ok}/{len(poses)}",
        "mean_inliers": round(mean_inliers, 1),
        "plot": str(Path(args.plot).resolve()) if args.plot else None,
    }
    print(json.dumps(summary, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

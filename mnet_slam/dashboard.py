from __future__ import annotations

import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


STATIC_DIR = Path(__file__).parent / "static"


def _connect(session: Path) -> sqlite3.Connection:
    uri = f"file:{session.resolve()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _read_pose_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.frame_key, f.source_id, f.frame_id, f.timestamp, p.pose_json,
               p.tracking_ok, p.matches, p.inliers, p.loop_closed, p.loop_with,
               p.place_score, p.latency_s
        FROM poses p
        LEFT JOIN frames f ON f.frame_key = p.frame_key
        ORDER BY f.timestamp, f.source_id, f.frame_id
        """
    ).fetchall()
    out = []
    for row in rows:
        pose = json.loads(row[4])
        out.append(
            {
                "frame_key": row[0],
                "source_id": row[1],
                "frame_id": row[2],
                "timestamp": row[3],
                "translation": [pose[0][3], pose[1][3], pose[2][3]],
                "tracking_ok": bool(row[5]),
                "matches": row[6],
                "inliers": row[7],
                "loop_closed": bool(row[8]),
                "loop_with": row[9],
                "place_score": row[10] or 0.0,
                "latency_ms": (row[11] or 0.0) * 1000.0,
            }
        )
    return out


def dashboard_payload(session: Path) -> dict:
    conn = _connect(session)
    try:
        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ["frames", "poses", "edges"]
        }
        edge_kinds = dict(conn.execute("SELECT kind, count(*) FROM edges GROUP BY kind").fetchall())
        sources = [
            {"source_id": row[0], "frames": row[1]}
            for row in conn.execute("SELECT source_id, count(*) FROM frames GROUP BY source_id ORDER BY source_id")
        ]
        poses = _read_pose_rows(conn)
        recent = poses[-12:]
        loops = [p for p in poses if p["loop_closed"]]
        return {
            "session": str(session.resolve()),
            "counts": counts,
            "edge_kinds": edge_kinds,
            "sources": sources,
            "trajectory": poses,
            "recent": recent,
            "loops": loops,
        }
    finally:
        conn.close()


class DashboardHandler(BaseHTTPRequestHandler):
    session_path: Path

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = (STATIC_DIR / "dashboard.html").read_bytes()
            self._send(200, body, "text/html; charset=utf-8")
            return
        if parsed.path == "/static/dashboard.js":
            self._send(200, (STATIC_DIR / "dashboard.js").read_bytes(), "application/javascript")
            return
        if parsed.path == "/static/dashboard.css":
            self._send(200, (STATIC_DIR / "dashboard.css").read_bytes(), "text/css")
            return
        if parsed.path == "/api/session":
            qs = parse_qs(parsed.query)
            session = Path(qs.get("session", [str(self.session_path)])[0])
            try:
                body = json.dumps(dashboard_payload(session)).encode()
                self._send(200, body, "application/json")
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
            return
        self._send(404, b"not found", "text/plain")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the mNET SLAM dashboard.")
    parser.add_argument("--session", required=True, help="SQLite session file to inspect.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = type("BoundDashboardHandler", (DashboardHandler,), {"session_path": Path(args.session)})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(json.dumps({"url": url, "session": str(Path(args.session).resolve())}, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

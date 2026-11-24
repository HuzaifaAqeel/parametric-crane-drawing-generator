"""HTTP server for the parametric crane drawing generator.

Python standard library only: http.server ThreadingHTTPServer + sqlite3.
Run with: python3 server.py  (or ./run.sh)
Serves the static UI on / and a JSON API under /api.
"""

import json
import os
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crane import build_svg, derive, validate_inputs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "crane.db")
HOST = "127.0.0.1"
PORT = 8000

LIST_FIELDS = ("id", "name", "span_m", "capacity_t", "lift_height_m",
               "duty_class", "updated_at")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS designs ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL,"
        "span_m REAL NOT NULL,"
        "capacity_t REAL NOT NULL,"
        "lift_height_m REAL NOT NULL,"
        "trolley_position_m REAL NOT NULL,"
        "duty_class TEXT NOT NULL,"
        "notes TEXT NOT NULL DEFAULT '',"
        "created_at TEXT NOT NULL,"
        "updated_at TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def row_to_inputs(row):
    return {
        "name": row["name"],
        "span_m": row["span_m"],
        "capacity_t": row["capacity_t"],
        "lift_height_m": row["lift_height_m"],
        "trolley_position_m": row["trolley_position_m"],
        "duty_class": row["duty_class"],
        "notes": row["notes"],
    }


def design_with_derived(row, include_svg=False):
    inputs = row_to_inputs(row)
    derived = derive(inputs)
    design = {
        "id": row["id"],
        "inputs": inputs,
        "derived": derived,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_svg:
        design["svg"] = build_svg(inputs, derived)
    return design


def warnings_for(derived):
    warnings = []
    if not derived["deflection_ok"]:
        warnings.append(
            "Deflection check FAILED: live-load deflection %.2f mm exceeds "
            "the L/750 limit of %.2f mm. Increase girder depth (higher duty "
            "class), reduce span or reduce capacity."
            % (derived["deflection_live_mm"], derived["deflection_limit_mm"])
        )
    return warnings


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep stdout quiet
        pass

    # -- helpers ---------------------------------------------------------
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return None, {"error": "Request body is empty."}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None, {"error": "Request body is not valid JSON."}
        if not isinstance(data, dict):
            return None, {"error": "Request body must be a JSON object."}
        return data, None

    def validated(self, data):
        inputs, errors = validate_inputs(data)
        if errors:
            self.send_json(400, {"errors": errors})
            return None
        return inputs

    # -- routing ---------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return
        if path == "/api/designs":
            conn = get_db()
            rows = conn.execute(
                "SELECT %s FROM designs ORDER BY updated_at DESC, id DESC"
                % ", ".join(LIST_FIELDS)
            ).fetchall()
            conn.close()
            self.send_json(200, {"designs": [dict(r) for r in rows]})
            return
        if path.startswith("/api/designs/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[3].isdigit():
                self.get_design(int(parts[3]))
                return
            if len(parts) == 5 and parts[3].isdigit() and parts[4] == "drawing.svg":
                self.get_drawing(int(parts[3]))
                return
            self.send_json(404, {"error": "Not found."})
            return
        self.serve_static(path)

    def get_design(self, design_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        conn.close()
        if row is None:
            self.send_json(404, {"error": "Design %d not found." % design_id})
            return
        self.send_json(200, design_with_derived(row, include_svg=True))

    def get_drawing(self, design_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM designs WHERE id = ?", (design_id,)).fetchone()
        conn.close()
        if row is None:
            self.send_json(404, {"error": "Design %d not found." % design_id})
            return
        inputs = row_to_inputs(row)
        svg = build_svg(inputs, derive(inputs))
        body = svg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(body)))
        self.send_header(
            "Content-Disposition",
            'attachment; filename="crane-design-%d.svg"' % design_id,
        )
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/preview":
            data, err = self.read_json_body()
            if err:
                self.send_json(400, err)
                return
            inputs = self.validated(data)
            if inputs is None:
                return
            derived = derive(inputs)
            self.send_json(200, {
                "inputs": inputs,
                "derived": derived,
                "warnings": warnings_for(derived),
                "svg": build_svg(inputs, derived),
            })
            return
        if parsed.path == "/api/designs":
            data, err = self.read_json_body()
            if err:
                self.send_json(400, err)
                return
            inputs = self.validated(data)
            if inputs is None:
                return
            conn = get_db()
            stamp = now_iso()
            cur = conn.execute(
                "INSERT INTO designs (name, span_m, capacity_t, lift_height_m,"
                " trolley_position_m, duty_class, notes, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (inputs["name"], inputs["span_m"], inputs["capacity_t"],
                 inputs["lift_height_m"], inputs["trolley_position_m"],
                 inputs["duty_class"], inputs["notes"], stamp, stamp),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM designs WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            conn.close()
            self.send_json(201, design_with_derived(row, include_svg=False))
            return
        self.send_json(404, {"error": "Not found."})

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "designs" and parts[3].isdigit():
            design_id = int(parts[3])
            data, err = self.read_json_body()
            if err:
                self.send_json(400, err)
                return
            inputs = self.validated(data)
            if inputs is None:
                return
            conn = get_db()
            row = conn.execute(
                "SELECT * FROM designs WHERE id = ?", (design_id,)
            ).fetchone()
            if row is None:
                conn.close()
                self.send_json(404, {"error": "Design %d not found." % design_id})
                return
            conn.execute(
                "UPDATE designs SET name=?, span_m=?, capacity_t=?,"
                " lift_height_m=?, trolley_position_m=?, duty_class=?,"
                " notes=?, updated_at=? WHERE id=?",
                (inputs["name"], inputs["span_m"], inputs["capacity_t"],
                 inputs["lift_height_m"], inputs["trolley_position_m"],
                 inputs["duty_class"], inputs["notes"], now_iso(), design_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM designs WHERE id = ?", (design_id,)
            ).fetchone()
            conn.close()
            self.send_json(200, design_with_derived(row, include_svg=False))
            return
        self.send_json(404, {"error": "Not found."})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.split("/")
        if len(parts) == 4 and parts[1] == "api" and parts[2] == "designs" and parts[3].isdigit():
            design_id = int(parts[3])
            conn = get_db()
            cur = conn.execute("DELETE FROM designs WHERE id = ?", (design_id,))
            conn.commit()
            conn.close()
            if cur.rowcount == 0:
                self.send_json(404, {"error": "Design %d not found." % design_id})
                return
            self.send_response(204)
            self.end_headers()
            return
        self.send_json(404, {"error": "Not found."})

    # -- static files ----------------------------------------------------
    def serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        safe = os.path.normpath(urllib.parse.unquote(path)).lstrip("/")
        full = os.path.join(STATIC_DIR, safe)
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self.send_json(404, {"error": "Not found."})
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    get_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Crane drawing generator running at http://%s:%d" % (HOST, PORT))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.shutdown()


if __name__ == "__main__":
    main()

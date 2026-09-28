"""Run the UI against the real engine: python3 src/ui/serve.py  → http://127.0.0.1:8000

Standard library only. The page (built fresh from app_template.html on every load) talks to:

    GET  /api/health     {"ok": true, "muted": [[type, equipment_id], ...]}
    POST /api/suggest    BookingRequest  → {"suggestion_set": {...}, "errors": [...]}
    POST /api/feedback   [FeedbackEvent] → {"saved": [...]}      (appends to data/feedback_log.json)
    GET  /api/plan       {"bookings": [...] | null}             (last confirmed plan)
    POST /api/book       BookingRequest  → {"saved": [...]}     (writes data/confirmed_bookings.csv)

    python3 src/ui/serve.py --reset-demo   deletes the confirmed plan and empties the feedback log first
    python3 src/ui/serve.py --placeholders explanation panels open but say "to be filled in" (demo)

Opened as a plain file (no server), the page still works on the baked-in SuggestionSet.
Local demo only: binds to 127.0.0.1, no authentication.
"""
import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ui.build import build_html  # noqa: E402
from src.ui.engine import price_request, save_feedback, muted_pairs, load_plan, save_plan, reset_demo  # noqa: E402

MAX_BODY = 256 * 1024
PLACEHOLDERS = False  # set by --placeholders


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(n) or b"null")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html, _ = build_html(placeholders=PLACEHOLDERS)
            return self._send(200, html.encode(), "text/html")
        if self.path == "/api/health":
            return self._send(200, {"ok": True, "muted": sorted(map(list, muted_pairs()))})
        if self.path == "/api/plan":
            return self._send(200, {"bookings": load_plan()})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._json_body()
            if self.path == "/api/suggest":
                sset, errors = price_request(body)
                return self._send(200, {"suggestion_set": sset, "errors": errors})
            if self.path == "/api/feedback":
                if not isinstance(body, list):
                    return self._send(400, {"error": "expected a list of FeedbackEvents"})
                return self._send(200, {"saved": save_feedback(body)})
            if self.path == "/api/book":
                return self._send(200, {"saved": save_plan(body)})
            self._send(404, {"error": "not found"})
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # keep the demo alive, show the problem in the page
            traceback.print_exc()
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("  " + fmt % args + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reset-demo", action="store_true",
                    help="delete data/confirmed_bookings.csv and empty data/feedback_log.json before starting")
    ap.add_argument("--placeholders", action="store_true",
                    help="explanation panels open but say 'to be filled in' (for the demo)")
    args = ap.parse_args()
    global PLACEHOLDERS
    PLACEHOLDERS = args.placeholders
    if args.reset_demo:
        reset_demo()
        print("Demo reset: confirmed plan deleted, feedback log emptied.")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Lab X booking assistant: http://127.0.0.1:{args.port}   (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

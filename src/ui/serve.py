"""Run the UI against the real engine: python3 src/ui/serve.py  → http://127.0.0.1:8000

One app, two assistants. The start page (home.html) lets the researcher choose:
    GET  /            start page
    GET  /plan        experiment plan assistant (plan.html; API in plan_api.py, under /api/plan/...)
    GET  /bookings    booking assistant (built fresh from app_template.html on every load)
Both pages share the team's lab profile (profile.js, GET /api/labs), kept only in the browser.

Standard library only. The booking page talks to:

    GET  /api/health     {"ok": true, "muted": [[type, equipment_id], ...], "llm": {"ollama": bool, "claude": bool}}
    POST /api/suggest    BookingRequest (+ "use_llm", "provider") → {"suggestion_set": {...}, "errors": [...]}
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
from urllib.parse import urlsplit
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ui.build import build_html  # noqa: E402
from src.ui.engine import price_request, save_feedback, muted_pairs, load_plan, save_plan, reset_demo  # noqa: E402
from src.ui import plan_api  # noqa: E402

HOME = Path(__file__).with_name("home.html")

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
        self.path = urlsplit(self.path).path   # "/plan?values=1" is "/plan"
        if self.path == "/":
            return self._send(200, HOME.read_bytes(), "text/html")
        if self.path in ("/bookings", "/index.html"):
            html, _ = build_html(placeholders=PLACEHOLDERS)
            return self._send(200, html.encode(), "text/html")
        if self.path == "/plan":
            return self._send(200, plan_api.PAGE.read_bytes(), "text/html")
        if self.path == "/profile.js":
            return self._send(200, plan_api.PROFILE_JS.read_bytes(), "text/javascript")
        if self.path == "/api/labs":
            return self._send(200, plan_api.labs())
        if self.path == "/api/plan/catalog":
            return self._send(200, plan_api.catalog())
        if self.path == "/api/health":
            return self._send(200, {"ok": True, "muted": sorted(map(list, muted_pairs())),
                                    "llm": plan_api.llm_status()})
        if self.path == "/api/plan":
            return self._send(200, {"bookings": load_plan()})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = self._json_body()
            if self.path == "/api/plan/suggest":
                return self._send(*plan_api.suggest(body or {}))
            if self.path == "/api/plan/feedback":
                if not isinstance(body, list):
                    return self._send(400, {"error": "expected a list of FeedbackEvents"})
                return self._send(200, {"saved": plan_api.save_feedback(body)})
            if self.path == "/api/suggest":
                llm = None
                if body.get("use_llm"):   # optional AI for bookings too (src/ai/booking_ai.py)
                    from src.ai.llm.providers import get_llm
                    llm = get_llm(body.get("provider") if body.get("provider") in ("ollama", "claude") else None)
                sset, errors = price_request(body, llm=llm)
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
    st = plan_api.llm_status()
    ai = "AI: " + ", ".join(k for k, v in st.items() if v) if any(st.values()) else "no AI: rules + templates"
    print(f"Lab X assistant: http://127.0.0.1:{args.port}   (plan + bookings; {ai}; Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

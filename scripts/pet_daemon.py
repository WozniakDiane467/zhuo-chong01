"""
pet_daemon.py - Background bridge daemon for desktop pet state management.

Runs a lightweight HTTP server that receives state commands from hooks/manual use.
State changes are written to ~/.workbuddy/pet_state.json, which the desktop pet
polls every 500ms. State persists until explicitly changed (no auto-revert).

Endpoints:
    POST /set     {"state": "thinking", "message": "正在思考..."}  →  set pet state
    GET  /set?state=thinking&msg=Hello                            →  set pet state (GET form)
    POST /idle                                                       →  force idle
    GET  /idle                                                       →  force idle
    GET  /status                                                     →  current state info
    POST /confirm   {"tool_name","tool_input","summary","timeout"} → create confirm request
    POST /respond   {"request_id","decision"}                      → pet decision (allow/deny/remember)
    GET  /pending                                                  → list pending confirm requests
    GET  /confirm/result?request_id=cf-...                         → confirm result (pending/decided)

Usage:
    python pet_daemon.py [--port 19877]
"""

import os
import sys
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from pet_constants import DAEMON_PORT, STATE_FILE
import pet_confirm_rules as rules

MIN_DWELL = 0.3  # Minimum seconds a state must persist before being overwritten
CONFIRM_RETENTION = 300  # seconds to keep decided requests before cleanup


class PetDaemon:
    def __init__(self, config_file: str = None):
        self.current_state = "idle"
        self.current_message = ""
        self.last_update = time.time()
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._dwell_timer = None
        self._pending_state = None
        self._pending_message = ""
        self.confirm_lock = threading.Lock()
        self.confirm_requests = {}      # request_id -> dict
        self._confirm_seq = 0
        self._remembered = None         # (tool_name, tool_input) from last remember
        self.config_file = config_file

    def set_state(self, state: str, message: str = ""):
        with self.lock:
            elapsed = time.time() - self.last_update
            if elapsed < MIN_DWELL and self.current_state != state:
                # Too fast — schedule this new state for later
                self._pending_state = state
                self._pending_message = message
                if self._dwell_timer is None:
                    delay = MIN_DWELL - elapsed + 0.05
                    self._dwell_timer = threading.Timer(delay, self._apply_pending)
                    self._dwell_timer.daemon = True
                    self._dwell_timer.start()
                return

            # Only cancel pending timer if we're switching to a different state
            if self._dwell_timer is not None and self.current_state != state:
                self._dwell_timer.cancel()
                self._dwell_timer = None
                self._pending_state = None
                self._pending_message = ""

            self._apply_state(state, message)

    def _apply_state(self, state: str, message: str):
        """Actually apply a state change (write to file)."""
        self.current_state = state
        self.current_message = message
        self.last_update = time.time()
        self._write_state_file(state, message)

    def _apply_pending(self):
        """Called by dwell timer to apply a deferred state change."""
        with self.lock:
            if self._pending_state is not None:
                state = self._pending_state
                msg = self._pending_message
                self._pending_state = None
                self._pending_message = ""
                self._dwell_timer = None
                self._apply_state(state, msg)

    def _write_state_file(self, state: str, message: str):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "state": state,
                    "message": message,
                    "timestamp": time.time(),
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[daemon] Failed to write state file: {e}", file=sys.stderr)

    def create_confirm(self, tool_name: str, summary: str, tool_input: dict,
                       timeout: float = 60) -> str:
        with self.confirm_lock:
            self._confirm_seq += 1
            request_id = f"cf-{int(time.time())}-{self._confirm_seq}"
            self.confirm_requests[request_id] = {
                "request_id": request_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
                "summary": summary,
                "created_at": time.time(),
                "timeout": timeout,
                "decision": None,
            }
            return request_id

    def _sweep_expired(self):
        now = time.time()
        for rid, req in list(self.confirm_requests.items()):
            if req["decision"] is None and now - req["created_at"] > req["timeout"]:
                req["decision"] = "deny"
                req["reason"] = "timeout"
            elif req["decision"] is not None and now - req["created_at"] > CONFIRM_RETENTION:
                del self.confirm_requests[rid]

    def get_pending(self) -> list:
        with self.confirm_lock:
            self._sweep_expired()
            return [
                {"request_id": r["request_id"], "tool_name": r["tool_name"],
                 "summary": r["summary"], "created_at": r["created_at"]}
                for r in self.confirm_requests.values()
                if r["decision"] is None
            ]

    def get_confirm_result(self, request_id: str) -> dict:
        with self.confirm_lock:
            self._sweep_expired()
            req = self.confirm_requests.get(request_id)
            if req is None:
                return {"status": "unknown"}
            if req["decision"] is None:
                return {"status": "pending"}
            return {"status": "decided", "decision": req["decision"],
                    "reason": req.get("reason", "")}

    def respond(self, request_id: str, decision: str) -> bool:
        with self.confirm_lock:
            req = self.confirm_requests.get(request_id)
            if req is None:
                return False
            if req["decision"] is not None:
                return False  # already decided, cannot override
            if decision == "remember":
                self._remembered = (req["tool_name"], req.get("tool_input", {}))
                try:
                    rules.remember_rule(req["tool_name"], req.get("tool_input", {}),
                                        self.config_file or rules.CONFIG_FILE)
                except Exception:
                    pass
                req["decision"] = "allow"
                req["reason"] = "remembered"
                return True
            elif decision in ("allow", "deny"):
                req["decision"] = decision
                return True
            return False

    def get_remembered(self):
        with self.confirm_lock:
            return self._remembered

    def get_status(self) -> dict:
        with self.lock:
            elapsed = time.time() - self.last_update
            return {
                "state": self.current_state,
                "message": self.current_message,
                "seconds_since_update": round(elapsed, 1),
            }

    def shutdown(self):
        self._stop_event.set()
        self.set_state("idle", "")


class PetHandler(BaseHTTPRequestHandler):
    daemon: PetDaemon = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)

        if path in ("", "/", "/status"):
            self._send_json(self.daemon.get_status())

        elif path == "/set":
            state = params.get("state", [""])[0]
            msg = params.get("msg", [""])[0]
            if not state:
                self._send_json({"error": "Missing 'state' parameter"}, 400)
                return
            self.daemon.set_state(state, msg)
            self._send_json({"ok": True, "state": state, "message": msg})

        elif path == "/pending":
            self._send_json({"requests": self.daemon.get_pending()})
        elif path in ("/confirm/result", "/result"):
            rid = params.get("request_id", [""])[0]
            self._send_json(self.daemon.get_confirm_result(rid))

        elif path == "/idle":
            self.daemon.set_state("idle", "")
            self._send_json({"ok": True, "state": "idle"})

        else:
            self._send_json({"error": "Unknown endpoint"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        if path in ("/set", "/state"):
            state = data.get("state", "")
            msg = data.get("message", data.get("msg", ""))
            if not state:
                self._send_json({"error": "Missing 'state'"}, 400)
                return
            self.daemon.set_state(state, msg)
            self._send_json({"ok": True, "state": state, "message": msg})
        elif path == "/confirm":
            summary = data.get("summary", "")
            tool_name = data.get("tool_name", "")
            tool_input = data.get("tool_input", {})
            try:
                timeout = float(data.get("timeout", 60))
            except (TypeError, ValueError):
                timeout = 60
            rid = self.daemon.create_confirm(tool_name, summary, tool_input, timeout)
            self._send_json({"ok": True, "request_id": rid})
        elif path == "/respond":
            rid = data.get("request_id", "")
            decision = data.get("decision", "")
            ok = self.daemon.respond(rid, decision)
            if not ok:
                self._send_json({"error": "invalid request_id or decision"}, 400)
                return
            self._send_json({"ok": True, "request_id": rid, "decision": decision})
        elif path == "/idle":
            self.daemon.set_state("idle", "")
            self._send_json({"ok": True, "state": "idle"})
        else:
            self._send_json({"error": "Unknown endpoint"}, 404)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pet state daemon")
    parser.add_argument("--port", type=int, default=DAEMON_PORT)
    args = parser.parse_args()

    daemon = PetDaemon()
    PetHandler.daemon = daemon

    server = HTTPServer(("127.0.0.1", args.port), PetHandler)
    print(f"[daemon] Pet bridge running on http://127.0.0.1:{args.port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[daemon] Shutting down...")
        daemon.shutdown()
        server.shutdown()


if __name__ == "__main__":
    main()

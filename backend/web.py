"""Loopback-only web dashboard server for CYBERGUARD."""
from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from backend.service import analyze_request, dashboard_data, demo_fixture_data, incident_data, set_incident_status

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
MAX_REQUEST_BYTES = 140 * 1024 * 1024


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def log_message(self, format, *args):
        # Avoid writing submitted values or identifiers to the console.
        return

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is empty or exceeds size limit")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("incomplete request body")
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            try:
                return self._json(200, dashboard_data())
            except Exception as exc:
                return self._json(500, {"error": str(exc)})
        if parsed.path == "/api/incidents":
            try:
                return self._json(200, {"incidents": incident_data()})
            except Exception as exc:
                return self._json(500, {"error": str(exc)})
        if parsed.path == "/api/multimedia-config":
            from config.multimedia_config import get_multimedia_config, check_system_capabilities
            return self._json(200, {"config": get_multimedia_config(), "capabilities": check_system_capabilities()})
        if parsed.path == "/api/health":
            return self._json(200, {"status": "ok", "application": "CYBERGUARD Intelligence Dashboard"})
        if parsed.path.startswith("/api/demo-fixture/"):
            try:
                fixture_id = unquote(parsed.path.rsplit("/", 1)[-1])
                return self._json(200, demo_fixture_data(fixture_id))
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:
                return self._json(500, {"error": str(exc)})
        if parsed.path.startswith("/api/"):
            return self._json(404, {"error": "API endpoint not found"})
        self.path = parsed.path or "/"
        return super().do_GET()

    def do_POST(self):
        try:
            payload = self._body()
            if self.path == "/api/analyze":
                return self._json(200, analyze_request(payload, asset_sensitivity=payload.get("asset_sensitivity", "medium")))
            if self.path == "/api/analyze-demo":
                return self._json(200, analyze_request(
                    payload,
                    asset_sensitivity=payload.get("asset_sensitivity", "medium"),
                    persist_incident=False,
                ))
            if self.path == "/api/multimedia-config":
                from config.multimedia_config import update_multimedia_config
                return self._json(200, update_multimedia_config(payload))
            return self._json(404, {"error": "API endpoint not found"})
        except (ValueError, KeyError) as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})

    def do_PATCH(self):
        try:
            parts = [unquote(x) for x in urlparse(self.path).path.split("/") if x]
            if len(parts) != 4 or parts[:2] != ["api", "incidents"] or parts[3] != "status":
                return self._json(404, {"error": "API endpoint not found"})
            payload = self._body()
            incident = set_incident_status(parts[2], payload.get("status"))
            return self._json(200, incident)
        except (ValueError, KeyError) as exc:
            return self._json(400, {"error": str(exc)})
        except Exception as exc:
            return self._json(500, {"error": str(exc)})


def main(argv=None):
    import argparse
    import webbrowser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: loopback only)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open-browser", action="store_true", help="open the dashboard after the server starts")
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("dashboard server is intended for loopback access only")
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"CYBERGUARD dashboard running at http://{args.host}:{args.port}")
    if args.open_browser:
        webbrowser.open(f"http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

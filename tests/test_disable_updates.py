import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from stationbot.provision import disable_updates


def test_disable_updates_persists_flag_without_losing_other_settings():
    state = {"led": {"count": 3}, "updates": {"enabled": True, "interval_minutes": 360}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            state.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        disable_updates(server.server_port)
    finally:
        server.shutdown()
    assert state["updates"] == {"enabled": False, "interval_minutes": 360}
    assert state["led"] == {"count": 3}

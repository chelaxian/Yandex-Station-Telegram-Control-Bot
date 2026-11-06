import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from stationbot.provision import apply_update_policy, suspend_updates


def policy_server(state):
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
    return server


def test_update_policy_preserves_settings_and_normalizes_interval():
    state = {"led": {"count": 3}, "updates": {"enabled": False, "interval_minutes": 9999}}
    server = policy_server(state)
    try:
        apply_update_policy(server.server_port)
    finally:
        server.shutdown()
    assert state["updates"] == {"enabled": True, "interval_minutes": 360}
    assert state["led"] == {"count": 3}


def test_suspend_updates_stops_a_bad_release_without_losing_settings():
    state = {"web": {"api": True}, "updates": {"enabled": True, "interval_minutes": 360}}
    server = policy_server(state)
    try:
        suspend_updates(server.server_port)
    finally:
        server.shutdown()
    assert state["updates"] == {"enabled": False, "interval_minutes": 360}
    assert state["web"] == {"api": True}


def test_bad_update_policy_response_is_rejected():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = json.dumps({"updates": {"enabled": False, "interval_minutes": 360}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(Exception, match="управляемую политику"):
            apply_update_policy(server.server_port)
    finally:
        server.shutdown()

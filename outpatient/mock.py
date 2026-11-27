"""HTTP fixture service for the three simulated source interfaces."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit

from outpatient.data import SOURCES


def fixture_handler(payloads):
    routes = {path: payloads[source] for source, path in SOURCES.items()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = routes.get(urlsplit(self.path).path)
            if data is None:
                self.send_error(404)
                return
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(payloads, host, port):
    with ThreadingHTTPServer((host, port), fixture_handler(payloads)) as server:
        print(f"Synthetic fixture service listening on {host}:{port}", flush=True)
        server.serve_forever()

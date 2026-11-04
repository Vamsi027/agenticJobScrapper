"""Serve the web UI locally.

Usage:
    python -m jobscraper.web               # http://localhost:8000
    python -m jobscraper.web --port 8080

The UI is static (jobscraper/static) and talks to Supabase directly from the
browser, so this is just a file server; GitHub Pages serves the same folder.
Use "localhost" rather than 127.0.0.1 so it matches the redirect URL
allowed in Supabase Auth.
"""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"


class Handler(SimpleHTTPRequestHandler):
    def log_request(self, code="-", size="-"):
        pass  # static file requests are noise

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always serve the latest app.js while developing
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description="Serve the job matching UI locally.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), partial(Handler, directory=str(STATIC_DIR)))
    print(f"Job matches UI at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

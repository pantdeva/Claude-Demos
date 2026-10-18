"""Serve the dashboard locally:  python serve.py   →  http://localhost:8000

Options: --port 8080, --host 0.0.0.0 (to open it from another device on your network).
"""

import argparse
import functools
import http.server
import webbrowser
from pathlib import Path

APP = Path(__file__).parent / "app"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not (APP / "index.html").exists():
        raise SystemExit("app/index.html not found. Run: python build_app.py")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(APP))
    url = f"http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}"
    with http.server.ThreadingHTTPServer((a.host, a.port), handler) as srv:
        print(f"Dashboard running at {url}  (Ctrl+C to stop)")
        if not a.no_browser:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

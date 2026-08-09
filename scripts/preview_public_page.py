"""Serve the public page locally, re-rendering on every request.

Development tooling, not part of the deploy. `python -m lpa.public_page`
writes the file the Action publishes; this serves the same render over HTTP so
the page can be worked on without a build step in the loop.

Two things make it a live preview rather than a static file on disk:

- Every request re-imports `lpa.public_page` and re-reads Storage, so a saved
  edit to the renderer is on screen at the next refresh. Nothing is cached,
  which is the opposite of the Streamlit dashboard's deliberate 15-minute read
  cache — that exists because a served app should not hammer a free-tier
  database, and neither applies to one local reader on SQLite.
- A small script polls `/version` and reloads when the render changes, so
  saving a file refreshes the browser without touching it. The poller is
  injected here and never reaches the published page.

    python scripts/preview_public_page.py [--port 8000]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lpa.storage import connect

RELOADER = """
<script>
(function () {
  var current = null;
  setInterval(function () {
    fetch("/version").then(function (r) { return r.text(); }).then(function (v) {
      if (current === null) { current = v; return; }
      if (v !== current) { location.reload(); }
    }).catch(function () {});
  }, 700);
})();
</script>
"""

ERROR_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Render failed</title>
<style>
  body {{ background: #15161A; color: #E7E8E2; font: 14px/1.6 ui-monospace, Menlo, monospace;
         margin: 0; padding: 40px; }}
  h1 {{ font-size: 15px; letter-spacing: .12em; text-transform: uppercase;
       color: #E0705F; margin: 0 0 20px; }}
  pre {{ white-space: pre-wrap; color: #A6A9A0; }}
</style>
<h1>Render failed</h1>
<pre>{trace}</pre>
{reloader}
"""


def render() -> str:
    """The page as the Action would publish it, from a freshly imported module.

    Reloaded rather than imported once so an edit to the renderer takes effect
    without restarting the server — the whole point of the preview.
    """
    module = importlib.import_module("lpa.public_page")
    importlib.reload(module)
    return module.build_page(connect())


def render_or_report() -> tuple[str, bool]:
    """The page, or a readable traceback in its place.

    A syntax error mid-edit must not kill the server: the browser is the place
    the mistake is most useful, and a dead port means restarting by hand every
    time a bracket is left open.
    """
    try:
        return render(), True
    except Exception:  # noqa: BLE001 — the traceback is the product here
        return ERROR_PAGE.format(
            trace=traceback.format_exc(), reloader=RELOADER
        ), False


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        body, ok = render_or_report()
        if self.path == "/version":
            payload = hashlib.sha256(body.encode()).hexdigest().encode()
            self._send(payload, "text/plain")
            return
        if ok:
            body = body.replace("</body>", f"{RELOADER}</body>")
        self._send(body.encode(), "text/html; charset=utf-8")

    def _send(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        """Quiet. One line per poll, seven times a second, buries everything."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Public page preview on http://127.0.0.1:{args.port} — Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

"""Explicit local preview; never writes or substitutes production files."""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
PREVIEW = Path(__file__).resolve().parent
ORIGINAL = ROOT / "frontend" / "public"
PUBLIC = ROOT / "public"
PREVIEW_FILES = {"index.html", "observatory.css", "observatory.js"}


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        url_path = unquote(urlsplit(path).path)
        if url_path.startswith("/app/"):
            relative = url_path[5:] or "index.html"
            base = PREVIEW if relative in PREVIEW_FILES else ORIGINAL
        else:
            relative = url_path.lstrip("/")
            base = PUBLIC
        resolved = (base / relative).resolve()
        if not resolved.is_relative_to(base):
            return str(PREVIEW / "not-found")
        return str(resolved)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    print(f"Preview: http://127.0.0.1:{args.port}/app/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()

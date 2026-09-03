#!/usr/bin/env python3
"""Local dev server for public/ that DISABLES browser caching.

Plain `python3 -m http.server` sends no cache headers, so browsers heuristically cache
app.js / styles.css / i18n.js — and a normal reload (or a `?v=` query, which only busts
index.html) keeps serving STALE assets. That makes edits look like they "didn't take".
This server sends no-store on everything, so every reload gets fresh code. Dev only.
"""
import functools
import http.server
import os
import socket
import socketserver

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
PORT = int(os.environ.get("PORT", "4178"))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def rewrite_api_path(self):
        if self.path.split("?", 1)[0] == "/api/live/johor":
            self.path = "/data/live-johor.json"

    def do_GET(self):
        self.rewrite_api_path()
        super().do_GET()

    def do_HEAD(self):
        self.rewrite_api_path()
        super().do_HEAD()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # bind dual-stack (IPv6 + IPv4) so `localhost` — which macOS resolves to ::1 first —
    # always reaches THIS server, not some other dev server squatting [::1]:PORT.
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (AttributeError, OSError):
            pass
        super().server_bind()


if __name__ == "__main__":
    handler = functools.partial(NoCacheHandler, directory=ROOT)
    with Server(("", PORT), handler) as httpd:
        print(f"MyPolitik dev server (no-cache) -> http://localhost:{PORT}")
        httpd.serve_forever()

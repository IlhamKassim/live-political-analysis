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
import re
import socket
import socketserver

ROOT = os.environ.get("DEV_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
REPO_PUBLIC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public"))
PORT = int(os.environ.get("PORT", "4178"))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        clean_path = path.split("?", 1)[0].split("#", 1)[0]
        orig = super().translate_path(clean_path)
        if os.path.exists(orig):
            return orig
        words = [w for w in clean_path.split("/") if w]
        cand = REPO_PUBLIC
        for word in words:
            if word not in (os.curdir, os.pardir):
                cand = os.path.join(cand, word)
        if clean_path.endswith("/") and os.path.isdir(cand):
            idx = os.path.join(cand, "index.html")
            if os.path.isfile(idx):
                return idx
        if os.path.exists(cand):
            return cand
        return orig

    def rewrite_api_path(self):
        req_path = self.path.split("?", 1)[0]
        query = ("?" + self.path.split("?", 1)[1]) if "?" in self.path else ""
        if req_path.startswith("/app/"):
            req_path = req_path[4:]
            self.path = req_path + query

        m = re.match(r"^/api/live/([a-zA-Z0-9_-]+)$", req_path)
        if m:
            eid = m.group(1)
            candidates = [f"/data/live-{eid}.json"]
            if "-" in eid:
                suffix = eid.split("-", 1)[1]
                candidates.append(f"/data/live-{suffix}.json")
            if eid == "johor":
                candidates.append("/data/live-prn16-johor.json")
            for cand in candidates:
                disk_path = os.path.join(ROOT, cand.lstrip("/"))
                if os.path.isfile(disk_path):
                    self.path = cand + query
                    return
            self.path = "/data/live-johor.json" + query
            return

        # Prerendered page in REPO_PUBLIC: serve directly
        repo_cand = os.path.join(REPO_PUBLIC, req_path.lstrip("/"))
        if os.path.isdir(repo_cand) and os.path.isfile(os.path.join(repo_cand, "index.html")):
            return
        if os.path.isfile(repo_cand):
            return

        # SPA fallback for dev: if a route like /dewan/ or /bills/ has no disk file, serve index.html
        disk_path = os.path.join(ROOT, req_path.lstrip("/"))
        if disk_path.endswith("/") and os.path.isdir(disk_path) and os.path.isfile(os.path.join(disk_path, "index.html")):
            return
        if not os.path.exists(disk_path) and not req_path.startswith("/data/"):
            if any(req_path.strip("/").startswith(prefix) for prefix in ("dewan", "ms/dewan", "bills", "ms/bills", "politicians", "ms/politicians", "sentiment", "ms/sentiment", "projection", "ms/projection", "mp", "ms/mp")):
                self.path = "/index.html" + query

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
        print(f"PolitikKu dev server (no-cache) -> http://localhost:{PORT}")
        httpd.serve_forever()

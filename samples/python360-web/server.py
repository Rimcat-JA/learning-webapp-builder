#!/usr/bin/env python3
"""Python 360: localhost-only static server. Python 3.8+, no packages required."""
import argparse
import errno
import json
import mimetypes
import os
from pathlib import Path
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent / "public"
HEALTH = {"app": "python360-local", "version": "1.0.0"}
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quiet for routine assets; report HTTP errors.
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def reply(self, status, body, content_type="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        port = self.server.server_address[1]
        if self.headers.get("Host", "").lower() not in ("localhost:%d" % port, "127.0.0.1:%d" % port):
            return self.reply(403, b"Localhost access only.")
        try:
            request_path = unquote(urlsplit(self.path).path, errors="strict")
        except (ValueError, UnicodeError):
            return self.reply(400, b"Invalid path.")
        if request_path == "/__python360_health":
            return self.reply(200, json.dumps(HEALTH).encode(), "application/json")
        parts = request_path.split("/")
        if not request_path.startswith("/") or "\\" in request_path or "\x00" in request_path or any(x in (".", "..") or x.startswith(".") for x in parts if x):
            return self.reply(404, b"Not found.")
        file = (ROOT / (request_path.lstrip("/") or "index.html")).resolve()
        try:
            file.relative_to(ROOT.resolve())
        except ValueError:
            return self.reply(404, b"Not found.")
        if not file.is_file():
            return self.reply(404, b"Not found.")
        try:
            body = file.read_bytes()
        except OSError:
            return self.reply(404, b"Not found.")
        content_type = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/json":
            content_type += "; charset=utf-8"
        self.reply(200, body, content_type)

    do_HEAD = do_GET

    def do_POST(self):
        self.reply(405, b"Only GET and HEAD are supported.")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # On Windows, prevent two listeners from sharing a port.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description="Run Python 360 on this computer only.")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    if not (ROOT / "index.html").is_file() or not (ROOT / "data.json").is_file():
        parser.exit(1, "Missing public/ files. Extract the whole ZIP before starting.\n")
    url = "http://localhost:%d" % args.port
    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        if exc.errno not in (errno.EADDRINUSE, 10048):
            parser.exit(1, "Cannot start the local server: %s\n" % exc)
        try:
            # The localhost check must never go through a system proxy.
            with build_opener(ProxyHandler({})).open(url + "/__python360_health", timeout=2) as response:
                same_app = json.loads(response.read(1024)) == HEALTH
        except Exception:
            same_app = False
        if same_app:
            print("Python 360 is already running at " + url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
        parser.exit(1, "Port %d is used by another app. Close it or run: python server.py --port 4174\n" % args.port)
    print("Python 360 is ready: " + url, flush=True)
    print("Keep this window open. Press Ctrl+C to stop. No package installation is needed.", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPython 360 stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

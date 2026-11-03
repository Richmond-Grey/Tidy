"""Share files straight from this computer with a link. No UI imports.

A small HTTP server serves only files the user has explicitly shared, each under
an unguessable random token. Links work on the same network straight away; for
people elsewhere an optional tunnel (cloudflared if installed, otherwise
localhost.run over the ssh client built into Windows/macOS/Linux) gives a public
https address. Either way the file is only reachable while Tidy is running.
"""
import html
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

DEFAULT_PORT = 8765
_CHUNK = 256 * 1024


@dataclass
class Share:
    token: str
    path: str
    created: float
    expires: float | None = None      # unix time, None = never
    max_downloads: int | None = None  # None = unlimited
    downloads: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def is_live(self) -> bool:
        if self.expires is not None and time.time() > self.expires:
            return False
        if self.max_downloads is not None and self.downloads >= self.max_downloads:
            return False
        return os.path.isfile(self.path)

    def status(self) -> str:
        if not os.path.isfile(self.path):
            return "File missing"
        if self.expires is not None and time.time() > self.expires:
            return "Expired"
        if self.max_downloads is not None and self.downloads >= self.max_downloads:
            return "Used up"
        return "Live"


def lan_ip() -> str:
    """This computer's address on the local network (no traffic is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class ShareStore:
    """The list of shared files, saved to disk so links survive a restart."""

    def __init__(self, path: str | None = None):
        self.path = path
        self._lock = threading.Lock()
        self._shares: dict[str, Share] = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    for item in json.load(f):
                        share = Share(**item)
                        self._shares[share.token] = share
            except (OSError, ValueError, TypeError):
                pass

    def _save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([asdict(s) for s in self._shares.values()], f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def add(self, path: str, expires_in: float | None = None, max_downloads: int | None = None) -> Share:
        share = Share(token=secrets.token_urlsafe(16), path=os.path.abspath(path), created=time.time(),
                      expires=time.time() + expires_in if expires_in else None, max_downloads=max_downloads)
        with self._lock:
            self._shares[share.token] = share
            self._save()
        return share

    def remove(self, token: str):
        with self._lock:
            self._shares.pop(token, None)
            self._save()

    def get(self, token: str) -> Share | None:
        with self._lock:
            return self._shares.get(token)

    def all(self) -> list[Share]:
        with self._lock:
            return sorted(self._shares.values(), key=lambda s: -s.created)

    def count_download(self, token: str):
        with self._lock:
            if token in self._shares:
                self._shares[token].downloads += 1
                self._save()


class ShareServer:
    """Serves shared files. on_event(kind, share) fires on background threads with
    kind 'download_started' / 'download_finished'."""

    def __init__(self, store: ShareStore, on_event: Callable[[str, Share], None] | None = None,
                 port: int = DEFAULT_PORT, host: str = "0.0.0.0"):
        self.host = host  # 0.0.0.0 so other devices on the network can connect
        self.store = store
        self.on_event = on_event or (lambda kind, share: None)
        self.preferred_port = port
        self.port: int | None = None
        self._server: ThreadingHTTPServer | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> int:
        if self._server:
            return self.port
        handler = _make_handler(self)
        last_error = None
        for port in (self.preferred_port, *range(self.preferred_port + 1, self.preferred_port + 20), 0):
            try:
                self._server = ThreadingHTTPServer((self.host, port), handler)
                break
            except OSError as e:
                last_error = e
        if not self._server:
            raise OSError(f"Couldn't start the sharing server: {last_error}")
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def local_url(self, share: Share) -> str:
        return f"http://{lan_ip()}:{self.port}/s/{share.token}"


def _make_handler(server: ShareServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Tidy"
        sys_version = ""

        def log_message(self, *_args):  # keep the console quiet
            pass

        def do_HEAD(self):
            self._route(head=True)

        def do_GET(self):
            self._route(head=False)

        def _route(self, head):
            parts = urllib.parse.urlsplit(self.path).path.strip("/").split("/")
            if len(parts) == 2 and parts[0] in ("s", "d"):
                share = server.store.get(parts[1])
                if share and share.is_live():
                    if parts[0] == "s":
                        return self._page(share, head)
                    return self._file(share, head)
                return self._message(410 if share else 404, "This link isn't available",
                                     "It may have expired, been stopped, or the file was moved.", head)
            if parts == [""] or parts == ["favicon.ico"]:
                return self._message(404, "Tidy file sharing", "Open the full link you were sent.", head)
            return self._message(404, "Not found", "Check the link you were sent.", head)

        def _send_html(self, status, body, head):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def _message(self, status, title, text, head):
            self._send_html(status, _PAGE.format(title=html.escape(title), body=f"<p class=muted>{html.escape(text)}</p>"),
                            head)

        def _page(self, share, head):
            size = os.path.getsize(share.path)
            body = (f"<div class=icon>{html.escape(_ext_label(share.name))}</div>"
                    f"<h1>{html.escape(share.name)}</h1>"
                    f"<p class=muted>{_human(size)} · shared with Tidy</p>"
                    f"<a class=button href='/d/{share.token}'>Download</a>"
                    "<p class=small>The sender's computer needs to stay on until the download finishes.</p>")
            self._send_html(200, _PAGE.format(title=html.escape(share.name), body=body), head)

        def _file(self, share, head):
            size = os.path.getsize(share.path)
            start, end = 0, size - 1
            status = 200
            range_header = self.headers.get("Range", "")
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else size - 1
                else:  # suffix range: last N bytes
                    start = max(size - int(match.group(2)), 0)
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206
            ctype = mimetypes.guess_type(share.name)[0] or "application/octet-stream"
            quoted = urllib.parse.quote(share.name)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
            self.send_header("X-Content-Type-Options", "nosniff")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head:
                return
            fresh = start == 0
            if fresh:
                server.store.count_download(share.token)
                server.on_event("download_started", share)
            try:
                with open(share.path, "rb") as f:
                    f.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = f.read(min(_CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                if fresh or end == size - 1:
                    server.on_event("download_finished", share)
            except (ConnectionError, OSError):
                pass  # the other side cancelled or lost connection; they can resume

    return Handler


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _ext_label(name: str) -> str:
    ext = os.path.splitext(name)[1][1:].upper()
    return ext[:4] or "FILE"


_PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex>
<title>{title}</title><style>
:root{{--bg:#F6F5F1;--card:#fff;--text:#1B1A18;--muted:#77736B;--accent:#2F6F5E;--soft:#E5EFEB;--border:#E7E4DD}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121816;--card:#1A2420;--text:#EEF2F0;--muted:#98A6A0;--accent:#7FD1AE;--soft:#21312C;--border:#2A3E37}}}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);
color:var(--text);font:16px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif;padding:16px}}
main{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:40px 32px;max-width:440px;
width:100%;text-align:center}}h1{{font-size:20px;margin:16px 0 4px;word-break:break-word}}
.icon{{width:64px;height:76px;margin:0 auto;border-radius:10px;background:var(--soft);color:var(--accent);
display:grid;place-items:center;font-weight:700;letter-spacing:.04em}}.muted{{color:var(--muted);margin:0}}
.button{{display:inline-block;margin:28px 0 18px;background:var(--accent);color:var(--card);text-decoration:none;
font-weight:600;padding:12px 32px;border-radius:10px}}.small{{font-size:13px;color:var(--muted);margin:0}}
footer{{margin-top:28px;font-size:12px;color:var(--muted)}}</style></head>
<body><main>{body}<footer>Tidy</footer></main></body></html>"""


class Tunnel:
    """Public https address for the local server, so people outside your network can download.

    Uses cloudflared if it's installed, otherwise localhost.run through ssh. Both are
    free and need no account; the address changes every time the tunnel starts.
    """

    _URL = re.compile(r"https://[a-z0-9-]+\.(?:trycloudflare\.com|lhr\.life|localhost\.run)\b", re.I)

    def __init__(self, port: int, on_url: Callable[[str], None], on_closed: Callable[[str], None]):
        self.port = port
        self.on_url = on_url
        self.on_closed = on_closed
        self.url: str | None = None
        self._process: subprocess.Popen | None = None
        self._stopping = False

    @staticmethod
    def available() -> str | None:
        """Name of the tool that will be used, or None if neither is installed."""
        if shutil.which("cloudflared"):
            return "cloudflared"
        if shutil.which("ssh"):
            return "localhost.run"
        return None

    def start(self):
        tool = self.available()
        if tool == "cloudflared":
            command = [shutil.which("cloudflared"), "tunnel", "--no-autoupdate", "--url",
                       f"http://localhost:{self.port}"]
        elif tool == "localhost.run":
            command = [shutil.which("ssh"), "-o", "StrictHostKeyChecking=accept-new", "-o",
                       "ServerAliveInterval=30", "-o", "ExitOnForwardFailure=yes", "-o", "BatchMode=yes",
                       "-R", f"80:localhost:{self.port}", "nokey@localhost.run"]
        else:
            raise OSError("No tunnel tool found. Install cloudflared, or the OpenSSH client.")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                         errors="replace", creationflags=flags)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        process = self._process
        last_line = ""
        for line in process.stdout:
            if line.strip():
                last_line = line.strip()
            if not self.url and (match := self._URL.search(line)):
                if "admin.localhost.run" in match.group(0):
                    continue
                self.url = match.group(0).rstrip("/")
                self.on_url(self.url)
        process.wait()
        self.url = None
        if not self._stopping:
            self.on_closed(last_line or "The internet link closed.")

    def stop(self):
        self._stopping = True
        if self._process and self._process.poll() is None:
            self._process.terminate()
        self._process = None
        self.url = None

    def public_url(self, share: Share) -> str | None:
        return f"{self.url}/s/{share.token}" if self.url else None

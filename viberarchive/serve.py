"""Serve the static site on your network so a phone on the same Wi-Fi can open it.

    python archive.py serve --site site            then open the printed address on the phone

Why not open the files directly on the phone: Chrome on Android blocks a page opened from the Files app from loading
the files beside it, so the styles and the search would not work. A web server does not have that problem.
Only the site folder is served. Nothing leaves your network, and the server stops when you press Ctrl+C.
"""
import functools
import http.server
import socket
from pathlib import Path

TYPES = {".js": "text/javascript; charset=utf-8", ".html": "text/html; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        pass


def lan_addresses():
    """This computer's addresses on the local network (the ones a phone can reach)."""
    found = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))     # no packet is sent; it only picks the outgoing interface
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return [a for a in dict.fromkeys(found) if not a.startswith("127.")]


def make_server(site, port=8000, host="0.0.0.0"):
    """The HTTP server for the site folder (not started)."""
    folder = Path(site)
    if not (folder / "index.html").exists():
        raise FileNotFoundError(f"{folder} has no index.html; run the 'html' command first")
    handler = functools.partial(_Handler, directory=str(folder))
    return http.server.ThreadingHTTPServer((host, port), handler)


def serve(site, port=8000, local_only=False):
    """Run until Ctrl+C."""
    server = make_server(site, port, "127.0.0.1" if local_only else "0.0.0.0")
    port = server.server_address[1]
    print(f"Serving {Path(site).resolve()}")
    print(f"  on this computer:  http://localhost:{port}/")
    if not local_only:
        for address in lan_addresses():
            print(f"  on your phone:     http://{address}:{port}/   (same Wi-Fi)")
        print("Anyone on this network can open it while the server runs. Windows may ask to allow Python "
              "through the firewall: allow it for private networks only.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()

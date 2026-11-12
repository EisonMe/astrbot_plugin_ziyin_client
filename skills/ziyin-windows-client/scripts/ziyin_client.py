#!/usr/bin/env python3
"""Read-only ZiYin client API helper using Python's standard library."""
from __future__ import annotations
import os
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Never forward a Bearer key to a redirected endpoint."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def main() -> int:
    base = os.environ.get("ZIYIN_BASE_URL", "").rstrip("/")
    key = os.environ.get("ZIYIN_API_KEY", "")
    if not base or not key:
        print("Set ZIYIN_BASE_URL and ZIYIN_API_KEY in a secure environment.", file=sys.stderr)
        return 2
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == "https" and parsed.hostname and parsed.port
                 and "@" not in parsed.netloc and not parsed.path and not parsed.query
                 and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        print("Use an HTTPS URL with host and port, without credentials or path.", file=sys.stderr)
        return 2
    command = sys.argv[1] if len(sys.argv) > 1 else "health"
    routes = {"health": "/api/health", "settings": "/api/settings", "tasks": "/api/tasks"}
    if command == "task" and len(sys.argv) == 3:
        routes["task"] = "/api/tasks/" + quote(sys.argv[2], safe="")
    elif command == "files" and len(sys.argv) in (2, 3):
        routes["files"] = "/api/files" + ("?" + urlencode({"path": sys.argv[2]}) if len(sys.argv) == 3 else "")
    elif command not in routes or len(sys.argv) != 2:
        print("Usage: ziyin_client.py health|settings|tasks|task ID|files [relative-path]", file=sys.stderr)
        return 2
    context = ssl.create_default_context(cafile=os.environ.get("ZIYIN_CA_FILE") or None)
    opener = build_opener(HTTPSHandler(context=context), NoRedirect())
    request = Request(base + routes[command], headers={"Authorization": "Bearer " + key})
    try:
        with opener.open(request, timeout=30) as response:
            payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise ValueError("response exceeds 1 MiB")
            print(payload.decode("utf-8"))
            return 0
    except (HTTPError, URLError, OSError, UnicodeError, ValueError) as exc:
        print(f"Request failed ({exc.__class__.__name__}); check endpoint, network and trusted TLS.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

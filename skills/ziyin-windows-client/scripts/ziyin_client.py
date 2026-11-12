#!/usr/bin/env python3
"""Read-only ZiYin Windows client API helper. Requires requests."""
from __future__ import annotations
import os
import sys
import requests


def main() -> int:
    base = os.environ.get("ZIYIN_BASE_URL", "").rstrip("/")
    key = os.environ.get("ZIYIN_API_KEY", "")
    if not base or not key:
        print("Set ZIYIN_BASE_URL and ZIYIN_API_KEY in a secure environment.", file=sys.stderr)
        return 2
    if not base.startswith("https://"):
        print("HTTPS is required; configure a trusted CA instead of disabling TLS verification.", file=sys.stderr)
        return 2
    ca = os.environ.get("ZIYIN_CA_FILE") or True
    command = sys.argv[1] if len(sys.argv) > 1 else "health"
    routes = {
        "health": ("GET", "/api/health"),
        "settings": ("GET", "/api/settings"),
        "tasks": ("GET", "/api/tasks"),
    }
    if command == "task" and len(sys.argv) == 3:
        routes["task"] = ("GET", "/api/tasks/" + requests.utils.quote(sys.argv[2], safe=""))
    elif command == "files":
        routes["files"] = ("GET", "/api/files")
    elif command not in routes and command != "task":
        print("Usage: ziyin_client.py health|settings|tasks|task ID|files [relative-path]", file=sys.stderr)
        return 2
    if command not in routes:
        print("task requires an ID", file=sys.stderr)
        return 2
    params = {"path": sys.argv[2]} if command == "files" and len(sys.argv) > 2 else None
    method, path = routes[command]
    try:
        response = requests.request(
            method, base + path, params=params,
            headers={"Authorization": "Bearer " + key},
            timeout=(5, 30), verify=ca, allow_redirects=False,
        )
        response.raise_for_status()
        print(response.text)
        return 0
    except requests.RequestException as exc:
        print(f"Request failed ({exc.__class__.__name__}); check network, endpoint and trusted TLS.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

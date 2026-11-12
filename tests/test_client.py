"""针对不依赖 AstrBot 的纯逻辑做单元测试。

运行：python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ziyin_api import (  # noqa: E402
    ClientError,
    ZiYinClient,
    build_ssl_context,
    normalize_base_url,
    normalize_pin,
)

VALID_PIN = "ab" * 32


class BaseUrlTests(unittest.TestCase):
    def test_accepts_ip_and_port(self) -> None:
        self.assertEqual(
            normalize_base_url("https://192.168.1.100:17643"),
            "https://192.168.1.100:17643",
        )

    def test_strips_trailing_slash(self) -> None:
        self.assertEqual(
            normalize_base_url(" https://192.168.1.100:17643/ "),
            "https://192.168.1.100:17643",
        )

    def test_rejects_missing_scheme(self) -> None:
        with self.assertRaises(ValueError):
            normalize_base_url("192.168.1.100:17643")

    def test_rejects_path(self) -> None:
        with self.assertRaises(ValueError):
            normalize_base_url("https://host:17643/api")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            normalize_base_url("   ")


class PinTests(unittest.TestCase):
    def test_normalizes_colons_and_case(self) -> None:
        raw = ":".join(("AB" * 32)[i:i + 2] for i in range(0, 64, 2))
        self.assertEqual(normalize_pin(raw), VALID_PIN)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(normalize_pin(""), "")

    def test_rejects_short_value(self) -> None:
        with self.assertRaises(ValueError):
            normalize_pin("abcd")

    def test_rejects_non_hex(self) -> None:
        with self.assertRaises(ValueError):
            normalize_pin("zz" * 32)


class SslContextTests(unittest.TestCase):
    def test_http_without_pin_returns_none(self) -> None:
        self.assertIsNone(build_ssl_context("", "", "http"))

    def test_http_with_pin_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_ssl_context("", VALID_PIN, "http")

    def test_pin_keeps_system_ca_and_hostname_validation(self) -> None:
        import ssl

        ctx = build_ssl_context("", VALID_PIN, "https")
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_pin_requires_existing_ca_file(self) -> None:
        with self.assertRaises(ValueError):
            build_ssl_context("/nonexistent/ca.pem", VALID_PIN, "https")


class ClientConstructionTests(unittest.TestCase):
    def test_plain_http_requires_explicit_opt_in(self) -> None:
        with self.assertRaises(ValueError):
            ZiYinClient("http://127.0.0.1:17643", "x" * 32)
        client = ZiYinClient("http://127.0.0.1:17643", "x" * 32, allow_insecure_http=True)
        self.assertTrue(client.has_key)
        self.assertIsNone(client._ssl)

    def test_missing_key_is_reported(self) -> None:
        client = ZiYinClient("https://127.0.0.1:17643", "")
        self.assertFalse(client.has_key)

    def test_write_headers_include_csrf_and_bearer(self) -> None:
        client = ZiYinClient("https://127.0.0.1:17643", "k" * 32)
        headers = client._headers(True)
        self.assertEqual(headers["X-ZiYin-Request"], "1")
        self.assertEqual(headers["Authorization"], "Bearer " + "k" * 32)

    def test_read_headers_omit_csrf(self) -> None:
        client = ZiYinClient("https://127.0.0.1:17643", "k" * 32)
        self.assertNotIn("X-ZiYin-Request", client._headers(False))


class ErrorDescriptionTests(unittest.TestCase):
    def test_uses_server_error_field(self) -> None:
        text = ZiYinClient._describe(401, json.dumps({"error": "密钥无效"}))
        self.assertIn("API 密钥无效", text)
        self.assertIn("密钥无效", text)

    def test_falls_back_to_plain_body(self) -> None:
        text = ZiYinClient._describe(500, "boom")
        self.assertIn("HTTP 500", text)
        self.assertIn("boom", text)

    def test_unknown_status(self) -> None:
        self.assertIn("HTTP 418", ZiYinClient._describe(418, ""))


class ClipHelperTests(unittest.TestCase):
    def test_clip_imports_from_main_module_source(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("def clip(", source)

    def test_clip_behavior(self) -> None:
        namespace: dict[str, object] = {}
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        start = source.index("def clip(")
        end = source.index("@register")
        exec(compile(source[start:end], "clip_extract", "exec"), namespace)  # noqa: S102
        clip = namespace["clip"]
        self.assertEqual(clip("abcdef", 3), ("abc", True))
        self.assertEqual(clip("abc", 10), ("abc", False))
        self.assertEqual(clip("abc", 0), ("abc", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
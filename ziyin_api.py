"""认证的紫音客户端 LAN API 客户端。

只负责 HTTP 细节：Bearer 认证、CSRF 头、TLS 校验与可复用的连接会话。
不包含任何 AstrBot 依赖，便于单独测试。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import ssl
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp


class ClientError(Exception):
    """客户端调用失败，消息可直接展示给用户。"""


def normalize_base_url(raw: str) -> str:
    """校验并规范化客户端基址。

    Args:
        raw: 配置中的地址，例如 https://192.168.1.100:17643

    Returns:
        去掉尾部斜杠的基址。

    Raises:
        ValueError: 协议不是 http/https，或带路径、查询串。
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("未配置客户端地址。")
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise ValueError("客户端地址必须以 https:// 或 http:// 开头。")
    if not parts.hostname:
        raise ValueError("客户端地址缺少主机名或 IP。")
    if "@" in parts.netloc or not parts.port:
        raise ValueError("客户端地址必须带端口，且不能包含账号密码。")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("客户端地址不能带路径、查询串或片段。")
    return f"{parts.scheme}://{parts.netloc}"


def normalize_pin(raw: str) -> str:
    """把证书指纹整理成 64 位小写十六进制。

    Args:
        raw: 形如 AB:CD:... 或连续十六进制。

    Returns:
        小写十六进制指纹；空输入返回空串。

    Raises:
        ValueError: 长度不是 32 字节。
    """
    value = (raw or "").replace(":", "").replace(" ", "").strip().lower()
    if not value:
        return ""
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("证书指纹必须是 64 位十六进制（SHA256）。")
    return value


def build_ssl_context(ca_file: str, pin: str, scheme: str) -> ssl.SSLContext | None:
    """按配置构造 TLS 上下文。

    Args:
        ca_file: 服务端证书 PEM 路径，空则用系统信任库。
        pin: 证书 SHA256 指纹，空则不固定。
        scheme: http 或 https。

    Returns:
        需要 TLS 时返回 SSLContext，明文 HTTP 返回 None。

    Raises:
        ValueError: 配置组合不合法。
    """
    if scheme != "https":
        if pin:
            raise ValueError("明文 HTTP 下无法校验证书指纹。")
        return None
    if ca_file and not os.path.isfile(ca_file):
        raise ValueError(f"证书文件不存在：{ca_file}")
    # 使用系统/指定 CA 完成链验证，指纹仅作为额外约束，不能替代 TLS 身份验证。
    return ssl.create_default_context(cafile=ca_file or None)


class ZiYinClient:
    """一个可复用的、带认证的客户端会话。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        ca_file: str = "",
        pin_sha256: str = "",
        allow_insecure_http: bool = False,
        timeout: float = 30.0,
    ) -> None:
        """保存连接参数，实际连接在 :meth:`start` 中建立。

        Args:
            base_url: 已规范化的基址。
            api_key: API 密钥。
            ca_file: 服务端证书 PEM。
            pin_sha256: 证书指纹。
            allow_insecure_http: 是否允许明文 HTTP。
            timeout: 单次请求总超时秒数。
        """
        self.base_url = base_url
        self._api_key = (api_key or "").strip()
        self._pin = normalize_pin(pin_sha256)
        self._timeout = timeout
        parts = urlsplit(base_url)
        self._scheme = parts.scheme
        if self._scheme == "http" and not allow_insecure_http:
            raise ValueError("当前地址是明文 HTTP，需显式开启「允许明文 HTTP」。")
        self._ssl = build_ssl_context(ca_file, self._pin, self._scheme)
        self._session: aiohttp.ClientSession | None = None

    @property
    def has_key(self) -> bool:
        """是否已配置 API 密钥。"""
        return bool(self._api_key)

    def _headers(self, write: bool) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        # 服务端对所有非 GET/HEAD 都要求该 CSRF 头，命令行客户端同样适用。
        if write:
            headers["X-ZiYin-Request"] = "1"
        return headers

    async def start(self) -> None:
        """建立底层会话。"""
        if self._session is not None and not self._session.closed:
            return
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._timeout),
            connector=aiohttp.TCPConnector(ssl=self._ssl, limit=8),
        )

    async def close(self) -> None:
        """释放底层会话。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        raw_body: bytes | None = None,
        content_type: str | None = None,
        expect_bytes: bool = False,
        allow_redirect: bool = False,
    ) -> Any:
        """发送一次认证请求。

        Args:
            method: HTTP 方法。
            path: 以 /api 开头的路径。
            params: 查询参数。
            json_body: JSON 请求体。
            raw_body: 原始请求体，与 json_body 二选一。
            content_type: 原始请求体的类型。
            expect_bytes: 返回二进制而非 JSON。
            allow_redirect: 是否接受 3xx。

        Returns:
            解析后的 JSON，或二进制内容，204 返回 None。

        Raises:
            ClientError: 网络、TLS、认证或业务错误。
        """
        await self.start()
        assert self._session is not None
        write = method not in ("GET", "HEAD")
        headers = self._headers(write)
        if json_body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        elif content_type:
            headers["Content-Type"] = content_type
        url = self.base_url + path
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json_body,
                data=raw_body,
                headers=headers,
                allow_redirects=allow_redirect,
            ) as response:
                await self._verify_pin(response)
                if 300 <= response.status < 400:
                    raise ClientError("服务端返回重定向；请检查客户端地址。")
                if expect_bytes and response.status < 400:
                    return await response.read()
                body = await response.text(errors="replace")
                if response.status == 204:
                    return None
                if response.status >= 400:
                    raise ClientError(self._describe(response.status, body))
                if not body.strip():
                    return None
                try:
                    return json.loads(body)
                except json.JSONDecodeError as exc:
                    raise ClientError(f"返回内容不是 JSON（HTTP {response.status}）。") from exc
        except aiohttp.ClientSSLError as exc:
            raise ClientError(f"TLS 校验失败：{exc.__class__.__name__}。请核对证书、指纹或主机名。") from exc
        except aiohttp.ClientConnectorError as exc:
            raise ClientError(f"无法连接 {self.base_url}：网络不通、未开放 LAN、防火墙或端口错误。") from exc
        except asyncio.TimeoutError as exc:
            raise ClientError(f"请求超时（{self._timeout:g} 秒）。") from exc
        except aiohttp.ClientError as exc:
            raise ClientError(f"请求失败：{exc.__class__.__name__}。") from exc

    async def _verify_pin(self, response: aiohttp.ClientResponse) -> None:
        """握手后比对证书指纹。

        Args:
            response: 已建立的响应。

        Raises:
            ClientError: 指纹不一致。
        """
        if not self._pin or self._scheme != "https":
            return
        transport = response.connection and response.connection.transport
        if transport is None:
            raise ClientError("无法读取 TLS 连接信息，拒绝继续。")
        ssl_object = transport.get_extra_info("ssl_object")
        if ssl_object is None:
            raise ClientError("连接不是 TLS，指纹校验失败。")
        der = ssl_object.getpeercert(binary_form=True)
        digest = hashlib.sha256(der).hexdigest()
        if digest != self._pin:
            raise ClientError("证书指纹不匹配，连接已拒绝。")

    @staticmethod
    def _describe(status: int, body: str) -> str:
        """把错误响应转成中文提示。

        Args:
            status: HTTP 状态码。
            body: 响应正文。

        Returns:
            单行错误信息。
        """
        detail = ""
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                detail = str(parsed.get("error") or parsed.get("message") or "")
        except json.JSONDecodeError:
            detail = body.strip().replace("\n", " ")[:200]
        table = {
            400: "请求参数被拒绝",
            401: "API 密钥无效或会话过期",
            403: "来源校验失败（缺 CSRF 头或被判定为跨站）",
            404: "目标不存在",
            409: "资源忙或文件被占用",
            429: "请求过多或队列已满",
        }
        base = table.get(status, f"HTTP {status}")
        return f"{base}：{detail}" if detail else base

    async def health(self) -> dict[str, Any]:
        """读取服务健康状态。"""
        return await self.request("GET", "/api/health")

    async def settings(self) -> dict[str, Any]:
        """读取连接信息（不含密钥）。"""
        return await self.request("GET", "/api/settings")

    async def submit_task(self, command: str, timeout_seconds: int, working_directory: str | None) -> dict[str, Any]:
        """提交后台 PowerShell 任务。"""
        body = {"command": command, "timeoutSeconds": timeout_seconds}
        if working_directory:
            body["workingDirectory"] = working_directory
        return await self.request("POST", "/api/tasks", json_body=body)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """按 ID 读取任务快照。"""
        return await self.request("GET", f"/api/tasks/{quote(task_id, safe='')}")

    async def list_tasks(self) -> list[dict[str, Any]]:
        """读取最近任务列表。"""
        data = await self.request("GET", "/api/tasks")
        return data if isinstance(data, list) else []

    async def cancel_task(self, task_id: str) -> Any:
        """请求取消任务。"""
        return await self.request("POST", f"/api/tasks/{quote(task_id, safe='')}/cancel")

    async def list_files(self, path: str | None) -> Any:
        """列出目录。"""
        params = {"path": path} if path else None
        return await self.request("GET", "/api/files", params=params)

    async def download_file(self, path: str, max_bytes: int) -> bytes:
        """下载文件，超过上限即拒绝。"""
        data = await self.request(
            "GET", "/api/files/content", params={"path": path}, expect_bytes=True
        )
        if len(data) > max_bytes:
            raise ClientError(f"文件超过 {max_bytes // 1024 // 1024} MiB 上限。")
        return data

    async def upload_file(self, path: str, content: bytes) -> Any:
        """上传（覆盖）文件。"""
        return await self.request(
            "PUT",
            "/api/files/content",
            params={"path": path},
            raw_body=content,
            content_type="application/octet-stream",
        )

    async def delete_file(self, path: str) -> Any:
        """删除文件根目录中的单个文件。"""
        return await self.request("DELETE", "/api/files", params={"path": path})

    async def screenshot(self) -> bytes:
        """抓取本机普通桌面截图。"""
        return await self.request("POST", "/api/desktop/screenshot", expect_bytes=True)

    async def desktop_status(self) -> dict[str, Any]:
        """查询托盘桌面授权状态。"""
        return await self.request("GET", "/api/desktop/status")

    async def desktop_input(self, action: str, x: int = 0, y: int = 0, text: str = "", key: str = "") -> dict[str, Any]:
        """发送鼠标、键盘或文字输入。"""
        body: dict[str, Any] = {"action": action, "x": x, "y": y}
        if text:
            body["text"] = text
        if key:
            body["key"] = key
        return await self.request("POST", "/api/desktop/input", json_body=body)

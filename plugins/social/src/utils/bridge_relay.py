"""Polaris Browser Bridge 本地中继服务与 ExtensionBackend。

为何需要该模块：
1. Chrome 136+ 禁用了默认用户目录的 --remote-debugging-port 命令行参数；
2. 通过 Chrome 扩展（基于 chrome.debugger）附着自建标签页，安装一次后无需用户重复点选弹窗；
3. 本地中继（BridgeRelay）将 Playwright 标准 CDP 协议指令双向转换为扩展能理解的轻量 RPC 协议，
   对外伪装为标准 Chrome CDP 浏览器端点（提供 /json/version 与 WebSocket）。
"""

from __future__ import annotations

import asyncio
import hmac
import http
import json
import logging
import os
import re
import secrets
import time
import uuid
from typing import Any

from patchright.async_api import Browser, Playwright
from patchright.async_api import Error as PwError
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from .bridge_const import BRIDGE_PORT_END, BRIDGE_PORT_START, EXTENSION_ID
from .browser_hub import HubError
from .cfg import CFG, ENV_BACKEND

logger = logging.getLogger("polaris.bridge_relay")


def get_or_create_token() -> str:
    """获取或生成安全的 32 字节随机 Hex 配对令牌（文件权限 0600）。"""
    token_file = CFG / "bridge_token"
    if token_file.exists():
        try:
            t = token_file.read_text(encoding="utf-8").strip()
            if t:
                return t
        except OSError:
            pass

    token = secrets.token_hex(32)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        # 原子创建并以 0600 写入，避免先写后 chmod 的可读窗口
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # 并发创建：另一方已写入，重新读取
        for _ in range(20):
            try:
                t = token_file.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except OSError:
                pass
            time.sleep(0.05)
        return token
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token


class BridgeRelay:
    """双口中继服务端：扩展 WebSocket 口 + Playwright CDP 口。"""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or get_or_create_token()
        self.ext_port: int = 0
        self.cdp_port: int = 0
        self.cdp_path = f"/devtools/browser/{uuid.uuid4()}"

        self.ext_server: Server | None = None
        self.cdp_server: Server | None = None

        self.ext_conn: ServerConnection | None = None
        self.ext_ua: str = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        self.ext_version: str = "1.0.0"

        self.pw_conn: ServerConnection | None = None
        self.current_tab_id: int | None = None
        self.cached_target_info: dict[str, Any] | None = None

        self._pending_ext_reqs: dict[int, asyncio.Future[Any]] = {}
        self._next_id: int = 1
        self._ext_connected_event = asyncio.Event()
        self._heartbeat_task: asyncio.Task[None] | None = None

    def has_extension(self) -> bool:
        """检查扩展 WebSocket 是否已成功握手在线。"""
        return self.ext_conn is not None

    async def wait_for_extension(self, timeout: float = 2.0) -> bool:
        """等待扩展完成连接握手。"""
        if self.has_extension():
            return True
        try:
            await asyncio.wait_for(self._ext_connected_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def _next_ext_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    async def _send_to_extension(
        self, method: str, params: dict[str, Any], timeout_s: float = 20.0
    ) -> Any:
        """向扩展发送 RPC 命令并等待应答。"""
        if not self.ext_conn:
            raise HubError("attach_failed", "扩展连接未就绪或已断开")

        msg_id = self._next_ext_id()
        fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending_ext_reqs[msg_id] = fut

        try:
            await self.ext_conn.send(
                json.dumps({"id": msg_id, "method": method, "params": params})
            )
            return await asyncio.wait_for(fut, timeout=timeout_s)
        except TimeoutError:
            raise HubError(
                "timeout", f"等待扩展响应命令 {method} 超时 ({timeout_s}s)"
            ) from None
        finally:
            self._pending_ext_reqs.pop(msg_id, None)

    async def _authenticate_ext(self, ws: ServerConnection) -> bool:
        """执行扩展 WebSocket 握手认证。"""
        try:
            raw_msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            hello = json.loads(raw_msg)
            if hello.get("type") != "hello":
                await ws.close(4401, "Expected hello")
                return False

            client_token = str(hello.get("token") or "")
            if not hmac.compare_digest(client_token, self.token):
                logger.warning("扩展连接握手令牌错误，关闭连接")
                await ws.close(4401, "Invalid token")
                return False

            self.ext_ua = str(hello.get("ua") or self.ext_ua)
            self.ext_version = str(hello.get("ext_version") or "1.0.0")

            if self.ext_conn and self.ext_conn is not ws:
                try:
                    await self.ext_conn.close(1000, "Replaced by new connection")
                except (OSError, RuntimeError) as e:
                    logger.debug("关闭旧扩展连接异常: %s", e)

            self.ext_conn = ws
            self._ext_connected_event.set()
            await ws.send(json.dumps({"type": "hello_ok", "client": "browser_use"}))
            logger.info("Polaris Browser Bridge 扩展握手成功 (port=%d)", self.ext_port)
            return True
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
        ) as e:
            logger.debug("扩展握手失败: %s", e)
            await ws.close(4401, "Handshake failed")
            return False

    async def _handle_ext_cdp_event(self, msg: dict[str, Any]) -> None:
        """处理扩展上报的 CDP 事件。"""
        if not self.pw_conn:
            return
        session_id = msg.get("sessionId") or "pw-tab-1"
        pw_event = {
            "method": msg.get("method"),
            "params": msg.get("params", {}),
            "sessionId": session_id,
        }
        await self.pw_conn.send(json.dumps(pw_event))

    async def _handle_ext_detached(self) -> None:
        """处理扩展标签页分离事件。"""
        if self.pw_conn:
            await self.pw_conn.send(
                json.dumps(
                    {
                        "method": "Target.detachedFromTarget",
                        "params": {"sessionId": "pw-tab-1"},
                    }
                )
            )
        self.current_tab_id = None
        self.cached_target_info = None

    def _handle_ext_rpc_response(self, msg: dict[str, Any]) -> None:
        """处理扩展对内部 RPC 的应答。"""
        msg_id = msg.get("id")
        if msg_id not in self._pending_ext_reqs:
            return
        fut = self._pending_ext_reqs[msg_id]
        if fut.done():
            return
        if "error" in msg:
            err_msg = msg["error"].get("message", "Extension error")
            fut.set_exception(HubError("attach_failed", err_msg))
        else:
            fut.set_result(msg.get("result"))

    async def _process_ext_message(self, msg: dict[str, Any]) -> None:
        """扩展消息分发路由器。"""
        mtype = msg.get("type")
        if mtype == "pong":
            return
        if mtype == "cdp_event":
            await self._handle_ext_cdp_event(msg)
            return
        if mtype == "detached":
            await self._handle_ext_detached()
            return
        self._handle_ext_rpc_response(msg)

    def _cleanup_ext_conn(self, ws: ServerConnection) -> None:
        """扩展断开后的清理工作。"""
        if self.ext_conn is ws:
            self.ext_conn = None
            self._ext_connected_event.clear()
            self.current_tab_id = None
            self.cached_target_info = None

    async def _handle_ext_ws(self, ws: ServerConnection) -> None:
        """处理扩展的 WebSocket 连接。"""
        if not await self._authenticate_ext(ws):
            return

        # 启动保活心跳
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._ext_heartbeat())

        # 接收扩展消息循环
        try:
            async for raw in ws:
                await self._process_ext_message(json.loads(raw))
        except (
            ConnectionClosed,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            logger.debug("扩展连接循环断开: %s", e)
        finally:
            self._cleanup_ext_conn(ws)

    async def _ext_heartbeat(self) -> None:
        """扩展心跳保活循环（每 20s 发送 ping）。"""
        while True:
            await asyncio.sleep(20)
            if self.ext_conn:
                try:
                    await self.ext_conn.send(json.dumps({"type": "ping"}))
                except (ConnectionClosed, OSError, RuntimeError):
                    self.ext_conn = None
                    self._ext_connected_event.clear()
                    break
            else:
                break

    def _process_ext_request(self, conn: ServerConnection, req: Any) -> Any | None:
        """检查扩展 WebSocket 连接的 Origin 是否符合固定扩展 ID。"""
        path = getattr(req, "path", "")
        if path.split("?")[0] != "/bridge":
            r = conn.respond(http.HTTPStatus.NOT_FOUND, "Not Found")
            return r
        origin = req.headers.get("Origin") or ""
        expected = f"chrome-extension://{EXTENSION_ID}"
        if origin != expected:
            logger.warning("拒绝非法扩展 Origin: %s (预期: %s)", origin, expected)
            r = conn.respond(http.HTTPStatus.FORBIDDEN, "Forbidden Origin")
            return r
        return None

    def _process_cdp_request(self, conn: ServerConnection, req: Any) -> Any | None:
        """处理 Playwright 发起的 HTTP /json/version 版本探测请求。"""
        if req.path == "/json/version":
            # 提取 Chrome 版本号
            ver_match = re.search(r"Chrome/([\d.]+)", self.ext_ua)
            ver = ver_match.group(1) if ver_match else "130.0.0.0"
            data = {
                "Browser": f"Chrome/{ver}",
                "Protocol-Version": "1.3",
                "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.cdp_port}{self.cdp_path}",
            }
            body = json.dumps(data)
            r = conn.respond(http.HTTPStatus.OK, body)
            r.headers["Content-Type"] = "application/json"
            r.headers["Connection"] = "close"
            return r
        return None

    async def _handle_pw_ws(self, ws: ServerConnection) -> None:
        """处理来自 Playwright 的 CDP 指令流并与扩展交互桥接。"""
        self.pw_conn = ws
        try:
            async for raw in ws:
                cmd = json.loads(raw)
                await self._handle_pw_cmd(cmd)
        except (
            ConnectionClosed,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as e:
            logger.debug("Playwright CDP 连接断开: %s", e)
        finally:
            if self.pw_conn is ws:
                self.pw_conn = None

    async def _handle_pw_cmd(self, cmd: dict[str, Any]) -> None:
        """CDP 命令路由器。"""
        msg_id = cmd["id"]
        method = cmd.get("method", "")
        params = cmd.get("params", {})
        session_id = cmd.get("sessionId")

        # 1. 浏览器级命令（无 sessionId）
        if not session_id:
            if method == "Browser.getVersion":
                ver_match = re.search(r"Chrome/([\d.]+)", self.ext_ua)
                ver = ver_match.group(1) if ver_match else "130.0.0.0"
                res = {
                    "protocolVersion": "1.3",
                    "product": f"Chrome/{ver}",
                    "userAgent": self.ext_ua,
                    "jsVersion": "",
                }
                await self._reply_pw(msg_id, res)
                return

            if method == "Browser.setDownloadBehavior":
                await self._reply_pw(msg_id, {})
                return

            if method == "Target.setAutoAttach":
                if self.current_tab_id is None:
                    tab_res = await self._send_to_extension(
                        "createTab", {"url": "about:blank"}
                    )
                    self.current_tab_id = tab_res["tabId"]
                    self.cached_target_info = tab_res["targetInfo"]

                # 向 Playwright 下发 attachedToTarget 事件
                if self.pw_conn:
                    await self.pw_conn.send(
                        json.dumps(
                            {
                                "method": "Target.attachedToTarget",
                                "params": {
                                    "sessionId": "pw-tab-1",
                                    "targetInfo": self.cached_target_info,
                                    "waitingForDebugger": False,
                                },
                            }
                        )
                    )
                await self._reply_pw(msg_id, {})
                return

            if method == "Target.getTargetInfo":
                await self._reply_pw(
                    msg_id, {"targetInfo": self.cached_target_info or {}}
                )
                return

            if method == "Target.getBrowserContexts":
                await self._reply_pw(msg_id, {"browserContextIds": []})
                return

            if method == "Target.createTarget":
                # 单标签限制，返回错误告知
                await self._reply_pw_error(msg_id, "extension backend: single tab")
                return

            # 其他浏览器级命令转发给当前标签
            try:
                res = await self._send_to_extension(
                    "cdp",
                    {"tabId": self.current_tab_id, "method": method, "params": params},
                )
                await self._reply_pw(msg_id, res)
            except (HubError, OSError, RuntimeError, PwError) as e:
                await self._reply_pw_error(msg_id, str(e))
            return

        # 2. 标签级命令（sessionId == 'pw-tab-1'）
        if session_id == "pw-tab-1":
            try:
                res = await self._send_to_extension(
                    "cdp",
                    {"tabId": self.current_tab_id, "method": method, "params": params},
                )
                await self._reply_pw(msg_id, res, session_id="pw-tab-1")
            except (HubError, OSError, RuntimeError, PwError) as e:
                await self._reply_pw_error(msg_id, str(e), session_id="pw-tab-1")
            return

        # 3. 子目标命令（如 iframe / worker）
        try:
            res = await self._send_to_extension(
                "cdp",
                {
                    "tabId": self.current_tab_id,
                    "method": method,
                    "params": params,
                    "sessionId": session_id,
                },
            )
            await self._reply_pw(msg_id, res, session_id=session_id)
        except (HubError, OSError, RuntimeError, PwError) as e:
            await self._reply_pw_error(msg_id, str(e), session_id=session_id)

    async def _reply_pw(
        self, msg_id: int, result: Any, session_id: str | None = None
    ) -> None:
        if not self.pw_conn:
            return
        msg: dict[str, Any] = {"id": msg_id, "result": result}
        if session_id:
            msg["sessionId"] = session_id
        await self.pw_conn.send(json.dumps(msg))

    async def _reply_pw_error(
        self, msg_id: int, error_msg: str, session_id: str | None = None
    ) -> None:
        if not self.pw_conn:
            return
        msg: dict[str, Any] = {"id": msg_id, "error": {"message": error_msg}}
        if session_id:
            msg["sessionId"] = session_id
        await self.pw_conn.send(json.dumps(msg))

    async def start(self) -> None:
        """寻找可用端口并启动中继服务端。"""
        # 1. 绑定扩展端口 (18790-18799)
        bound = False
        for p in range(BRIDGE_PORT_START, BRIDGE_PORT_END + 1):
            try:
                server = await serve(
                    self._handle_ext_ws,
                    "127.0.0.1",
                    p,
                    process_request=self._process_ext_request,
                )
                self.ext_server = server
                self.ext_port = p
                bound = True
                logger.info("已绑定扩展桥接端口 127.0.0.1:%d", p)
                break
            except OSError:
                continue

        if not bound:
            raise HubError(
                "attach_failed",
                "未能绑定 18790-18799 中任一空闲端口，请检查是否有过多中继正在运行",
            )

        # 2. 绑定 CDP 随机端口
        self.cdp_server = await serve(
            self._handle_pw_ws,
            "127.0.0.1",
            0,
            process_request=self._process_cdp_request,
        )
        sockets = self.cdp_server.server.sockets
        if sockets:
            self.cdp_port = sockets[0].getsockname()[1]
        logger.info(
            "已绑定 CDP 中继端点 http://127.0.0.1:%d%s", self.cdp_port, self.cdp_path
        )

    async def close(self) -> None:
        """关闭中继服务端与连接。"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self.ext_server:
            self.ext_server.close()
            await self.ext_server.wait_closed()
        if self.cdp_server:
            self.cdp_server.close()
            await self.cdp_server.wait_closed()


_RELAY: BridgeRelay | None = None
_RELAY_LOCK = asyncio.Lock()


async def get_or_start_relay() -> BridgeRelay:
    """获取或启动进程级唯一的 BridgeRelay 单例。"""
    global _RELAY
    if _RELAY is None:
        async with _RELAY_LOCK:
            if _RELAY is None:
                r = BridgeRelay()
                await r.start()
                _RELAY = r
    return _RELAY


class ExtensionBackend:
    """Polaris Browser Bridge 扩展后端。

    优势：无需用户每次点选允许，支持全自动无人值守。
    限制：遵循单标签页模型，所有操作在独立窗口内的专属标签中串行完成。
    """

    name = "extension"
    fingerprint_risk = "low"

    def __init__(self) -> None:
        self.relay: BridgeRelay | None = None
        self.browser: Browser | None = None
        self._on_disconnected_cb: Any = None

    def set_disconnect_callback(self, cb: Any) -> None:
        self._on_disconnected_cb = cb

    def is_ready(self) -> bool:
        """扩展是否已在线握手。"""
        return self.relay is not None and self.relay.has_extension()

    def unattended_ok(self) -> bool:
        """扩展在线时允许无人值守发起调用。"""
        return True

    async def connect(self, pw: Playwright) -> Browser:
        """通过中继的 CDP 端点连接扩展驱动的浏览器。"""
        if self.relay is None:
            self.relay = await get_or_start_relay()

        explicit = os.environ.get(ENV_BACKEND, "auto").strip().lower() == "extension"
        wait_s = 30.0 if explicit else 2.0

        ready = await self.relay.wait_for_extension(timeout=wait_s)
        if not ready:
            token = self.relay.token
            token_path = CFG / "bridge_token"
            raise HubError(
                "attach_failed",
                f"未检测到 Polaris Browser Bridge 扩展连接。请在 Chrome 中加载扩展并在选项页粘贴配对令牌:\n{token}\n(令牌已保存于 {token_path})",
            )

        endpoint_url = f"http://127.0.0.1:{self.relay.cdp_port}"
        try:
            browser: Any = await pw.chromium.connect_over_cdp(
                endpoint_url, timeout=30000
            )
            self.browser = browser
            self._bind_disconnect(browser)
            return browser
        except (PwError, OSError, RuntimeError, TimeoutError) as e:
            logger.warning("驱动连接扩展中继失败 (%s)，尝试以备用配置重连", e)
            from playwright.async_api import async_playwright as pw_fallback

            pw_alt = await pw_fallback().start()
            browser = await pw_alt.chromium.connect_over_cdp(
                endpoint_url, timeout=30000
            )
            self.browser = browser
            self._bind_disconnect(browser)
            return browser

    def _bind_disconnect(self, browser: Browser) -> None:
        def on_disconnected(_browser: Any = None) -> None:
            self.browser = None
            if self._on_disconnected_cb:
                self._on_disconnected_cb()

        browser.on("disconnected", on_disconnected)

    async def close(self) -> None:
        """断开连接。"""
        if self.browser:
            await self.browser.close()
            self.browser = None

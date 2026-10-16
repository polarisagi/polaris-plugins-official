"""BrowserHub 单例与多后端（CDP 开关、系统 Chrome 托管、浏览器扩展桥接）管理。

为何需要该模块：
1. Chrome 136+ 禁用了默认配置目录的 --remote-debugging-port 命令行参数；
   本模块通过 Chrome 155 的 chrome://inspect 远程调试开关或专用配置目录实现非侵入连接。
2. 整个插件进程只建立一次底层 Playwright / Patchright 连接，所有工具共享 Hub。
3. 隔离保证：所有自动化操作必须在 Polaris 自建窗口内运行，严禁触碰用户的已有标签页。
"""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import platform
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from patchright.async_api import Browser, Page, Playwright
from patchright.async_api import Error as PwError
from playwright.async_api import Error as PlaywrightError

# 两套驱动的异常类互不继承：cdp/extension 默认 playwright、managed 默认 patchright，需同时捕获。
# except 中请写 (PwError, PlaywrightError, ...)；mypy 不支持在 except 元组里解包 PwError, PlaywrightError
PW_ERRORS: tuple[type[BaseException], ...] = (PwError, PlaywrightError)

from .cfg import (
    CFG,
    ENV_BACKEND,
    ENV_DRIVER,
    ENV_HEADLESS,
    ENV_IDLE_RELEASE_MIN,
    ENV_PROFILE,
)

logger = logging.getLogger("polaris.browser_hub")


class HubError(Exception):
    """BrowserHub 与工具执行的标准统一异常。"""

    def __init__(
        self, code: str, message: str, extra: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}

    def to_dict(self) -> dict[str, Any]:
        """序列化为标准 JSON 错误响应。"""
        res: dict[str, Any] = {"code": self.code, "message": self.message}
        res.update(self.extra)
        return res


class Backend(Protocol):
    """浏览器底层后端协议。"""

    name: str

    async def connect(self, pw: Playwright) -> Browser:
        """建立连接并返回 Browser 实例。"""
        ...

    def unattended_ok(self) -> bool:
        """无人值守定时任务是否允许自动发起新连接。"""
        ...

    async def close(self) -> None:
        """关闭或断开与浏览器的底层连接。"""
        ...


def devtools_port_candidates() -> list[Path]:
    """日常 Chrome / Edge 的 DevToolsActivePort 候选路径（按优先级）。"""
    home = Path.home()
    sys_name = platform.system()
    if sys_name == "Darwin":
        return [
            home / "Library/Application Support/Google/Chrome/DevToolsActivePort",
            home / "Library/Application Support/Microsoft Edge/DevToolsActivePort",
        ]
    if sys_name == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (home / "AppData" / "Local")
        return [
            base / "Google/Chrome/User Data/DevToolsActivePort",
            base / "Microsoft/Edge/User Data/DevToolsActivePort",
        ]
    # Linux
    return [
        home / ".config/google-chrome/DevToolsActivePort",
        home / ".config/microsoft-edge/DevToolsActivePort",
    ]


def find_devtools_port_file() -> Path | None:
    """查找日常 Chrome 或 Edge 的 DevToolsActivePort 文件路径。"""
    for p in devtools_port_candidates():
        if p.exists():
            return p
    return None


def read_devtools_ws_url(path: Path) -> str | None:
    """安全读取 DevToolsActivePort 提取 WebSocket 调试地址。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return None
        port = int(lines[0].strip())
        browser_path = lines[1].strip() if len(lines) > 1 else ""
        if browser_path.startswith("/devtools/"):
            return f"ws://127.0.0.1:{port}{browser_path}"
        return f"http://127.0.0.1:{port}"
    except (OSError, ValueError) as err:
        logger.debug("读取调试端口文件 %s 失败: %s", path, err)
        return None


def env_cdp_url() -> str | None:
    """显式指定的 CDP 端点（环境变量 POLARIS_BROWSER_CDP_URL），未设置返回 None。"""
    return os.environ.get("POLARIS_BROWSER_CDP_URL", "").strip() or None


PORT_FILE_UNREADABLE_MSG = (
    "无权读取 Chrome 数据目录中的 DevToolsActivePort（macOS 隐私保护拦截了跨 App 数据访问："
    "可在「系统设置 > 隐私与安全性 > 完全磁盘访问权限」中授权启动本进程的 App，如终端 / Claude / Polaris），"
    "或改用 Polaris Browser Bridge 扩展（无需读取该文件），或设置 POLARIS_BROWSER_CDP_URL"
)
PORT_FILE_MISSING_MSG = (
    "未找到 DevToolsActivePort：日常 Chrome 未运行，或未在 chrome://inspect/#remote-debugging "
    "打开远程调试开关（打开后 Chrome 才会写出该文件）。也可改用 Polaris Browser Bridge 扩展，"
    "或设置 POLARIS_BROWSER_CDP_URL"
)
PORT_FILE_MALFORMED_MSG = (
    "DevToolsActivePort 内容无效（Chrome 可能正在启动或已异常退出），请重启 Chrome 后重试，"
    "或改用 Polaris Browser Bridge 扩展 / 设置 POLARIS_BROWSER_CDP_URL"
)


def diagnose_devtools_port() -> str:
    """区分「文件不存在 / 无权限 / 内容无效」，返回可操作的错误提示。

    为何需要：Path.exists() 在无权限时同样返回 False，单一提示会把
    「未开远程调试」误报成「权限问题」，误导排查方向。
    """
    for p in devtools_port_candidates():
        try:
            p.stat()
        except FileNotFoundError:
            continue
        except PermissionError:
            return f"{PORT_FILE_UNREADABLE_MSG}（{p}）"
        except OSError:
            continue
        try:
            with p.open("rb"):
                pass
        except PermissionError:
            return f"{PORT_FILE_UNREADABLE_MSG}（{p}）"
        except OSError:
            continue
        return f"{PORT_FILE_MALFORMED_MSG}（{p}）"
    # 文件 stat 不到时，再看父目录是否可访问，以识别「目录被拦截」的情况
    for p in devtools_port_candidates():
        parent = p.parent
        try:
            if parent.is_dir() and not os.access(parent, os.R_OK | os.X_OK):
                return f"{PORT_FILE_UNREADABLE_MSG}（{parent}）"
        except OSError:
            return f"{PORT_FILE_UNREADABLE_MSG}（{parent}）"
    return PORT_FILE_MISSING_MSG


def locate_chrome_executable() -> tuple[str | None, str]:
    """定位真实系统 Chrome 可执行文件，确保浏览器指纹与真实用户一致。"""
    sys_name = platform.system()
    if sys_name == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c, "low"
    elif sys_name == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get(
            "ProgramFiles(x86)", r"C:\Program Files (x86)"
        )
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(
                program_files, "Google", "Chrome", "Application", "chrome.exe"
            ),
            os.path.join(
                program_files_x86, "Google", "Chrome", "Application", "chrome.exe"
            ),
            os.path.join(
                local_app_data, "Google", "Chrome", "Application", "chrome.exe"
            )
            if local_app_data
            else "",
            os.path.join(
                program_files, "Microsoft", "Edge", "Application", "msedge.exe"
            ),
            os.path.join(
                program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"
            ),
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c, "low"
    else:
        # Linux
        for binary in (
            "google-chrome",
            "google-chrome-stable",
            "chromium-browser",
            "microsoft-edge",
        ):
            found = shutil.which(binary)
            if found:
                return found, "low"

    return None, "high"


class CdpToggleBackend:
    """日常 Chrome 后端：通过 chrome://inspect 开关暴露的端口附着。

    优点：直接复用用户已登录状态。
    限制：每次全新连接需用户在 Chrome 弹窗中点击「允许」，无法无人值守。
    """

    name = "cdp"
    fingerprint_risk = "low"

    def __init__(self) -> None:
        self.browser: Browser | None = None
        self._on_disconnected_cb: Any = None

    def set_disconnect_callback(self, cb: Any) -> None:
        """设置断开连接时的清理回调。"""
        self._on_disconnected_cb = cb

    def can_connect(self) -> bool:
        """检查 DevToolsActivePort 是否可读，或已显式指定 POLARIS_BROWSER_CDP_URL。"""
        if env_cdp_url() is not None:
            return True
        p = find_devtools_port_file()
        return p is not None and read_devtools_ws_url(p) is not None

    def unattended_ok(self) -> bool:
        """未连接时禁止无人值守发起连接，防止半夜静默弹窗阻塞。"""
        return False

    async def connect(self, pw: Playwright) -> Browser:
        """通过 CDP 连接至日常 Chrome。"""
        ws_url = env_cdp_url()
        if not ws_url:
            p = find_devtools_port_file()
            ws_url = read_devtools_ws_url(p) if p else None
        if not ws_url:
            raise HubError("attach_failed", diagnose_devtools_port())

        # 60 秒超时时间供用户在弹窗中点击「允许」
        try:
            browser = await pw.chromium.connect_over_cdp(ws_url, timeout=60000)
        except (PwError, PlaywrightError) as err:
            if "Timeout" not in str(err):
                raise
            raise HubError(
                "attach_failed",
                "已连上 Chrome 调试端口，但 60 秒内未获授权：请在 Chrome 弹出的"
                "「允许远程调试」对话框中点击「允许」后重试；"
                "如需免弹窗，请改用 Polaris Browser Bridge 扩展",
            ) from err
        self.browser = browser

        def on_disconnected(_browser: Any = None) -> None:
            self.browser = None
            if self._on_disconnected_cb:
                self._on_disconnected_cb()

        browser.on("disconnected", on_disconnected)
        return browser

    async def close(self) -> None:
        """断开 CDP 会话，注意：connect_over_cdp 下 close 仅关闭客户端连接，不关闭用户浏览器。"""
        if self.browser:
            await self.browser.close()
            self.browser = None


class ManagedBackend:
    """托管 Chrome 后端：使用系统 Chrome 启动独立的专用 profile。

    优点：可无人值守定时运行，会话独立稳定，支持端点复用。
    """

    name = "managed"

    def __init__(self, profile: str = "default", headless: bool = False) -> None:
        self.profile = profile
        self.headless = headless
        self.browser: Browser | None = None
        self.chrome_bin, self.fingerprint_risk = locate_chrome_executable()
        self._on_disconnected_cb: Any = None

    def set_disconnect_callback(self, cb: Any) -> None:
        """设置断开连接时的清理回调。"""
        self._on_disconnected_cb = cb

    def unattended_ok(self) -> bool:
        """托管 Chrome 启动时无需用户点选弹窗，允许无人值守运行。"""
        return True

    def _check_endpoint_alive(self, endpoint_file: Path) -> str | None:
        """检查已保存的 endpoint.json 对应的 Chrome 进程与端口是否仍存活。"""
        if not endpoint_file.exists():
            return None
        try:
            data = json.loads(endpoint_file.read_text(encoding="utf-8"))
            pid = data.get("pid")
            ws_url = data.get("ws_url")
            profile = data.get("profile")
            if not pid or not ws_url or profile != self.profile:
                return None

            # 探测进程是否存在
            os.kill(pid, 0)

            # 探测 HTTP /json/version 是否可响应
            parsed = urlparse(ws_url)
            port = parsed.port or 9222
            http_conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
            try:
                http_conn.request("GET", "/json/version")
                resp = http_conn.getresponse()
                if resp.status == 200:
                    return str(ws_url)
            finally:
                http_conn.close()
        except (
            OSError,
            ValueError,
            TimeoutError,
            json.JSONDecodeError,
            http.client.HTTPException,
        ) as err:
            logger.debug("复用旧端点探测失败 (%s)，准备清理并重新启动", err)
            try:
                endpoint_file.unlink()
            except OSError:
                pass
        return None

    async def connect(self, pw: Playwright) -> Browser:
        """启动或复用托管 Chrome 实例。"""
        endpoint_file = CFG / "endpoint.json"
        alive_ws = self._check_endpoint_alive(endpoint_file)
        if alive_ws:
            try:
                browser = await pw.chromium.connect_over_cdp(alive_ws, timeout=10000)
                self.browser = browser
                self._bind_disconnect(browser)
                return browser
            except (PwError, PlaywrightError, OSError) as err:
                logger.debug("复用已有连接失败: %s", err)
                try:
                    endpoint_file.unlink()
                except OSError:
                    pass

        profile_dir = CFG / "profiles" / self.profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        port_file = profile_dir / "DevToolsActivePort"
        if port_file.exists():
            try:
                port_file.unlink()
            except OSError:
                pass

        exe_path = self.chrome_bin
        if not exe_path:
            exe_path = pw.chromium.executable_path
            self.fingerprint_risk = "high"

        cmd = [
            exe_path,
            f"--user-data-dir={profile_dir.resolve()}",
            "--remote-debugging-port=0",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if self.headless:
            cmd.append("--headless=new")

        # 异步启动子进程，参数列表安全传参
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

        deadline = time.time() + 10.0
        ws_url: str | None = None
        while time.time() < deadline:
            if port_file.exists():
                ws_url = read_devtools_ws_url(port_file)
                if ws_url:
                    break
            await asyncio.sleep(0.1)

        if not ws_url:
            proc.terminate()
            raise HubError(
                "attach_failed", "启动托管 Chrome 并等待 DevToolsActivePort 超时（10s）"
            )

        # 原子写入 endpoint.json
        endpoint_data = {
            "pid": proc.pid,
            "ws_url": ws_url,
            "profile": self.profile,
            "started_at": time.time(),
        }
        tmp_file = CFG / "endpoint.json.tmp"
        tmp_file.write_text(json.dumps(endpoint_data), encoding="utf-8")
        os.replace(tmp_file, endpoint_file)

        browser = await pw.chromium.connect_over_cdp(ws_url, timeout=15000)
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


async def select_backend() -> tuple[Backend, str]:
    """根据环境变量和运行环境自动裁决最适后端。"""
    explicit = os.environ.get(ENV_BACKEND, "auto").strip().lower()
    profile = os.environ.get(ENV_PROFILE, "default").strip()
    headless = os.environ.get(ENV_HEADLESS, "0").strip() in ("1", "true", "yes")

    if explicit == "cdp":
        return CdpToggleBackend(), "explicit_cdp"
    if explicit == "managed":
        return ManagedBackend(profile=profile, headless=headless), "explicit_managed"
    if explicit == "extension":
        from .bridge_relay import ExtensionBackend

        return ExtensionBackend(), "explicit_extension"

    # auto 模式裁决顺序：
    # 1. 尝试 T8b ExtensionBackend 握手（启动中继并等待扩展最多 2 秒）
    try:
        from .bridge_relay import ExtensionBackend, extension_wait_s, get_or_start_relay

        relay = await get_or_start_relay()
        # 已配对过扩展时多等一个唤醒周期，避免扩展休眠导致回落到需要点「允许」的 cdp 后端
        if await relay.wait_for_extension(timeout=extension_wait_s(explicit=False)):
            ext = ExtensionBackend()
            ext.relay = relay
            return ext, "extension_handshake_ready"
    except ImportError, OSError, RuntimeError:
        pass

    # 2. 检查日常 Chrome DevToolsActivePort
    cdp_backend = CdpToggleBackend()
    if cdp_backend.can_connect():
        return cdp_backend, "cdp_devtools_port_active"

    # 3. 兜底进入专用 profile 托管模式
    return ManagedBackend(
        profile=profile, headless=headless
    ), "managed_profile_fallback"


class BrowserHub:
    """BrowserHub 单例：全进程统一的浏览器生命周期、隔离及多后端调度中枢。"""

    def __init__(self) -> None:
        self.backend: Backend | None = None
        self.backend_reason: str = "init"
        # 两套驱动（patchright / playwright）类型同构但不同模块，统一按 Any 处理
        self.pw: Any = None
        self.browser: Browser | None = None
        self.work_page: Page | None = None
        self.has_window: bool = False
        self.owned_targets: set[str] = set()
        # targetId -> Page：仅记录 Polaris 自建页，避免遍历用户日常标签
        self._owned_pages: dict[str, Page] = {}
        self._lock = asyncio.Lock()
        self.page_lock = asyncio.Lock()
        self._last_activity = time.time()
        self.driver_name = "patchright"
        self._cached_site_logins: dict[str, bool] = {}

        # 空闲释放分钟数
        release_env = os.environ.get(ENV_IDLE_RELEASE_MIN)
        if release_env is not None and release_env.strip().isdigit():
            self.idle_release_min = int(release_env.strip())
        else:
            self.idle_release_min = 0  # 默认由后端动态指定

        # 启动后台空闲守护任务
        self._watchdog_task: asyncio.Task[None] | None = None

    def mark_activity(self) -> None:
        """标记最新工具调用时间戳。"""
        self._last_activity = time.time()

    def set_cached_login(self, site: str, logged_in: bool) -> None:
        """缓存站点的登录探测结果。"""
        self._cached_site_logins[site] = logged_in

    def get_cached_site_statuses(self) -> list[dict[str, Any]]:
        """获取所有已缓存站点的状态展示。"""
        res = []
        for s, li in self._cached_site_logins.items():
            res.append({"site": s, "logged_in": li})
        return res

    async def _ensure_connected(self) -> None:
        """确保底层 Playwright 和 Browser 已连接。"""
        if self.browser is not None and self.browser.is_connected():
            return

        if self.backend is None:
            self.backend, self.backend_reason = await select_backend()
            if hasattr(self.backend, "set_disconnect_callback"):
                self.backend.set_disconnect_callback(self._on_browser_disconnected)

            # extension 后端默认空闲 10 分钟自动释放连接与标签
            if (
                self.backend.name == "extension"
                and os.environ.get(ENV_IDLE_RELEASE_MIN) is None
            ):
                self.idle_release_min = 10

        pw_init: Any  # 同上：两套驱动入口函数类型同构，按 Any 处理
        # cdp / extension 后端默认用 playwright：patchright 附着日常 Chrome（chrome://inspect 开关模式）时
        # connect_over_cdp 会在全部命令已应答后仍不返回（2026-10 真机复现），playwright 3~4 秒即连上。
        # extension 后端经中继转发，patchright 同样会卡死并触发降级重连，统一用 playwright
        default_driver = (
            "playwright" if self.backend.name in ("cdp", "extension") else "patchright"
        )
        driver_choice = os.environ.get(ENV_DRIVER, default_driver).strip().lower()
        if driver_choice == "playwright":
            from playwright.async_api import async_playwright as pw_init

            self.driver_name = "playwright"
        else:
            try:
                from patchright.async_api import async_playwright as pw_init

                self.driver_name = "patchright"
            except ImportError:
                from playwright.async_api import async_playwright as pw_init

                self.driver_name = "playwright"

        if self.pw is None:
            self.pw = await pw_init().start()

        self.browser = await self.backend.connect(self.pw)

        # 启动空闲释放监听
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._idle_watchdog())

    def _on_browser_disconnected(self) -> None:
        """底层连接断开处理，重置状态。"""
        self.browser = None
        self.work_page = None
        self.has_window = False
        self.owned_targets.clear()
        self._owned_pages.clear()

    async def _find_page_by_marker(self, marker: str, timeout_s: float = 5.0) -> Page:
        """按唯一标记 URL 在 contexts[0].pages 中定位自建页（不对任何页开 CDP 会话）。"""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self.browser and self.browser.contexts:
                for p in self.browser.contexts[0].pages:
                    if not p.is_closed() and p.url == marker:
                        return p
            await asyncio.sleep(0.1)
        raise HubError(
            "no_page", f"未能在 {timeout_s} 秒内定位自建目标页 (marker={marker})"
        )

    async def _create_owned_page_locked(self, url: str = "about:blank") -> Page:
        """必须在持锁状态下调用，创建并记录自建页面。"""
        await self._ensure_connected()
        assert self.browser is not None

        # 扩展后端运行在单标签隔离模式：复用已连接的目标页面
        if (
            self.backend
            and self.backend.name == "extension"
            and self.browser.contexts
            and self.browser.contexts[0].pages
        ):
            page = self.browser.contexts[0].pages[0]
            # 中继只暴露扩展自建的单个标签，无需再开 CDP 会话查询目标 ID；
            # 且 chrome.debugger 不允许 Target.attachToBrowserTarget（new_cdp_session 会报 Not allowed）
            self.owned_targets.add("ext-tab")
            self.has_window = True
            if url != "about:blank":
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return page

        # 每次创建新页面都在新窗口打开，彻底杜绝混入用户日常标签页
        # 唯一标记 URL：之后仅按 page.url 定位，不触碰用户任何标签
        marker = f"about:blank#polaris-{uuid.uuid4().hex}"
        cdp = await self.browser.new_browser_cdp_session()
        try:
            res = await cdp.send(
                "Target.createTarget",
                {"url": marker, "newWindow": True, "background": True},
            )
            target_id = res["targetId"]
        finally:
            await cdp.detach()

        self.owned_targets.add(target_id)
        self.has_window = True

        page = await self._find_page_by_marker(marker, timeout_s=5.0)
        self._owned_pages[target_id] = page
        if url != "about:blank":
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page

    async def _page_locked(self, unattended: bool = False) -> Page:
        """page() 的无锁实现，调用方必须已持有 self._lock（asyncio.Lock 不可重入）。"""
        if self.browser is None or not self.browser.is_connected():
            # 无人值守检查：若当前后端不支持静默连接则拒绝发起连接
            if self.backend is None:
                self.backend, self.backend_reason = await select_backend()
                if hasattr(self.backend, "set_disconnect_callback"):
                    self.backend.set_disconnect_callback(self._on_browser_disconnected)

            if unattended and not self.backend.unattended_ok():
                raise HubError(
                    "needs_user_approval",
                    "请在 Chrome 弹窗中允许一次远程调试，或安装 Polaris Browser Bridge 扩展实现免弹窗",
                )
            await self._ensure_connected()

        if self.work_page is None or self.work_page.is_closed():
            self.work_page = await self._create_owned_page_locked()
        return self.work_page

    async def page(self, *, unattended: bool = False) -> Page:
        """获取复用的工作页，未连接时建立连接。"""
        self.mark_activity()
        async with self._lock:
            return await self._page_locked(unattended)

    async def new_owned_page(self, url: str = "about:blank") -> Page:
        """创建一个新的专属标签页，与用户日常标签隔离。"""
        self.mark_activity()
        async with self._lock:
            if self.backend and self.backend.name == "extension":
                p = await self._page_locked()
                if url != "about:blank":
                    await p.goto(url, wait_until="domcontentloaded", timeout=30000)
                return p
            return await self._create_owned_page_locked(url)

    async def owned_pages(self) -> list[Page]:
        """返回所有当前存活的自有页面。严禁访问或返回用户日常标签。"""
        async with self._lock:
            if (
                not self.browser
                or not self.browser.is_connected()
                or not self.browser.contexts
            ):
                return []
            if self.backend and self.backend.name == "extension":
                return [p for p in self.browser.contexts[0].pages if not p.is_closed()]
            # 直接返回自建页字典中未关闭者，不遍历用户日常标签
            for tid in [t for t, p in self._owned_pages.items() if p.is_closed()]:
                del self._owned_pages[tid]
            return list(self._owned_pages.values())

    async def status(self) -> dict[str, Any]:
        """汇总当前 BrowserHub 的运行时状态。"""
        pages = await self.owned_pages()
        connected = self.browser is not None and self.browser.is_connected()
        try:
            from .bridge_relay import get_or_create_token

            token = get_or_create_token()
        except ImportError, OSError:
            token = ""
        ext_dir = str(Path(__file__).resolve().parent.parent / "extension")
        return {
            "backend": self.backend.name if self.backend else "none",
            "reason": self.backend_reason,
            "connected": connected,
            "driver": self.driver_name,
            "profile": getattr(self.backend, "profile", None) if self.backend else None,
            "owned_tabs": len(pages),
            "fingerprint_risk": getattr(self.backend, "fingerprint_risk", "low")
            if self.backend
            else "low",
            "sites": self.get_cached_site_statuses(),
            "extension_dir": ext_dir,
            "bridge_token": token,
            "bridge_token_path": str(CFG / "bridge_token"),
            "pair_instruction": f"在 Chrome (chrome://extensions) 加载扩展并在选项页粘贴配对令牌: {token}",
        }

    async def _idle_watchdog(self) -> None:
        """后台空闲检查：达到释放时间后自动断开连接。"""
        while True:
            await asyncio.sleep(15)
            if self.idle_release_min <= 0 or self.browser is None:
                continue
            if time.time() - self._last_activity >= self.idle_release_min * 60:
                async with self._lock:
                    if self.browser and (
                        time.time() - self._last_activity >= self.idle_release_min * 60
                    ):
                        # 仅安全关闭自有页面与断开会话
                        if self.backend:
                            await self.backend.close()
                        self._on_browser_disconnected()
                        break


# 模块级全局 Hub 单例
_HUB: BrowserHub | None = None
_HUB_LOCK = asyncio.Lock()


async def get_hub() -> BrowserHub:
    """获取进程全局唯一的 BrowserHub 单例。"""
    global _HUB
    if _HUB is None:
        async with _HUB_LOCK:
            if _HUB is None:
                _HUB = BrowserHub()
    return _HUB

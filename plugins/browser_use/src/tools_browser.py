"""交互式浏览器工具集。

为何需要该模块：
1. 替代旧有的臃肿 8 工具实现，全面拥抱精简、省 token 的现代化 Agent 交互协议；
2. 统一错误码与返回结构（ok: true | ok: false + error: {code, message}）；
3. 严格遵循隔离原则：所有交互只对 Hub 所持有的自有标签页生效，防止污染用户日常会话。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Literal

from patchright.async_api import Page

from .browser_hub import HubError, PlaywrightError, PwError, get_hub
from .extract import extract_structured, read_page_content
from .snapshot_js import SCROLL_INFO_JS, SNAPSHOT_JS

REF_PATTERN = re.compile(r"^e\d{1,5}$")


async def get_page_tab_id(page: Page) -> str:
    """获取页面的 CDP 目标 targetId 作为唯一 tab_id。"""
    try:
        s = await page.context.new_cdp_session(page)
        info = await s.send("Target.getTargetInfo")
        await s.detach()
        return str(info.get("targetInfo", {}).get("targetId", ""))
    except (PwError, PlaywrightError, OSError):
        return ""


async def tool_browser_open(url: str, new_tab: bool = False) -> dict[str, Any]:
    """打开指定 URL 并等待初始网络加载完成。"""
    if not url.startswith(("http://", "https://")):
        return {
            "ok": False,
            "error": {
                "code": "invalid_args",
                "message": "URL 必须以 http:// 或 https:// 开头",
            },
        }

    try:
        hub = await get_hub()
        async with hub.page_lock:
            if new_tab:
                page = await hub.new_owned_page()
            else:
                page = await hub.page(unattended=False)

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except (PwError, PlaywrightError, TimeoutError):
                pass

            tab_id = await get_page_tab_id(page)
            title = await page.title()
            res: dict[str, Any] = {
                "ok": True,
                "tab_id": tab_id,
                "url": page.url,
                "title": title,
            }
            if new_tab and hub.backend and hub.backend.name == "extension":
                res["note"] = "扩展模式仅单标签，已复用当前活动工作标签"
            return res
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, PlaywrightError, OSError, TimeoutError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "attach_failed", "message": str(e)}}


async def tool_browser_read(
    mode: Literal["article", "markdown", "text", "links"] = "article",
    max_chars: int = 6000,
    offset: int = 0,
    selector: str | None = None,
) -> dict[str, Any]:
    """以低 token 消耗的模式读取当前活动工作页的正文、Markdown、纯文本或链接。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            page = await hub.page(unattended=False)
            res = await read_page_content(
                page, mode=mode, max_chars=max_chars, offset=offset, selector=selector
            )
            return {"ok": True, **res}
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, PlaywrightError, OSError, TimeoutError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "no_page", "message": str(e)}}


async def tool_browser_snapshot(
    scope: Literal["viewport", "page"] = "viewport",
    max_items: int = 80,
) -> dict[str, Any]:
    """对当前页面可交互元素进行快照编码，打上 e<N> 引用编号以便后续精准操作。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            page = await hub.page(unattended=False)
            res = await page.evaluate(
                SNAPSHOT_JS, {"scope": scope, "max_items": max_items}
            )
            return {
                "ok": True,
                "snapshot": res.get("snapshot", ""),
                "total": res.get("total", 0),
                "displayed": res.get("displayed", 0),
                "url": page.url,
                "title": await page.title(),
            }
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, PlaywrightError, OSError, TimeoutError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "no_page", "message": str(e)}}


async def tool_browser_act(
    ref: str,
    action: Literal[
        "click", "fill", "fill_and_enter", "hover", "select", "press", "back"
    ],
    text: str = "",
) -> dict[str, Any]:
    """对快照生成的 e<N> 引用元素执行点击、输入、悬停或回退操作。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            page = await hub.page(unattended=False)
            old_url = page.url

            if action == "back":
                await page.go_back(timeout=10000)
                return {
                    "ok": True,
                    "url_changed": page.url != old_url,
                    "url": page.url,
                    "title": await page.title(),
                }

            # 严格校验 ref 避免选择器注入攻击
            if not REF_PATTERN.match(ref):
                raise HubError(
                    "invalid_args", f"非法元素引用格式 '{ref}'，必须符合 e<数字> 格式"
                )

            locator = page.locator(f'[data-polaris-ref="{ref}"]')
            count = await locator.count()
            if count == 0:
                raise HubError(
                    "stale_ref",
                    f"页面元素引用 '{ref}' 已失效或页面结构已变化，请先调用 browser_snapshot 刷新",
                )

            target = locator.first

            if action == "click":
                await target.click(timeout=10000)
            elif action == "fill":
                await target.fill(text, timeout=10000)
            elif action == "fill_and_enter":
                await target.fill(text, timeout=10000)
                await target.press("Enter")
            elif action == "hover":
                await target.hover(timeout=10000)
            elif action == "select":
                await target.select_option(text, timeout=10000)
            elif action == "press":
                await page.keyboard.press(text)

            # 稍等片刻以便单页应用或跳转响应
            await asyncio.sleep(0.5)

            return {
                "ok": True,
                "url_changed": page.url != old_url,
                "url": page.url,
                "title": await page.title(),
            }
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (
        PwError,
        PlaywrightError,
        OSError,
        TimeoutError,
        ValueError,
        RuntimeError,
    ) as e:
        code = "timeout" if "timeout" in str(e).lower() else "invalid_args"
        return {"ok": False, "error": {"code": code, "message": str(e)}}


async def tool_browser_scroll(
    direction: Literal["down", "up"] = "down",
    times: int = 1,
) -> dict[str, Any]:
    """向上或向下平滑滚动页面，返回滚动后的纵坐标与触底状态。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            page = await hub.page(unattended=False)
            count = min(max(1, times), 10)
            delta = 600 if direction == "down" else -600

            for _ in range(count):
                await page.evaluate(f"window.scrollBy(0, {delta});")
                await asyncio.sleep(0.2)

            info = await page.evaluate(SCROLL_INFO_JS)
            return {
                "ok": True,
                "scroll_y": info.get("scroll_y", 0),
                "at_bottom": info.get("at_bottom", False),
            }
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, PlaywrightError, OSError, TimeoutError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "no_page", "message": str(e)}}


async def tool_browser_extract(
    container: str,
    fields: dict[str, str],
    max_items: int = 50,
) -> dict[str, Any]:
    """根据 CSS 选择器规则对当前页面列表批量抽取字段。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            page = await hub.page(unattended=False)
            res = await extract_structured(
                page, container=container, fields=fields, max_items=max_items
            )
            return {"ok": True, "items": res["items"], "count": res["count"]}
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (
        PwError,
        PlaywrightError,
        OSError,
        TimeoutError,
        ValueError,
        RuntimeError,
    ) as e:
        return {"ok": False, "error": {"code": "invalid_args", "message": str(e)}}


async def tool_browser_tabs(
    action: Literal["list", "switch", "close"] = "list",
    tab_id: str = "",
) -> dict[str, Any]:
    """管理 Polaris 自建的浏览器标签页。"""
    try:
        hub = await get_hub()
        async with hub.page_lock:
            pages = await hub.owned_pages()

            if action == "list":
                tabs = []
                for p in pages:
                    tid = await get_page_tab_id(p)
                    tabs.append(
                        {
                            "tab_id": tid,
                            "url": p.url,
                            "title": await p.title(),
                        }
                    )
                return {"ok": True, "tabs": tabs, "count": len(tabs)}

            if not tab_id:
                raise HubError(
                    "invalid_args", "执行 switch 或 close 操作时必须提供 tab_id"
                )

            target_page: Page | None = None
            for p in pages:
                tid = await get_page_tab_id(p)
                if tid == tab_id:
                    target_page = p
                    break

            if target_page is None:
                raise HubError("no_page", f"未找到专属标签页 tab_id={tab_id}")

            if action == "switch":
                await target_page.bring_to_front()
                hub.work_page = target_page
                return {"ok": True, "active_tab": tab_id, "url": target_page.url}

            if action == "close":
                await target_page.close()
                hub.owned_targets.discard(tab_id)
                if hub.work_page == target_page:
                    hub.work_page = None
                return {"ok": True, "closed_tab": tab_id}

            raise HubError("invalid_args", f"不支持的 tabs 操作: {action}")
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (
        PwError,
        PlaywrightError,
        OSError,
        TimeoutError,
        ValueError,
        RuntimeError,
    ) as e:
        return {"ok": False, "error": {"code": "invalid_args", "message": str(e)}}


async def tool_browser_status() -> dict[str, Any]:
    """查看浏览器多后端连接状态与站点频次配额。"""
    try:
        hub = await get_hub()
        st = await hub.status()

        return {"ok": True, **st}
    except HubError as e:
        return {"ok": False, "error": e.to_dict()}
    except (PwError, PlaywrightError, OSError, TimeoutError, RuntimeError) as e:
        return {"ok": False, "error": {"code": "internal_error", "message": str(e)}}

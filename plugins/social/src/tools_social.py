"""social_* 读工具的实现（搜索 / 热榜 / 动态 / 正文 / 平台清单 / 自测）。

为何需要该模块：
1. 把配方采集引擎（harvest）包装成面向 Agent 的「读」契约，统一返回
   {"ok": true, ...} / {"ok": false, "error": {"code", "message"}}；
2. social_read 在自建页打开帖文 / 文章并抽取正文 Markdown，同样计入该平台的共享限速；
3. 外部网页内容一律视为不可信数据，只做抽取，绝不据此改写配方或配置。
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import random
import re
from typing import Any
from urllib.parse import urlparse

import trafilatura
from patchright.async_api import Error as PwError

from .gate import FALLBACK_KEY, WRITE_PLATFORMS, limits_for, platform_for_url, rate_key
from .harvest.engine import check_block_signals
from .harvest.loader import load_all_recipes
from .ratelimit import acquire, get_site_status
from .tools_harvest import tool_harvest, tool_harvest_selftest
from .utils.browser_hub import HubError, get_hub
from .utils.extract import paginate_content

logger = logging.getLogger("polaris.tools_social")

# 单次页面导航超时（毫秒）
NAV_TIMEOUT_MS = 30000


def err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    """构造统一错误返回。"""
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def _hub_err(e: HubError) -> dict[str, Any]:
    return {"ok": False, "error": e.to_dict()}


async def _run_action(
    platform: str, action: str, params: dict[str, Any], max_items: int
) -> dict[str, Any]:
    """校验配方与动作后执行采集，结果统一以 platform 字段返回。"""
    recipes, diag = load_all_recipes()
    recipe = recipes.get(platform)
    if recipe is None:
        info = diag.get(platform, {}).get("error")
        if info:
            return err("recipe_error", f"平台 {platform} 配方解析错误: {info}")
        return err("unsupported_platform", f"未找到平台 {platform} 的配方")
    if action not in recipe.actions:
        return err(
            "unsupported_action",
            f"平台 {platform} 不支持动作 '{action}'，"
            f"可用动作: {', '.join(recipe.actions)}",
        )
    res = await tool_harvest(
        site=platform, action=action, params=params, max_items=max_items
    )
    if not res.get("ok"):
        return res
    return {
        "ok": True,
        "platform": platform,
        "action": action,
        "items": res["items"],
        "count": res["count"],
    }


async def tool_social_search(
    platform: str, query: str, max_items: int
) -> dict[str, Any]:
    """按关键词搜索平台内容。"""
    q = query.strip()
    if not q:
        return err("invalid_args", "query 不能为空")
    return await _run_action(platform, "search", {"q": q}, max_items)


async def tool_social_hot(platform: str, max_items: int) -> dict[str, Any]:
    """获取平台热榜。"""
    return await _run_action(platform, "hot", {}, max_items)


async def tool_social_feed(
    platform: str, handle: str, max_items: int
) -> dict[str, Any]:
    """获取指定用户的公开动态时间线。"""
    recipes, _ = load_all_recipes()
    recipe = recipes.get(platform)
    if recipe is not None and "user_timeline" not in recipe.actions:
        return await _run_action(platform, "user_timeline", {}, max_items)
    h = handle.strip().lstrip("@")
    if not h:
        return err("invalid_args", "handle 不能为空")
    return await _run_action(platform, "user_timeline", {"handle": h}, max_items)


_META_AUTHOR_RE = re.compile(
    r"""<meta[^>]+name=["']author["'][^>]*content=["']([^"']+)["']""", re.IGNORECASE
)


def _meta_author(html: str) -> str:
    """trafilatura 对非拉丁字符的作者名会拒收，这里从 <meta name="author"> 兜底。"""
    m = _META_AUTHOR_RE.search(html)
    return html_lib.unescape(m.group(1)).strip() if m else ""


def extract_article(html: str, url: str) -> dict[str, Any]:
    """从渲染后的 HTML 抽取正文 Markdown 与元信息（纯函数，便于离线测试）。"""
    content = trafilatura.extract(
        html, output_format="markdown", include_links=True, url=url
    )
    text = (content or "").strip()
    if not text:
        text = (trafilatura.html2txt(html) or "").strip()
    meta = trafilatura.extract_metadata(html, default_url=url)
    return {
        "title": (getattr(meta, "title", None) or "") if meta else "",
        "author": (
            (getattr(meta, "author", None) if meta else None) or _meta_author(html)
        ),
        "published_at": (getattr(meta, "date", None) or "") if meta else "",
        "content": text,
    }


async def tool_social_read(url: str, max_chars: int, offset: int) -> dict[str, Any]:
    """在自建页打开帖文 / 文章并抽取正文 Markdown，计入对应平台的限速。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return err("invalid_args", "url 必须是 http:// 或 https:// 开头的有效地址")

    key = platform_for_url(url)
    limits = limits_for(key)
    try:
        hub = await get_hub()
        # 先在页面锁内取页（可能抛 needs_user_approval，此时不应消耗限速名额），再占名额
        await hub.page_lock.acquire()
        try:
            page = await hub.page(unattended=True)
            await acquire(key, limits)
        except BaseException:
            hub.page_lock.release()
            raise
        try:
            resp = await page.goto(
                url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS
            )
            recipe = load_all_recipes()[0].get(key)
            if recipe is not None:
                await check_block_signals(page, resp, recipe.block_signals, key)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except PwError:
                logger.debug("等待 networkidle 超时，按已加载内容抽取: %s", url)
            await asyncio.sleep(random.uniform(0.3, 0.8))
            html = await page.content()
            final_url = page.url
            page_title = await page.title()
        finally:
            hub.page_lock.release()
    except HubError as e:
        return _hub_err(e)
    except (PwError, OSError, TimeoutError, RuntimeError) as e:
        return err("read_failed", str(e))

    art = extract_article(html, final_url)
    if not art["content"]:
        return err("empty_content", "未能从页面抽取到正文，可能需要登录或页面结构特殊")
    content, content_hash, truncated, next_offset = paginate_content(
        art["content"], offset=offset, max_chars=max_chars
    )
    return {
        "ok": True,
        "platform": key,
        "url": final_url,
        "title": art["title"] or page_title,
        "author": art["author"],
        "published_at": art["published_at"],
        "content": content,
        "content_hash": content_hash,
        "truncated": truncated,
        "next_offset": next_offset,
    }


async def tool_social_selftest(platform: str) -> dict[str, Any]:
    """对指定平台的全部读动作做一次最小自测并报告字段完整率。"""
    try:
        res = await tool_harvest_selftest(platform)
    except HubError as e:
        return _hub_err(e)
    except (PwError, OSError, RuntimeError, ValueError) as e:
        return err("selftest_failed", str(e))
    if "site" in res:
        res = {**res, "platform": res.pop("site")}
    return res


async def tool_social_platforms() -> dict[str, Any]:
    """列出平台、读动作与参数、配方状态、登录态缓存与限速余量。"""
    try:
        recipes, diag = load_all_recipes()
        hub = await get_hub()
        logins = {s["site"]: s["logged_in"] for s in hub.get_cached_site_statuses()}
        platforms: list[dict[str, Any]] = []
        for pid, recipe in recipes.items():
            actions = {
                name: {
                    "description": act.description,
                    "method": act.extract.method,
                    "params": {
                        p: {
                            "type": spec.type,
                            "description": spec.description,
                            "default": spec.default,
                            "required": spec.required,
                        }
                        for p, spec in act.params.items()
                    },
                }
                for name, act in recipe.actions.items()
            }
            rate = get_site_status(pid, recipe.limits)
            platforms.append(
                {
                    "platform": pid,
                    "name": recipe.site.name,
                    "status": recipe.status,
                    "origin": diag.get(pid, {}).get("origin", "builtin"),
                    "actions": actions,
                    "logged_in": logins.get(pid),
                    "rate": {
                        "min_interval_s": recipe.limits.min_interval_s,
                        "active_hours": recipe.limits.active_hours,
                        "remaining_hour": rate["remaining_hour"],
                        "remaining_day": rate["remaining_day"],
                        "cooling_until": rate["cooling_until"],
                    },
                }
            )
        errors = [
            {"platform": k, "error": v.get("error")}
            for k, v in diag.items()
            if v.get("status") == "error"
        ]
        return {
            "ok": True,
            "platforms": platforms,
            "recipe_errors": errors,
            "write_only_platforms": [
                p for p in WRITE_PLATFORMS if rate_key(p) not in recipes
            ],
            "rate_key_aliases": {"twitter": "x"},
            "default_rate_key": FALLBACK_KEY,
        }
    except (OSError, RuntimeError, ValueError) as e:
        return err("internal_error", str(e))

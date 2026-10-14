"""social 真机冒烟测试（手工运行，不进 CI）。

运行方式（在 plugins/social 目录）：
    cd plugins/social && POLARIS_BROWSER_BACKEND=cdp uv run python scripts/live_smoke.py | tee /tmp/live_smoke.log

警告：本脚本会连接本机日常 Chrome（cdp 后端需已打开 chrome://inspect 远程调试开关，
Chrome 会弹出「允许远程调试」对话框，必须人工点击允许，60 秒内）。无权读取 Chrome 数据目录中的
DevToolsActivePort 时，请改用 Polaris Browser Bridge 扩展，或设置 POLARIS_BROWSER_CDP_URL。
全程只建立一条连接，只在插件自建窗口中做只读操作（打开、搜索、读取），每站导航 ≤15 次，
不点赞 / 关注 / 评论 / 发帖，不读 cookie，不触碰用户已有标签。

步骤（每步输出一行 JSON）：
    platforms -> zhihu 登录态 -> social_search(zhihu, "AI Agent") -> social_hot(zhihu)
    -> social_read(第一条结果) -> social_search(x, "AI agent") -> social_feed(x, "OpenAI")
    -> 把 3 条结果用资料库（knowledge_base/src/vault.py）的 save_docs 存为文档。
资料库默认写到 /tmp/polaris-vault-smoke（--vault 可改），绝不写用户真实资料库。
遇到风控信号（blocked / cooling_down）立即停止该站点。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from src.gate import acquire_platform
from src.harvest.loader import load_all_recipes
from src.tools_social import (
    tool_social_feed,
    tool_social_hot,
    tool_social_platforms,
    tool_social_read,
    tool_social_search,
)
from src.utils.browser_hub import HubError, get_hub

DEFAULT_VAULT = "/tmp/polaris-vault-smoke"  # nosec B108 - 冒烟专用临时资料库，约定路径
RISK_CODES = {"blocked", "cooling_down"}


def emit(step: str, **kw: Any) -> None:
    print(json.dumps({"step": step, **kw}, ensure_ascii=False, default=str), flush=True)


def brief(items: list[dict[str, Any]], n: int = 3) -> list[dict[str, str]]:
    return [
        {"title": (i.get("title") or "")[:80], "url": i.get("url") or ""}
        for i in items[:n]
    ]


async def timed(coro: Any) -> tuple[Any, float]:
    t = time.time()
    r = await coro
    return r, round(time.time() - t, 2)


def load_vault_module() -> ModuleType:
    """按文件路径加载资料库核心（避免与本插件同名的 src 包冲突）。"""
    path = PLUGIN_DIR.parent / "knowledge_base" / "src" / "vault.py"
    spec = importlib.util.spec_from_file_location("polaris_vault_smoke", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载资料库模块: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["polaris_vault_smoke"] = mod
    spec.loader.exec_module(mod)
    return mod


def fix_zhihu_url(u: str) -> str:
    """api.zhihu.com 形式转 Web 形式（仅冒烟脚本兜底）。"""
    for a, b in (
        ("api.zhihu.com/questions/", "www.zhihu.com/question/"),
        ("api.zhihu.com/answers/", "www.zhihu.com/answer/"),
    ):
        if a in u:
            return u.replace(a, b)
    return u


def item_to_doc(platform: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": item.get("url") or "",
        "title": item.get("title") or "",
        "content": item.get("excerpt") or item.get("title") or "",
        "source": platform,
        "author": item.get("author") or "",
        "published_at": item.get("published_at") or "",
        "tags": ["live-smoke", platform],
    }


def report(
    step: str, res: dict[str, Any], dt: float, blocked: set[str], platform: str
) -> None:
    if res.get("ok"):
        items = res.get("items") or []
        emit(step, ok=True, seconds=dt, count=len(items), top=brief(items))
        return
    err = res.get("error") or {}
    emit(step, ok=False, seconds=dt, error=err)
    if err.get("code") in RISK_CODES:
        blocked.add(platform)
        emit("RISK_STOP", platform=platform, error=err)


async def check_login(platform: str) -> None:
    """打开站点登录探测页并检查已登录标记（第一次取页会触发 Chrome 允许弹窗）。"""
    recipe = load_all_recipes()[0][platform]
    spec = recipe.site.login_check
    if spec is None:
        emit(f"login_check_{platform}", ok=False, error="配方未声明 login_check")
        return
    hub = await get_hub()
    t = time.time()
    async with hub.page_lock:
        page = await hub.page(unattended=False)
        await acquire_platform(platform)
        await page.goto(spec.url, wait_until="domcontentloaded", timeout=30000)
        logged = await page.query_selector(spec.logged_in_selector) is not None
    hub.set_cached_login(platform, logged)
    emit(
        f"login_check_{platform}",
        ok=True,
        seconds=round(time.time() - t, 2),
        logged_in=logged,
        backend=hub.backend.name if hub.backend else None,
        reason=hub.backend_reason,
    )


async def run_zhihu(blocked: set[str], collected: list[dict[str, Any]]) -> None:
    await check_login("zhihu")
    res, dt = await timed(tool_social_search("zhihu", "AI Agent", 10))
    report("social_search_zhihu", res, dt, blocked, "zhihu")
    first_url = ""
    if res.get("ok") and res["items"]:
        first_url = next((i["url"] for i in res["items"] if i.get("url")), "")
    if "zhihu" in blocked:
        return
    hot, dt = await timed(tool_social_hot("zhihu", 10))
    report("social_hot_zhihu", hot, dt, blocked, "zhihu")
    if hot.get("ok") and hot["items"]:
        collected.append(item_to_doc("zhihu", hot["items"][0]))
        first_url = first_url or next(
            (i["url"] for i in hot["items"] if i.get("url")), ""
        )
    if "zhihu" in blocked or not first_url:
        return
    target = fix_zhihu_url(first_url)
    rd, dt = await timed(tool_social_read(target, 3000, 0))
    if rd.get("ok"):
        emit(
            "social_read_zhihu",
            ok=True,
            seconds=dt,
            url=rd["url"],
            title=rd["title"],
            author=rd["author"],
            chars=len(rd["content"]),
            truncated=rd["truncated"],
            head=rd["content"][:200],
        )
        collected.append(
            {
                "url": rd["url"],
                "title": rd["title"],
                "content": rd["content"],
                "source": "zhihu",
                "author": rd["author"],
                "published_at": rd["published_at"],
                "tags": ["live-smoke", "zhihu"],
            }
        )
    else:
        emit(
            "social_read_zhihu",
            ok=False,
            seconds=dt,
            target=target,
            error=rd.get("error"),
        )
        if (rd.get("error") or {}).get("code") in RISK_CODES:
            blocked.add("zhihu")


async def run_x(blocked: set[str], collected: list[dict[str, Any]]) -> None:
    res, dt = await timed(tool_social_search("x", "AI agent", 10))
    report("social_search_x", res, dt, blocked, "x")
    if "x" in blocked:
        return
    feed, dt = await timed(tool_social_feed("x", "OpenAI", 5))
    report("social_feed_x", feed, dt, blocked, "x")
    if feed.get("ok") and feed["items"]:
        collected.append(item_to_doc("x", feed["items"][0]))
    elif res.get("ok") and res["items"]:
        collected.append(item_to_doc("x", res["items"][0]))


def save_to_vault(vault_dir: str, collected: list[dict[str, Any]]) -> None:
    if not collected:
        emit("vault_save", ok=False, error="没有可保存的结果")
        return
    mod = load_vault_module()
    res = mod.save_docs(collected[:3], kind="raw", vault_dir=vault_dir)
    emit(
        "vault_save",
        ok=not res["failed"],
        vault=res["vault"],
        saved=res["saved"],
        updated=res["updated"],
        unchanged=res["unchanged"],
        failed=res["failed"],
    )


async def cleanup() -> None:
    """只关闭自建页并断开驱动，不关闭用户 Chrome。"""
    try:
        hub = await get_hub()
        closed = 0
        for pg in list(hub._owned_pages.values()):
            if not pg.is_closed():
                await pg.close()
                closed += 1
        if hub.pw:
            await hub.pw.stop()
        emit("cleanup", closed_owned_pages=closed, disconnected=True)
    except Exception as e:  # noqa: BLE001 - 清理阶段不应掩盖前面的结果
        emit("cleanup", ok=False, error=str(e))


async def main() -> None:
    ap = argparse.ArgumentParser(description="social 真机冒烟（只读、单连接）")
    ap.add_argument("--vault", default=DEFAULT_VAULT, help="冒烟结果写入的资料库目录")
    ap.add_argument("--sites", default="zhihu,x", help="要测的站点，逗号分隔")
    args = ap.parse_args()
    sites = set(args.sites.split(","))
    blocked: set[str] = set()
    collected: list[dict[str, Any]] = []

    plat = await tool_social_platforms()
    emit(
        "platforms",
        ok=plat.get("ok"),
        platforms=[
            {
                "platform": p["platform"],
                "status": p["status"],
                "actions": list(p["actions"]),
                "remaining_hour": p["rate"]["remaining_hour"],
            }
            for p in plat.get("platforms", [])
        ],
        write_only=plat.get("write_only_platforms"),
    )

    try:
        if "zhihu" in sites:
            await run_zhihu(blocked, collected)
        if "x" in sites:
            await run_x(blocked, collected)
        save_to_vault(args.vault, collected)
    finally:
        await cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except HubError as e:
        emit("fatal", error=e.to_dict())

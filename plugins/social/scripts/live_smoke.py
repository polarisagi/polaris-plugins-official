"""browser_use 真机冒烟测试（手工运行，不进 CI）。

警告：本脚本会连接本机日常 Chrome（需已打开 chrome://inspect 远程调试开关），
Chrome 会弹出「允许远程调试」对话框，必须人工点击允许（60 秒内）。
全程只建立一条连接，只在插件自建窗口中做只读操作（打开、搜索、读取、滚动），
不点赞/关注/评论/发帖，不读 cookie，不触碰用户已有标签。

用法（在 plugins/browser_use 目录）：
    POLARIS_BROWSER_BACKEND=cdp uv run --frozen python scripts/live_smoke.py
    ... live_smoke.py --sites zhihu            # 只测某站点
    ... live_smoke.py --diagnose zhihu,x       # 站点失败时额外记录 XHR 清单（同一连接内）
默认：某动作 0 条或出错时自动在同一连接内诊断（每动作多 1 次导航）。
输出：每步一行 JSON 到 stdout；诊断数据写入 /tmp/live_smoke_diag/。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.browser_hub import HubError, get_hub  # noqa: E402
from src.harvest.engine import format_template  # noqa: E402
from src.harvest.loader import load_all_recipes  # noqa: E402
from src.tools_browser import (  # noqa: E402
    tool_browser_open,
    tool_browser_read,
    tool_browser_snapshot,
    tool_browser_status,
)
from src.tools_harvest import _calc_field_rates, tool_harvest  # noqa: E402

DIAG_DIR = Path("/tmp/live_smoke_diag")
RISK_CODES = {"blocked"}


def emit(step: str, **kw: Any) -> None:
    print(json.dumps({"step": step, **kw}, ensure_ascii=False, default=str), flush=True)


def brief(items: list[dict[str, Any]], n: int = 3) -> list[dict[str, str]]:
    return [{"title": (i.get("title") or "")[:80], "url": i.get("url") or ""} for i in items[:n]]


async def timed(coro: Any) -> tuple[Any, float]:
    t = time.time()
    r = await coro
    return r, round(time.time() - t, 2)


async def do_harvest(step: str, site: str, action: str, params: dict[str, Any], n: int) -> dict[str, Any]:
    res, dt = await timed(tool_harvest(site=site, action=action, params=params, max_items=n))
    if res.get("ok"):
        items = res["items"]
        emit(step, ok=True, seconds=dt, count=len(items), top=brief(items),
             fill=_calc_field_rates(items), sample_metrics=(items[0].get("metrics") if items else None))
    else:
        emit(step, ok=False, seconds=dt, error=res.get("error"))
    return res


def skeleton(v: Any, depth: int = 0) -> Any:
    """仅保留键结构，丢弃值，用于诊断输出。"""
    if depth > 6:
        return "..."
    if isinstance(v, dict):
        return {k: skeleton(x, depth + 1) for k, x in list(v.items())[:30]}
    if isinstance(v, list):
        return [skeleton(v[0], depth + 1), f"len={len(v)}"] if v else []
    return type(v).__name__


async def diagnose(site: str, action: str, params: dict[str, Any]) -> None:
    """在自建页上重放配方首个 goto，记录所有 JSON 响应的 URL 与键结构。"""
    recipes, _ = load_all_recipes()
    rec = recipes[site]
    act = rec.actions[action]
    url = next((format_template(s.goto, params, act) for s in act.steps if s.goto), None)
    if not url:
        return
    DIAG_DIR.mkdir(exist_ok=True)
    hub = await get_hub()
    seen: list[dict[str, Any]] = []
    bodies: list[tuple[str, Any]] = []

    async def on_resp(resp: Any) -> None:
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                body = await resp.json()
                seen.append({"url": resp.url[:200], "status": resp.status, "keys": skeleton(body)})
                bodies.append((resp.url, body))
        except Exception as e:  # noqa: BLE001
            seen.append({"url": resp.url[:200], "err": str(e)[:80]})

    async with hub.page_lock:
        page = await hub.page(unattended=False)
        page.on("response", on_resp)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(4)
            for _ in range(2):
                await page.evaluate("window.scrollBy(0, 600)")
                await asyncio.sleep(1.5)
            title = await page.title()
            probe = await page.evaluate(
                """() => ({url: location.href, bodyLen: document.body.innerText.length,
                  head: document.body.innerText.slice(0, 200),
                  testids: [...new Set([...document.querySelectorAll('[data-testid]')].map(e=>e.dataset.testid))].slice(0,40),
                  classes: [...new Set([...document.querySelectorAll('[class]')].flatMap(e=>[...e.classList]).filter(c=>/Search|Card|Hot|Item/.test(c)))].slice(0,40)})"""
            )
        finally:
            page.remove_listener("response", on_resp)
    out = DIAG_DIR / f"{site}_{action}.json"
    out.write_text(json.dumps({"url": url, "title": title, "probe": probe, "json_responses": seen}, ensure_ascii=False, indent=1))
    for i, (u, b) in enumerate(bodies):
        if any(k in u for k in ("search", "hot", "graphql", "feed", "timeline")):
            (DIAG_DIR / f"{site}_{action}_body{i}.json").write_text(json.dumps(b, ensure_ascii=False)[:400000])
    emit(f"diagnose:{site}:{action}", file=str(out), json_urls=[s["url"] for s in seen][:25], probe=probe)


def fix_zhihu_url(u: str) -> str:
    """api.zhihu.com 形式转 Web 形式（仅冒烟脚本兜底）。"""
    for a, b in (("api.zhihu.com/questions/", "www.zhihu.com/question/"), ("api.zhihu.com/answers/", "www.zhihu.com/answer/")):
        if a in u:
            return u.replace(a, b)
    return u


async def read_article(step: str, url: str, max_chars: int) -> None:
    o, dt1 = await timed(tool_browser_open(url))
    if not o.get("ok"):
        emit(step, ok=False, seconds=dt1, error=o.get("error"))
        return
    r, dt2 = await timed(tool_browser_read(mode="article", max_chars=max_chars))
    text = r.get("text") or r.get("content") or ""
    emit(step, ok=r.get("ok"), seconds=round(dt1 + dt2, 2), final_url=o.get("url"), title=o.get("title"),
         chars=len(text), keys=list(r.keys()), head=text[:200], error=r.get("error"))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="zhihu,x")
    ap.add_argument("--diagnose", default="", help="强制诊断的站点，逗号分隔")
    ap.add_argument("--no-auto-diagnose", action="store_true")
    args = ap.parse_args()
    sites = args.sites.split(",")
    force_diag = set(filter(None, args.diagnose.split(",")))
    blocked: set[str] = set()
    failed: list[tuple[str, str, dict[str, Any]]] = []

    def note(site: str, action: str, params: dict[str, Any], res: dict[str, Any]) -> None:
        err = (res.get("error") or {}).get("code")
        if err in RISK_CODES:
            blocked.add(site)
            emit("RISK_STOP", site=site, error=res.get("error"))
        elif not res.get("ok") or res.get("count", 0) == 0:
            failed.append((site, action, params))

    try:
        if "zhihu" in sites:
            # a/b: 连接 + 打开首页 + 读取 + 登录态（第一次取页触发 Chrome 允许弹窗）
            o, dt = await timed(tool_browser_open("https://www.zhihu.com/"))
            emit("b_open_zhihu", ok=o.get("ok"), seconds=dt, url=o.get("url"), title=o.get("title"), error=o.get("error"))
            st = await tool_browser_status()
            emit("a_hub_status", backend=st.get("backend"), reason=st.get("reason"), connected=st.get("connected"),
                 driver=st.get("driver"), owned_tabs=st.get("owned_tabs"))
            if not o.get("ok"):
                return
            r, dt = await timed(tool_browser_read(mode="article", max_chars=2000))
            text = r.get("text") or r.get("content") or ""
            emit("b_read_zhihu_home", ok=r.get("ok"), seconds=dt, chars=len(text), keys=list(r.keys()), head=text[:120], error=r.get("error"))
            recipes, _ = load_all_recipes()
            sel = recipes["zhihu"].site.login_check.logged_in_selector
            hub = await get_hub()
            page = await hub.page()
            logged = await page.query_selector(sel) is not None
            emit("b_login_check_zhihu", logged_in=logged)

            p = {"q": "AI Agent"}
            c = await do_harvest("c_zhihu_search", "zhihu", "search", p, 10)
            note("zhihu", "search", p, c)
            if "zhihu" not in blocked:
                d = await do_harvest("d_zhihu_hot", "zhihu", "hot", {}, 10)
                note("zhihu", "hot", {}, d)
                first = next((i["url"] for i in (c.get("items") or []) if i.get("url")), None) or \
                    next((i["url"] for i in (d.get("items") or []) if i.get("url")), None)
                if first:
                    emit("e_target", raw_url=first, fixed_url=fix_zhihu_url(first))
                    await read_article("e_zhihu_article", fix_zhihu_url(first), 3000)

        if "x" in sites:
            p = {"q": "AI agent", "mode": "latest"}
            f = await do_harvest("f_x_search", "x", "search", p, 10)
            note("x", "search", p, f)
            if "x" not in blocked:
                p = {"handle": "OpenAI"}
                g = await do_harvest("g_x_user_timeline", "x", "user_timeline", p, 5)
                note("x", "user_timeline", p, g)

        # h: 当前页快照
        s, dt = await timed(tool_browser_snapshot(scope="viewport", max_items=30))
        emit("h_snapshot", ok=s.get("ok"), seconds=dt, chars=len(s.get("snapshot", "")), total=s.get("total"),
             displayed=s.get("displayed"), head=s.get("snapshot", "")[:300], error=s.get("error"))

        # 诊断（同一连接）
        todo = [(s_, a, p_) for s_, a, p_ in failed if not args.no_auto_diagnose and s_ not in blocked]
        for s_ in force_diag:
            todo += [(s_, a, p_) for a, p_ in (("search", {"q": "AI Agent"}),)]
        for s_, a, p_ in todo:
            await diagnose(s_, a, p_)
    finally:
        # i: 只关闭自建页，断开驱动，不关闭用户 Chrome
        try:
            hub = await get_hub()
            closed = 0
            for pg in list(hub._owned_pages.values()):
                if not pg.is_closed():
                    await pg.close()
                    closed += 1
            if hub.pw:
                await hub.pw.stop()
            emit("i_cleanup", closed_owned_pages=closed, disconnected=True)
        except Exception as e:  # noqa: BLE001
            emit("i_cleanup", ok=False, error=str(e))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except HubError as e:
        emit("fatal", error=e.to_dict())

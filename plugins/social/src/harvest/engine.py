"""采集执行引擎。

为何需要该模块：
1. 自动化驱动配方中声明的多步流程（goto、wait_for、scroll、click、sleep）；
2. 支持 XHR/Fetch 响应流的智能嗅探拦截与 JSON 提取，大幅降低解析成本；
3. 全自动风控特征监听（状态码、URL、页面文案），一旦命中即时标记 SQLite 熔断；
4. 严格遵从无人值守调用限制与站点频次限速。
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import random
import re
from typing import Any
from urllib.parse import quote

from patchright.async_api import Error as PwError
from patchright.async_api import Page, Response

from ..utils.browser_hub import HubError, get_hub
from ..utils.extract import extract_structured
from ..ratelimit import acquire, mark_blocked
from .normalize import get_dot_path, normalize_items
from .recipe import Action, BlockSignals, CssExtract, Recipe, Step, XhrExtract

logger = logging.getLogger("polaris.harvest.engine")
PARAM_RE = re.compile(r"\{([a-zA-Z0-9_]+)(?:\|([a-zA-Z0-9_]+))?\}")


def format_template(template: str, params: dict[str, Any], action: Action) -> str:
    """对 URL 模板进行参数插值并应用指定过滤器（urlencode 或 json）。"""

    def repl(match: re.Match[str]) -> str:
        param_name = match.group(1)
        filter_name = match.group(2)

        val = params.get(param_name)
        if val is None and param_name in action.params:
            val = action.params[param_name].default

        if val is None:
            return ""

        if filter_name == "urlencode":
            return quote(str(val))
        if filter_name == "json":
            return json.dumps(val)
        return str(val)

    return PARAM_RE.sub(repl, template)


async def check_block_signals(
    page: Page,
    response: Response | None,
    signals: BlockSignals,
    site_id: str,
) -> None:
    """检查是否命中风控拦截特征。"""
    if response and signals.status and response.status in signals.status:
        mark_blocked(site_id, f"命中风控 HTTP 状态码: {response.status}")
        raise HubError(
            "blocked", f"目标站点 {site_id} 返回风控状态码 {response.status}"
        )

    curr_url = page.url
    for sub in signals.url_contains:
        if sub in curr_url:
            mark_blocked(site_id, f"URL 命中风控特征: {sub}")
            raise HubError(
                "blocked", f"目标站点 {site_id} 命中风控重定向 URL: {curr_url}"
            )

    if signals.text_contains:
        try:
            body_text = await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
            for sub in signals.text_contains:
                if sub in body_text:
                    mark_blocked(site_id, f"页面内容命中风控提示: {sub}")
                    raise HubError(
                        "blocked", f"目标站点 {site_id} 页面显示风控文案: {sub}"
                    )
        except (PwError, OSError):
            pass


async def execute_step(
    page: Page,
    step: Step,
    params: dict[str, Any],
    action: Action,
    signals: BlockSignals,
    site_id: str,
) -> None:
    """执行单个原子动作步骤。"""
    if step.goto:
        url = format_template(step.goto, params, action)
        resp = await page.goto(
            url, wait_until="domcontentloaded", timeout=int(step.timeout_s * 1000)
        )
        await check_block_signals(page, resp, signals, site_id)

    if step.wait_for:
        await page.wait_for_selector(step.wait_for, timeout=int(step.timeout_s * 1000))

    if step.scroll:
        delta = 600 if step.scroll.direction == "down" else -600
        for _ in range(step.scroll.times):
            await page.evaluate(f"window.scrollBy(0, {delta});")
            await asyncio.sleep(0.2)

    if step.click:
        await page.click(step.click, timeout=int(step.timeout_s * 1000))

    if step.sleep:
        low, high = step.sleep
        delay = random.uniform(low, high)
        await asyncio.sleep(delay)


async def _check_login_state(
    hub: Any, page: Page, site_id: str, check_spec: Any
) -> None:
    """探测并缓存当前站点的登录态。"""
    cached_login = hub._cached_site_logins.get(site_id)
    if cached_login is not None:
        return
    try:
        el = await page.query_selector(check_spec.logged_in_selector)
        logged_in = el is not None
        hub.set_cached_login(site_id, logged_in)
        if not logged_in:
            raise HubError(
                "not_logged_in",
                f"站点 {site_id} 尚未处于已登录状态，请先在 Chrome 中登录该平台",
            )
    except HubError:
        raise
    except (PwError, OSError) as e:
        logger.debug("探测登录态异常: %s", e)


def _extract_xhr_items(
    captured_json: list[Any], xhr_spec: XhrExtract
) -> list[dict[str, Any]]:
    """从拦截到的 JSON 数据流中按点路径抽取结构化字段。"""
    items: list[dict[str, Any]] = []
    for payload in captured_json:
        matched_list = get_dot_path(payload, xhr_spec.items)
        if isinstance(matched_list, list):
            for raw in matched_list:
                item: dict[str, Any] = {}
                for k, dot_path in xhr_spec.fields.items():
                    item[k] = get_dot_path(raw, dot_path)
                items.append(item)
    return items


async def _extract_content(
    page: Page, action: Action, captured_json: list[Any], max_items: int
) -> tuple[list[dict[str, Any]], str]:
    """按配方首选方案与备用降级方案抽取数据列表。"""
    raw_items: list[dict[str, Any]] = []
    method_used = "xhr" if isinstance(action.extract, XhrExtract) else "css"
    if isinstance(action.extract, XhrExtract):
        if not captured_json:
            await asyncio.sleep(1.0)
        raw_items = _extract_xhr_items(captured_json, action.extract)
    elif isinstance(action.extract, CssExtract):
        css_spec: CssExtract = action.extract
        extracted = await extract_structured(
            page,
            container=css_spec.container,
            fields=css_spec.fields,
            max_items=max_items,
        )
        raw_items = extracted.get("items", [])

    if not raw_items and action.extract_fallback:
        logger.info("首选提取结果为空，启动 CSS 降级方案")
        fb_spec = action.extract_fallback
        extracted = await extract_structured(
            page,
            container=fb_spec.container,
            fields=fb_spec.fields,
            max_items=max_items,
        )
        raw_items = extracted.get("items", [])
        if raw_items:
            method_used = "css"
    return raw_items, method_used


async def run_harvest(
    recipe: Recipe,
    action_name: str,
    params: dict[str, Any] | None = None,
    max_items: int = 20,
    return_method: bool = False,
) -> Any:
    """核心入口：根据配方与动作执行全流程数据采集。"""
    action = recipe.actions.get(action_name)
    if not action:
        raise HubError(
            "invalid_args", f"站点 {recipe.site.id} 不支持动作 '{action_name}'"
        )

    call_params = params or {}
    site_id = recipe.site.id

    # 1. 先在页面锁内取页（可能抛 needs_user_approval，此时不应消耗限速名额）
    hub = await get_hub()
    await hub.page_lock.acquire()
    try:
        page = await hub.page(unattended=True)
        # 2. 取页成功后再占用站点频次与风控名额
        await acquire(site_id, recipe.limits)
    except BaseException:
        hub.page_lock.release()
        raise

    captured_json: list[Any] = []

    # 3. 若为 XHR 模式，注册响应拦截监听器
    async def on_response(resp: Response) -> None:
        try:
            if isinstance(action.extract, XhrExtract) and fnmatch.fnmatch(
                resp.url, action.extract.url_glob
            ):
                ct = resp.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    body = await resp.json()
                    captured_json.append(body)
        except (PwError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("解析拦截响应异常: %s", e)

    is_xhr = isinstance(action.extract, XhrExtract)

    try:
        if is_xhr:
            page.on("response", on_response)

        # 4. 依次执行各个动作步骤
        for step in action.steps:
            await execute_step(
                page, step, call_params, action, recipe.block_signals, site_id
            )

        # 5. 登录检查
        if recipe.site.login_check:
            await _check_login_state(hub, page, site_id, recipe.site.login_check)

        # 6. 数据提取与格式标准化
        raw_items, method_used = await _extract_content(
            page, action, captured_json, max_items
        )
        normalized = normalize_items(raw_items, site_id, recipe.site.base_url)
        res = normalized[:max_items]
        if return_method:
            return res, method_used
        return res

    finally:
        if is_xhr:
            page.remove_listener("response", on_response)
        hub.page_lock.release()

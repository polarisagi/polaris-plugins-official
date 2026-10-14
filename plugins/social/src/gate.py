"""读写共享限速闸门与平台键映射。

为何需要该模块：
1. 读取（搜索 / 热榜 / 动态 / 正文）与发帖、互动使用的是同一个账号，限速必须按「平台」
   这一把键统一计数，否则一边采集一边发帖时频率叠加、风控特征也要维护两份；
2. 配方站点沿用配方的 [limits]；没有配方的平台（instagram 等）使用保守默认值；
3. 写工具通过装饰器在统一入口调用 ratelimit.acquire，被限速时返回错误码而不是执行，
   适配器代码无需任何改动。
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec
from urllib.parse import urlparse

from .harvest.loader import load_all_recipes
from .ratelimit import Limits, acquire
from .utils.browser_hub import HubError

P = ParamSpec("P")

# 无配方平台的保守默认限速：间隔 10 秒、每小时 20 次、每天 60 次，全天可用
DEFAULT_LIMITS = Limits(
    min_interval_s=10.0,
    jitter_s=(0.5, 1.5),
    max_per_hour=20,
    max_per_day=60,
    active_hours="00:00-24:00",
    cooldown_on_block_h=6.0,
)

# 未知域名使用的限速键
FALLBACK_KEY = "web"

# 写工具里的平台名 -> 限速键（配方站点 id）
PLATFORM_ALIASES: dict[str, str] = {"twitter": "x"}

# 写适配器支持的平台（与 main.SUPPORTED_PLATFORMS 一致）
WRITE_PLATFORMS: tuple[str, ...] = (
    "twitter",
    "instagram",
    "facebook",
    "weibo",
    "xiaohongshu",
    "douyin",
    "wechat",
    "tiktok",
    "linkedin",
    "threads",
)

# URL 域名后缀 -> 限速键
DOMAIN_PLATFORMS: tuple[tuple[str, str], ...] = (
    ("zhihu.com", "zhihu"),
    ("x.com", "x"),
    ("twitter.com", "x"),
    ("weibo.com", "weibo"),
    ("weibo.cn", "weibo"),
    ("xiaohongshu.com", "xiaohongshu"),
    ("xhslink.com", "xiaohongshu"),
    ("instagram.com", "instagram"),
    ("facebook.com", "facebook"),
    ("douyin.com", "douyin"),
    ("mp.weixin.qq.com", "wechat"),
    ("tiktok.com", "tiktok"),
    ("linkedin.com", "linkedin"),
    ("threads.net", "threads"),
    ("threads.com", "threads"),
)


def rate_key(platform: str) -> str:
    """把工具里的平台名规范化为限速键（twitter -> x）。"""
    p = platform.strip().lower()
    return PLATFORM_ALIASES.get(p, p)


def platform_for_url(url: str) -> str:
    """按 URL 域名映射到平台限速键；未知域名返回 FALLBACK_KEY。"""
    host = (urlparse(url).hostname or "").lower()
    for suffix, key in DOMAIN_PLATFORMS:
        if host == suffix or host.endswith("." + suffix):
            return key
    return FALLBACK_KEY


def limits_for(key: str) -> Limits:
    """取平台限速：有配方用配方的 [limits]，否则用保守默认值。"""
    recipes, _ = load_all_recipes()
    recipe = recipes.get(key)
    return recipe.limits if recipe else DEFAULT_LIMITS


async def acquire_platform(platform: str) -> None:
    """占用该平台一个限速名额；被限速或处于熔断冷却期时抛出 HubError。"""
    key = rate_key(platform)
    await acquire(key, limits_for(key))


def error_result(err: HubError) -> dict[str, Any]:
    """HubError -> 统一错误返回。"""
    return {"ok": False, "error": err.to_dict()}


def rate_limited_write(
    fn: Callable[P, Awaitable[Any]],
) -> Callable[P, Awaitable[Any]]:
    """写工具装饰器：执行前先占用平台限速名额，被限速时返回错误码而不执行。

    只对已知写平台生效；未知平台透传，由工具自身返回「不支持」提示。
    被装饰函数必须有名为 platform 的参数。
    """
    sig = inspect.signature(fn)
    if "platform" not in sig.parameters:
        raise TypeError(f"{fn.__name__} 缺少 platform 参数，无法接入限速闸门")

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        platform = sig.bind_partial(*args, **kwargs).arguments.get("platform")
        if isinstance(platform, str) and platform.strip().lower() in WRITE_PLATFORMS:
            try:
                await acquire_platform(platform)
            except HubError as e:
                return error_result(e)
        return await fn(*args, **kwargs)

    return wrapper

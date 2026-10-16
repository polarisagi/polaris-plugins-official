"""读写共享限速闸门单元测试（全部离线，限速库使用临时目录）。

验证内容：
1. 平台别名与 URL 域名到限速键的映射；
2. 有配方平台沿用配方 [limits]，无配方平台与未知域名使用保守默认值；
3. 写工具装饰器：限速通过时执行、被限速时返回错误码而不执行、读写计入同一把键；
4. 未知平台透传给工具本身处理。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from src import gate, ratelimit
from src.utils.browser_hub import HubError


@pytest.fixture(autouse=True)
def _tmp_ratelimit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "ratelimit.db"
    monkeypatch.setattr(ratelimit, "get_db_path", lambda: db)
    return db


def test_rate_key_alias() -> None:
    assert gate.rate_key("twitter") == "x"
    assert gate.rate_key(" Twitter ") == "x"
    assert gate.rate_key("weibo") == "weibo"


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://www.zhihu.com/question/1", "zhihu"),
        ("https://zhuanlan.zhihu.com/p/1", "zhihu"),
        ("https://x.com/OpenAI/status/1", "x"),
        ("https://twitter.com/OpenAI/status/1", "x"),
        ("https://weibo.com/1/abc", "weibo"),
        ("https://m.weibo.cn/detail/1", "weibo"),
        ("https://www.xiaohongshu.com/explore/1", "xiaohongshu"),
        ("https://mp.weixin.qq.com/s/abc", "wechat"),
        ("https://example.com/a", "web"),
        # 后缀必须按域名边界匹配，不能被 notx.com 之类蒙混
        ("https://notx.com/a", "web"),
        ("https://x.com.evil.example/a", "web"),
    ],
)
def test_platform_for_url(url: str, key: str) -> None:
    assert gate.platform_for_url(url) == key


def test_limits_for_recipe_and_default() -> None:
    zhihu = gate.limits_for("zhihu")
    assert zhihu.min_interval_s == 4.0
    assert zhihu.max_per_hour == 60

    for key in ("instagram", "web", "linkedin"):
        lim = gate.limits_for(key)
        assert lim.min_interval_s == 10.0
        assert lim.max_per_hour == 20
        assert lim.max_per_day == 60


async def test_decorator_executes_when_quota_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquired: list[str] = []

    async def fake_acquire(site: str, _limits: object) -> None:
        acquired.append(site)

    monkeypatch.setattr(gate, "acquire", fake_acquire)

    @gate.rate_limited_write
    async def tool(platform: str, content: str) -> str:
        return f"posted {platform}:{content}"

    assert await tool("twitter", "hi") == "posted twitter:hi"
    assert await tool(platform="weibo", content="yo") == "posted weibo:yo"
    # twitter 与读工具的 x 共用同一把键
    assert acquired == ["x", "weibo"]


async def test_decorator_returns_error_without_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def deny(_site: str, _limits: object) -> None:
        raise HubError("rate_limited", "达到每小时请求上限")

    monkeypatch.setattr(gate, "acquire", deny)
    ran: list[str] = []

    @gate.rate_limited_write
    async def tool(platform: str) -> str:
        ran.append(platform)
        return "ok"

    res: Any = await tool("instagram")
    assert res["ok"] is False
    assert res["error"]["code"] == "rate_limited"
    assert ran == []


async def test_decorator_passthrough_for_unknown_platform() -> None:
    @gate.rate_limited_write
    async def tool(platform: str) -> str:
        return f"unsupported {platform}"

    assert await tool("myspace") == "unsupported myspace"


async def test_read_and_write_share_one_bucket() -> None:
    """真实限速库：写入占满 x 的每小时配额后，读取同一平台被拒绝。"""
    limits = ratelimit.Limits(
        min_interval_s=0.0,
        jitter_s=(0.0, 0.0),
        max_per_hour=2,
        max_per_day=10,
        active_hours="00:00-24:00",  # 与时段无关，避免夜间运行时被时段规则先拦截
    )
    await ratelimit.acquire("x", limits)
    await ratelimit.acquire(gate.rate_key("twitter"), limits)
    with pytest.raises(HubError) as ei:
        await ratelimit.acquire(
            gate.platform_for_url("https://x.com/a/status/1"), limits
        )
    assert ei.value.code == "rate_limited"


def test_decorator_requires_platform_param() -> None:
    with pytest.raises(TypeError):

        @gate.rate_limited_write
        async def bad(content: str) -> str:
            return content

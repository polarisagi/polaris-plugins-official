"""旧适配器读工具：只读标注、共享限速闸门（限速拒绝不调用适配器，正常才调用）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Self

import pytest
from src import gate, main, ratelimit, tools_social
from src.utils.browser_hub import HubError

LEGACY_READS = [
    "get_my_posts",
    "get_comments",
    "search_posts",
    "read_post",
    "get_trending_topics",
    "get_user_profile",
    "get_post_analytics",
    "get_account_analytics",
    "get_notifications",
    "get_mentions",
]


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def search_posts(self, query: str) -> list[dict[str, str]]:
        self.calls.append(("search_posts", (query,)))
        return [{"url": "https://x.com/a/status/1", "snippet": query}]

    async def read_post(self, ident: str) -> str:
        self.calls.append(("read_post", (ident,)))
        return "full text"

    async def get_user_profile(self, username: str) -> dict[str, Any]:
        self.calls.append(("get_user_profile", (username,)))
        return {"name": username}


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeAdapter:
    monkeypatch.setattr(ratelimit, "get_db_path", lambda: tmp_path / "rl.db")
    fake = FakeAdapter()

    async def fake_get_adapter(_platform: str) -> FakeAdapter:
        return fake

    monkeypatch.setattr(main, "_get_adapter", fake_get_adapter)
    return fake


def _acquire_stub(monkeypatch: pytest.MonkeyPatch, deny: bool) -> list[str]:
    seen: list[str] = []

    async def fake(site: str, _limits: object) -> None:
        seen.append(site)
        if deny:
            raise HubError("rate_limited", "达到每小时请求上限")

    monkeypatch.setattr(gate, "acquire", fake)
    return seen


async def test_allowed_calls_adapter_and_keeps_return_shape(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _acquire_stub(monkeypatch, deny=False)
    assert await main.search_posts("twitter", "q") == [
        {"url": "https://x.com/a/status/1", "snippet": "q"}
    ]
    assert await main.read_post("twitter", "id") == "full text"
    assert await main.get_user_profile("weibo", "bob") == {"name": "bob"}
    assert seen == ["x", "x", "weibo"]  # twitter 与读侧 x 同键
    assert [c[0] for c in adapter.calls] == [
        "search_posts",
        "read_post",
        "get_user_profile",
    ]


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("search_posts", ("twitter", "q")),
        ("read_post", ("xiaohongshu", "id")),
        ("get_user_profile", ("weibo", "bob")),
    ],
)
async def test_denied_returns_error_and_skips_adapter(
    adapter: FakeAdapter,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    args: tuple[str, ...],
) -> None:
    _acquire_stub(monkeypatch, deny=True)
    res = await getattr(main, name)(*args)
    assert res["ok"] is False
    assert res["error"]["code"] == "rate_limited"
    assert adapter.calls == []


async def test_unknown_platform_passes_through(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _acquire_stub(monkeypatch, deny=True)
    # 未知平台不占名额，交给原工具返回「不支持」
    res = await main.read_post("myspace", "id")
    assert seen == []
    assert res == "full text"  # fake 适配器不区分平台，仅验证透传


async def test_real_shared_bucket_blocks_reads_after_writes(
    adapter: FakeAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    limits = ratelimit.Limits(
        min_interval_s=0.0,
        jitter_s=(0.0, 0.0),
        max_per_hour=1,
        max_per_day=5,
        active_hours="00:00-24:00",  # 与时段无关，避免夜间运行时被时段规则先拦截
    )
    monkeypatch.setattr(gate, "limits_for", lambda _k: limits)
    await ratelimit.acquire("x", limits)  # 模拟一次写入已占满配额
    res = await main.search_posts("twitter", "q")
    assert res["error"]["code"] == "rate_limited"
    assert adapter.calls == []


def test_annotations_and_descriptions() -> None:
    tools = {t.name: t for t in asyncio.run(main.mcp.list_tools())}
    for name in [*LEGACY_READS, "search_free_image"]:
        ann = tools[name].annotations
        assert ann is not None, name
        assert ann.readOnlyHint is True and ann.openWorldHint is True, name
    assert "social_search" in (tools["search_posts"].description or "")
    assert "social_read" in (tools["read_post"].description or "")
    assert "social_hot" in (tools["get_trending_topics"].description or "")


async def test_search_free_image_has_timeouts_and_https_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(ValueError):
        tools_social.download_image("http://example.com/a.jpg", str(tmp_path / "a.jpg"))

    captured: dict[str, Any] = {}

    class Resp:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def read(self, _n: int) -> bytes:
            return b"img"

    def fake_urlopen(_req: object, timeout: float) -> Resp:
        captured["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(tools_social.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "ok.jpg"
    tools_social.download_image("https://images.pexels.com/a.jpg", str(dest))
    assert dest.read_bytes() == b"img"
    assert captured["timeout"] == tools_social.IMAGE_TIMEOUT_S

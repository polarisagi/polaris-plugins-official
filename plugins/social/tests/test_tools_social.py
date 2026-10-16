"""social_* 读工具单元测试（全部使用假对象，不连接真实 Chrome、不访问任何网站）。

验证内容：
1. 工具签名里的平台枚举与内置配方站点一致；
2. 配方缺动作时返回 unsupported_action，参数缺失返回 invalid_args；
3. 动作映射：search -> q、hot -> 无参、feed -> user_timeline.handle；
4. extract_article 正文 / 元信息抽取与 social_read 分页、限速键、取页失败不占名额；
5. 工具注册：读工具 readOnlyHint=True，写工具 readOnlyHint=False 且 destructiveHint=True。
"""

from __future__ import annotations

import asyncio
import typing
from pathlib import Path
from typing import Any

import pytest
from src import main, ratelimit, tools_social
from src.harvest.loader import get_builtin_recipes_dir, load_all_recipes
from src.utils.browser_hub import HubError


@pytest.fixture(autouse=True)
def _tmp_ratelimit_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "ratelimit.db"
    monkeypatch.setattr(ratelimit, "get_db_path", lambda: db)


def test_platform_literal_matches_builtin_recipes() -> None:
    builtin = {
        p.stem
        for p in get_builtin_recipes_dir().glob("*.toml")
        if not p.name.startswith("_")
    }
    assert set(typing.get_args(main.ReadPlatform)) == builtin


async def test_unsupported_action_error() -> None:
    res = await tools_social.tool_social_hot("x", 5)
    assert res["ok"] is False
    assert res["error"]["code"] == "unsupported_action"

    res = await tools_social.tool_social_feed("zhihu", "someone", 5)
    assert res["error"]["code"] == "unsupported_action"

    res = await tools_social.tool_social_search("zhihu", "   ", 5)
    assert res["error"]["code"] == "invalid_args"

    # handle 为空且平台没有关注流（following）时才报参数错误
    res = await tools_social.tool_social_feed("zhihu", "  @ ", 5)
    assert res["error"]["code"] == "invalid_args"


async def test_action_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any], int]] = []

    async def fake_harvest(
        site: str,
        action: str,
        params: dict[str, Any] | None = None,
        max_items: int = 20,
    ) -> dict[str, Any]:
        calls.append((site, action, params or {}, max_items))
        return {"ok": True, "items": [{"title": "t"}], "count": 1}

    monkeypatch.setattr(tools_social, "tool_harvest", fake_harvest)

    r = await tools_social.tool_social_search("zhihu", " AI Agent ", 7)
    assert r == {
        "ok": True,
        "platform": "zhihu",
        "action": "search",
        "items": [{"title": "t"}],
        "count": 1,
    }
    await tools_social.tool_social_hot("weibo", 3)
    await tools_social.tool_social_feed("x", "@OpenAI", 4)
    await tools_social.tool_social_feed("x", "", 6)
    assert calls == [
        ("zhihu", "search", {"q": "AI Agent"}, 7),
        ("weibo", "hot", {}, 3),
        ("x", "user_timeline", {"handle": "OpenAI"}, 4),
        ("x", "following", {}, 6),
    ]


ARTICLE_HTML = """<html><head><title>如何构建 Agent</title>
<meta name="author" content="张三">
<meta property="article:published_time" content="2026-10-01T08:00:00Z">
</head><body><nav>menu</nav><article><h1>如何构建 Agent</h1>
<p>这是一篇关于智能体系统架构的长文，包含足够多的正文内容以便抽取器识别。</p>
<p>第二段继续讨论工具调用、记忆与评估，并给出一些工程上的实践建议和注意事项。</p>
<p>第三段讨论限速、风控与合规，强调读写共用同一个账号的频率预算管理。</p>
</article><footer>copyright</footer></body></html>"""


def test_extract_article() -> None:
    art = tools_social.extract_article(ARTICLE_HTML, "https://example.com/a")
    assert "智能体系统架构" in art["content"]
    assert "menu" not in art["content"]
    assert art["title"] == "如何构建 Agent"
    assert art["author"] == "张三"
    assert art["published_at"].startswith("2026-10-01")


class FakePage:
    def __init__(self, html: str, url: str) -> None:
        self._html = html
        self.url = url
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **_kw: Any) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_load_state(self, *_a: Any, **_kw: Any) -> None:
        return None

    async def content(self) -> str:
        return self._html

    async def title(self) -> str:
        return "fallback-title"

    async def evaluate(self, *_a: Any, **_kw: Any) -> str:
        return ""


class FakeHub:
    def __init__(self, page: FakePage | None, err: HubError | None = None) -> None:
        self.page_lock = asyncio.Lock()
        self._page = page
        self._err = err

    async def page(self, *, unattended: bool = False) -> FakePage:
        assert unattended is True
        if self._err:
            raise self._err
        assert self._page is not None
        return self._page


async def test_social_read_paginates_and_uses_domain_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = FakePage(ARTICLE_HTML, "about:blank")
    hub = FakeHub(page)
    acquired: list[str] = []

    async def fake_get_hub() -> FakeHub:
        return hub

    async def fake_acquire(site: str, _limits: object) -> None:
        acquired.append(site)

    monkeypatch.setattr(tools_social, "get_hub", fake_get_hub)
    monkeypatch.setattr(tools_social, "acquire", fake_acquire)

    url = "https://www.zhihu.com/question/1/answer/2"
    res = await tools_social.tool_social_read(url, 30, 0)
    assert res["ok"] is True
    assert res["platform"] == "zhihu"
    assert res["url"] == url
    assert res["title"] == "如何构建 Agent"
    assert res["author"] == "张三"
    assert len(res["content"]) == 30
    assert res["truncated"] is True
    assert res["next_offset"] == 30
    assert len(res["content_hash"]) == 16
    assert acquired == ["zhihu"]
    assert not hub.page_lock.locked()

    res2 = await tools_social.tool_social_read(url, 30, res["next_offset"])
    assert res2["content"] != res["content"]
    assert acquired == ["zhihu", "zhihu"]


async def test_social_read_unknown_domain_uses_default_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hub = FakeHub(FakePage(ARTICLE_HTML, "about:blank"))
    seen: list[tuple[str, Any]] = []

    async def fake_get_hub() -> FakeHub:
        return hub

    async def fake_acquire(site: str, limits: Any) -> None:
        seen.append((site, limits.max_per_hour))

    monkeypatch.setattr(tools_social, "get_hub", fake_get_hub)
    monkeypatch.setattr(tools_social, "acquire", fake_acquire)
    res = await tools_social.tool_social_read("https://example.com/post", 8000, 0)
    assert res["ok"] is True
    assert seen == [("web", 20)]


async def test_social_read_rejects_bad_url_and_page_failure_keeps_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = await tools_social.tool_social_read("file:///etc/passwd", 8000, 0)
    assert bad["error"]["code"] == "invalid_args"

    hub = FakeHub(None, err=HubError("needs_user_approval", "需要授权"))
    acquired: list[str] = []

    async def fake_get_hub() -> FakeHub:
        return hub

    async def fake_acquire(site: str, _limits: object) -> None:
        acquired.append(site)

    monkeypatch.setattr(tools_social, "get_hub", fake_get_hub)
    monkeypatch.setattr(tools_social, "acquire", fake_acquire)
    res = await tools_social.tool_social_read("https://x.com/a/status/1", 8000, 0)
    assert res["error"]["code"] == "needs_user_approval"
    assert acquired == []
    assert not hub.page_lock.locked()


async def test_social_platforms_lists_recipes(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = FakeHub(None)
    hub.get_cached_site_statuses = lambda: [{"site": "zhihu", "logged_in": True}]  # type: ignore[attr-defined]

    async def fake_get_hub() -> FakeHub:
        return hub

    monkeypatch.setattr(tools_social, "get_hub", fake_get_hub)
    res = await tools_social.tool_social_platforms()
    assert res["ok"] is True
    by_id = {p["platform"]: p for p in res["platforms"]}
    assert {"zhihu", "x", "weibo", "xiaohongshu"} <= set(by_id)
    assert by_id["zhihu"]["logged_in"] is True
    assert by_id["x"]["logged_in"] is None
    assert by_id["x"]["status"] == "beta"
    assert "user_timeline" in by_id["x"]["actions"]
    assert by_id["zhihu"]["rate"]["remaining_hour"] == 60
    assert "instagram" in res["write_only_platforms"]
    assert "twitter" not in res["write_only_platforms"]
    assert load_all_recipes()[0]  # 配方可加载


def _tools() -> dict[str, Any]:
    return {t.name: t for t in asyncio.run(main.mcp.list_tools())}


def test_tool_annotations() -> None:
    tools = _tools()
    reads = {
        "social_platforms",
        "social_search",
        "social_hot",
        "social_feed",
        "social_read",
        "social_selftest",
    }
    for name in reads:
        ann = tools[name].annotations
        assert ann is not None
        assert ann.readOnlyHint is True
        assert ann.openWorldHint is True

    writes = {
        "auto_post",
        "batch_post",
        "post_video",
        "post_story",
        "post_thread",
        "schedule_post",
        "delete_post",
        "edit_post",
        "like_post",
        "send_dm",
        "follow_user",
        "run_scheduled_posts",
    }
    for name in writes:
        ann = tools[name].annotations
        assert ann is not None, name
        assert ann.readOnlyHint is False, name
        assert ann.destructiveHint is True, name


def test_read_tool_schema_is_strict() -> None:
    tools = _tools()
    schema = tools["social_search"].inputSchema
    assert schema["required"] == ["platform", "query"]
    assert set(schema["properties"]["platform"]["enum"]) == {
        "zhihu",
        "x",
        "weibo",
        "xiaohongshu",
    }
    assert schema["properties"]["max_items"]["maximum"] == 100
    assert "platform" in tools["social_feed"].inputSchema["required"]

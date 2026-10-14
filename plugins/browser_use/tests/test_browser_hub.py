"""BrowserHub 自建页创建、锁重入与隔离性测试（全部使用假对象，不连接真实 Chrome）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from src import browser_hub as bh
from src.browser_hub import BrowserHub, HubError


class FakePage:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self._closed = False
        self.context: Any = None
        self.goto_calls: list[str] = []

    def is_closed(self) -> bool:
        return self._closed

    async def goto(self, url: str, **_kw: Any) -> None:
        self.goto_calls.append(url)
        self.url = url


class UserPage(FakePage):
    """用户日常标签：任何 CDP 会话请求都视为隐私越界。"""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.cdp_sessions = 0


class FakeContext:
    def __init__(self) -> None:
        self.pages: list[FakePage] = []
        self.user_cdp_sessions = 0

    async def new_cdp_session(self, _page: Any) -> Any:
        self.user_cdp_sessions += 1
        raise AssertionError("不应对任何页面开 CDP 会话")


class FakeCdp:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser

    async def send(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert method == "Target.createTarget"
        self.browser.create_params.append(params)
        page = FakePage(params["url"])
        page.context = self.browser.ctx
        self.browser.ctx.pages.append(page)
        return {"targetId": "T-OWNED"}

    async def detach(self) -> None:
        return None


class FakeBrowser:
    def __init__(self) -> None:
        self.ctx = FakeContext()
        self.contexts = [self.ctx]
        self.create_params: list[dict[str, Any]] = []

    def is_connected(self) -> bool:
        return True

    async def new_browser_cdp_session(self) -> FakeCdp:
        return FakeCdp(self)


class FakeBackend:
    def __init__(self, name: str, unattended: bool = True) -> None:
        self.name = name
        self._unattended = unattended

    def unattended_ok(self) -> bool:
        return self._unattended


def _hub(name: str) -> tuple[BrowserHub, FakeBrowser]:
    hub = BrowserHub()
    browser = FakeBrowser()
    hub.backend = FakeBackend(name)  # type: ignore[assignment]
    hub.browser = browser  # type: ignore[assignment]
    return hub, browser


async def test_new_owned_page_extension_no_deadlock() -> None:
    hub, browser = _hub("extension")
    tab = FakePage("about:blank")
    tab.context = FakeContext()
    # 扩展后端的单标签 CDP 会话由假会话承接
    sess = type(
        "S",
        (),
        {
            "send": staticmethod(
                lambda *_a, **_k: _coro({"targetInfo": {"targetId": "ext-1"}})
            ),
            "detach": staticmethod(lambda: _coro(None)),
        },
    )
    tab.context.new_cdp_session = lambda _p: _coro(sess)  # type: ignore[method-assign]
    browser.ctx.pages.append(tab)
    page = await asyncio.wait_for(hub.new_owned_page("https://example.com"), 2.0)
    assert page is tab
    assert tab.goto_calls == ["https://example.com"]


async def _coro(v: Any) -> Any:
    return v


async def test_create_owned_page_uses_marker_and_background() -> None:
    hub, browser = _hub("cdp")
    user = UserPage("https://mail.example.com/inbox")
    user.context = browser.ctx
    browser.ctx.pages.append(user)

    page = await asyncio.wait_for(hub.new_owned_page("https://example.com"), 2.0)

    params = browser.create_params[0]
    assert params["background"] is True
    assert params["newWindow"] is True
    assert params["url"].startswith("about:blank#polaris-")
    assert page is not user
    assert page.goto_calls == ["https://example.com"]  # type: ignore[attr-defined]
    # 全程不对任何页面开 CDP 会话（含用户标签）
    assert browser.ctx.user_cdp_sessions == 0
    assert await hub.owned_pages() == [page]


async def test_owned_pages_excludes_user_tabs_and_closed() -> None:
    hub, browser = _hub("cdp")
    user = UserPage("https://bank.example.com")
    user.context = browser.ctx
    browser.ctx.pages.append(user)
    p1 = await hub.new_owned_page()
    assert await hub.owned_pages() == [p1]
    p1._closed = True  # type: ignore[attr-defined]
    assert await hub.owned_pages() == []
    assert browser.ctx.user_cdp_sessions == 0


async def test_page_unattended_refused_without_connect() -> None:
    hub = BrowserHub()
    hub.backend = FakeBackend("cdp", unattended=False)  # type: ignore[assignment]
    with pytest.raises(HubError) as ei:
        await hub.page(unattended=True)
    assert ei.value.code == "needs_user_approval"


def test_module_has_no_target_id_scan() -> None:
    assert not hasattr(bh.BrowserHub, "_find_page_by_target_id")


def test_fallback_ws_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """端口文件不可读时，环境变量优先作为兜底调试端点。"""
    monkeypatch.setenv("POLARIS_BROWSER_CDP_URL", "ws://127.0.0.1:1/devtools/browser/x")
    assert bh.fallback_ws_url() == "ws://127.0.0.1:1/devtools/browser/x"


def test_fallback_ws_url_none_when_port_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """无环境变量且 9222 未监听时返回 None。"""
    monkeypatch.delenv("POLARIS_BROWSER_CDP_URL", raising=False)
    monkeypatch.setattr(bh, "DEFAULT_TOGGLE_PORT", 1)
    assert bh.fallback_ws_url() is None

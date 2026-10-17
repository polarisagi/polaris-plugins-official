"""MCP 服务器：工具元数据（MCP Apps visibility / resourceUri）、卡片资源与工具调用。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from src import main, setup_ops
from src.paths import BridgePaths


@pytest.fixture
def tmp_paths(tmp_path: Path, monkeypatch) -> BridgePaths:
    p = BridgePaths(
        cfg=tmp_path / "cfg",
        home=tmp_path,
        chrome_hosts_dir=tmp_path / "hosts",
    )
    monkeypatch.setattr(main, "_paths", lambda: p)
    monkeypatch.setattr(setup_ops.sys, "executable", sys.executable)
    return p


async def test_tools_declare_ui_meta():
    tools = {t.name: t for t in await main.mcp.list_tools()}
    assert set(tools) == {
        "bridge_setup",
        "bridge_open_chrome_extensions",
        "bridge_status",
        "bridge_rotate_token",
    }
    assert tools["bridge_setup"].meta["ui"]["resourceUri"] == main.SETUP_CARD_URI
    for t in tools.values():
        assert "app" in t.meta["ui"]["visibility"], f"{t.name} 卡片按钮必须可调用"


async def test_card_resource_mime_and_content():
    res = await main.mcp.list_resources()
    assert [str(r.uri) for r in res] == [main.SETUP_CARD_URI]
    assert res[0].mimeType == "text/html;profile=mcp-app"
    content = next(iter(await main.mcp.read_resource(main.SETUP_CARD_URI)))
    html = content.content
    for needle in (
        "ui/initialize",
        "tools/call",
        "bridge_setup",
        "bridge_status",
        "bridge_rotate_token",
        "bridge_open_chrome_extensions",
        "prefers-color-scheme",
    ):
        assert needle in html
    assert "innerHTML" not in html, "卡片只用 textContent，避免注入"


async def test_setup_and_status_tools(tmp_paths: BridgePaths):
    _, res = await main.mcp.call_tool("bridge_setup", {})
    assert res["setup"]["token_created"] is True
    assert (tmp_paths.ext_dir / "manifest.json").is_file()
    token = tmp_paths.token_file.read_text()
    assert token not in str(res)

    _, st = await main.mcp.call_tool("bridge_status", {})
    assert st["extension"]["ready"] and st["host"]["registered"]
    assert token not in str(st)

    _, rot = await main.mcp.call_tool("bridge_rotate_token", {})
    assert tmp_paths.token_file.read_text() != token
    assert "重新生成" in rot["message"]

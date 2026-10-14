"""Polaris Browser Use MCP Server (v2.1.0).

基于真实浏览器多后端隔离、DOM 快照与低 token 正文阅读的通用 Agent 浏览器扩展（不含任何平台知识；
已知社交平台的读写与采集见 polaris-social 插件）。
所有工具统一经由 FastMCP 注册，严格设置 ToolAnnotations 参数提示。
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .tools_browser import (
    tool_browser_act,
    tool_browser_extract,
    tool_browser_open,
    tool_browser_read,
    tool_browser_scroll,
    tool_browser_snapshot,
    tool_browser_status,
    tool_browser_tabs,
)

mcp = FastMCP("polaris-browser-use")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_open(url: str, new_tab: bool = False) -> dict[str, Any]:
    """打开指定 URL 网页。默认为活动工作页，可指定 new_tab=True 创建新专属标签页。"""
    return await tool_browser_open(url, new_tab=new_tab)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_read(
    mode: Literal["article", "markdown", "text", "links"] = "article",
    max_chars: int = 6000,
    offset: int = 0,
    selector: str | None = None,
) -> dict[str, Any]:
    """以极低 token 消耗阅读当前页面。支持智能正文(article)、结构(markdown)、纯文本(text)和超链(links)。支持字符分页。"""
    return await tool_browser_read(
        mode=mode, max_chars=max_chars, offset=offset, selector=selector
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_snapshot(
    scope: Literal["viewport", "page"] = "viewport",
    max_items: int = 80,
) -> dict[str, Any]:
    """生成页面可交互元素的快照，打上 e<N> 引用编码（例如 e12 button "登录"）。仅在需要点击/输入等复杂交互时使用。"""
    return await tool_browser_snapshot(scope=scope, max_items=max_items)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def browser_act(
    ref: str,
    action: Literal[
        "click", "fill", "fill_and_enter", "hover", "select", "press", "back"
    ],
    text: str = "",
) -> dict[str, Any]:
    """对快照生成的 e<N> 引用元素执行操作。支持点击(click)、输入(fill/fill_and_enter)、悬停(hover)、按键(press)和回退(back)。"""
    return await tool_browser_act(ref=ref, action=action, text=text)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_scroll(
    direction: Literal["down", "up"] = "down",
    times: int = 1,
) -> dict[str, Any]:
    """平滑滚动当前页面，返回最新滚动纵坐标与是否触底。"""
    return await tool_browser_scroll(direction=direction, times=times)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_extract(
    container: str,
    fields: dict[str, str],
    max_items: int = 50,
) -> dict[str, Any]:
    """按 CSS 选择器规则批量抽取页面列表。字段语法支持 css 或 css@attr（如 title: 'h3', url: 'a@href'）。"""
    return await tool_browser_extract(
        container=container, fields=fields, max_items=max_items
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
async def browser_tabs(
    action: Literal["list", "switch", "close"] = "list",
    tab_id: str = "",
) -> dict[str, Any]:
    """查看或切换 Polaris 自建的浏览器标签页。严禁触碰用户的已有标签。"""
    return await tool_browser_tabs(action=action, tab_id=tab_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
async def browser_status() -> dict[str, Any]:
    """查看当前浏览器后端类型(cdp/managed/extension)、连接状态与已登录站点缓存。"""
    return await tool_browser_status()


def main() -> None:
    """启动 MCP 服务端。"""
    mcp.run()


if __name__ == "__main__":
    main()

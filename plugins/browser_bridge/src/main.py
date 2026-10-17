"""Polaris Browser Bridge 设置插件（MCP 服务器名 polaris-browser-bridge）。

为何单独成插件：Chrome 扩展 Polaris Browser Bridge 被 browser_use 与 social 共用，
其唯一源码、一键设置、Native Messaging 自动配对与令牌管理都集中在这里；
本进程不运行中继（中继在使用浏览器的插件进程里），连接状态通过中继写入的握手文件判断。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import setup_ops
from .paths import BridgePaths, real_paths

SETUP_CARD_URI = "ui://polaris-browser-bridge/setup.html"
# MCP Apps 标准 UI 资源 MIME（Polaris 宿主只接受该值或 skybridge 旧别名）
MCP_APP_MIME = "text/html;profile=mcp-app"
_CARD_FILE = Path(__file__).resolve().parent / "ui" / "setup.html"

mcp = FastMCP("polaris-browser-bridge")

# 工具对模型与卡片视图均可见（卡片按钮通过 tools/call 调用，要求 visibility 含 "app"）
_MODEL_AND_APP = {"ui": {"visibility": ["model", "app"]}}


def _paths() -> BridgePaths:
    return real_paths()


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True
    ),
    meta={"ui": {"resourceUri": SETUP_CARD_URI, "visibility": ["model", "app"]}},
)
def bridge_setup() -> dict[str, Any]:
    """一键设置浏览器扩展：生成配对令牌、把扩展同步到稳定目录、注册 Chrome 自动配对宿主。可重复执行（插件升级后再跑一次即可更新扩展）。返回结构化状态与下一步说明。"""
    result = setup_ops.run_setup(_paths())
    result["message"] = (
        "已准备好扩展目录与自动配对。下一步：打开 chrome://extensions，开启开发者模式，"
        f"「加载已解压的扩展程序」选择 {result['extension']['dir']}；加载后扩展会自动获取令牌并连接。"
    )
    return result


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    meta=_MODEL_AND_APP,
)
def bridge_open_chrome_extensions() -> dict[str, Any]:
    """在 macOS 上打开 Chrome 的 chrome://extensions 页面，并在 Finder 中显示扩展目录，方便拖入加载。其他系统返回手动操作说明。需先运行 bridge_setup。"""
    return setup_ops.open_chrome_extensions(_paths())


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    meta=_MODEL_AND_APP,
)
def bridge_status() -> dict[str, Any]:
    """查看浏览器扩展设置状态：令牌是否存在、自动配对宿主是否已注册、扩展目录是否就绪及版本、扩展当前是否已连接。不会返回令牌明文。"""
    return setup_ops.build_status(_paths())


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False
    ),
    meta=_MODEL_AND_APP,
)
def bridge_rotate_token() -> dict[str, Any]:
    """重新生成扩展配对令牌（旧令牌立即作废）。已装扩展会通过 Native Messaging 自动获取新令牌；正在运行的中继会在下次握手或心跳时重新读取令牌文件并断开旧连接，扩展随后自动重连。手动粘贴过令牌的扩展需要重新粘贴或改用自动配对。"""
    paths = _paths()
    setup_ops.rotate_token(paths)
    st = setup_ops.build_status(paths)
    st["message"] = (
        "令牌已重新生成。自动配对的扩展会在断线后自动取新令牌，通常 1 分钟内恢复；"
        "手动粘贴过令牌的扩展请在扩展设置页点「重新自动配对」。"
    )
    return st


@mcp.resource(
    SETUP_CARD_URI,
    name="browser_bridge_setup_card",
    title="Browser Bridge 设置卡片",
    description="一键设置 Polaris Browser Bridge 扩展的交互卡片（MCP Apps）。",
    mime_type=MCP_APP_MIME,
    meta={"ui": {"prefersBorder": True}},
)
def setup_card() -> str:
    """返回单文件 HTML 卡片。"""
    return _CARD_FILE.read_text(encoding="utf-8")


def main() -> None:
    """启动 MCP 服务端。"""
    mcp.run()


if __name__ == "__main__":
    main()

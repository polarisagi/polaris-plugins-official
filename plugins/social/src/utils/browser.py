"""CDP browser connection — shared by all adapters.

通过共享的 BrowserHub 单例统一管理日常 Chrome 与托管浏览器连接，
确保在 Polaris 自建窗口内运行，杜绝侵入用户日常标签。
"""

from __future__ import annotations

from patchright.async_api import Page

from .browser_hub import get_hub


async def ensure_page() -> Page:
    """获取当前活动的工作标签页，保持与各平台适配器的调用契约兼容。"""
    hub = await get_hub()
    return await hub.page(unattended=False)


async def fresh_page() -> Page:
    """在 Polaris 专属窗口内开启新的标签页。"""
    hub = await get_hub()
    return await hub.new_owned_page()

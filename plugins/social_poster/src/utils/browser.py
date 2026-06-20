"""CDP browser connection — shared by all adapters."""

import os
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

_playwright = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None


async def _on_new_page(page: Page):
    global _page
    _page = page


async def ensure_page() -> Page:
    """Return the current active page, connecting to Chrome CDP if needed."""
    global _playwright, _browser, _context, _page

    if _page is not None and not _page.is_closed():
        return _page

    if _playwright is None:
        _playwright = await async_playwright().start()

    home = Path.home()
    local_app_data = os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))

    port_files = [
        home / "Library/Application Support/Google/Chrome/DevToolsActivePort",
        home / "Library/Application Support/Microsoft Edge/DevToolsActivePort",
        Path(local_app_data) / "Google/Chrome/User Data/DevToolsActivePort",
        Path(local_app_data) / "Microsoft/Edge/User Data/DevToolsActivePort",
    ]

    endpoint_url = None
    for port_file in port_files:
        if port_file.exists():
            try:
                content = port_file.read_text("utf-8").splitlines()
                if content:
                    port = int(content[0].strip())
                    endpoint_url = f"http://127.0.0.1:{port}"
                    if len(content) > 1 and content[1].strip().startswith("/devtools/"):
                        endpoint_url = f"ws://127.0.0.1:{port}{content[1].strip()}"
                    break
            except Exception:
                pass

    if not endpoint_url:
        raise RuntimeError(
            "No active Chrome DevTools port found.\n"
            "Start Chrome with remote debugging:\n"
            '  macOS: open -a "Google Chrome" --args --remote-debugging-port=9222\n'
            "  Win:   chrome.exe --remote-debugging-port=9222"
        )

    _browser = await _playwright.chromium.connect_over_cdp(endpoint_url)
    contexts = _browser.contexts
    _context = contexts[0] if contexts else await _browser.new_context()
    _context.on("page", _on_new_page)
    _page = await _context.new_page()
    return _page


async def fresh_page() -> Page:
    """Open a new tab and make it the active page."""
    global _context, _page
    await ensure_page()  # ensures _context is initialized
    if _context is None:
        raise RuntimeError("Browser context failed to initialize")
    p = await _context.new_page()
    _page = p
    return p

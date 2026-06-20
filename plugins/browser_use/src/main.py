import os
import sys
from typing import Optional
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page, BrowserContext, Browser

mcp = FastMCP("polaris-browser-use")

# Global state
_playwright = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None


async def _on_page(page: Page):
    global _page
    print("New tab opened, switching to it.", file=sys.stderr)
    _page = page


async def _ensure_page() -> Page:
    global _playwright, _browser, _context, _page

    if _page is not None and not _page.is_closed():
        return _page

    if _playwright is None:
        _playwright = await async_playwright().start()

    try:
        # Try dynamic debugging ports
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
                        if len(content) > 1 and content[1].strip().startswith(
                            "/devtools/"
                        ):
                            endpoint_url = f"ws://127.0.0.1:{port}{content[1].strip()}"
                        break
                except Exception:
                    pass

        if endpoint_url:
            _browser = await _playwright.chromium.connect_over_cdp(endpoint_url)
            contexts = _browser.contexts
            _context = contexts[0] if contexts else await _browser.new_context()
        else:
            raise Exception("No active DevTools port found.")

    except Exception as e:
        print(
            f"Failed to connect via CDP, launching a new browser instance... {e}",
            file=sys.stderr,
        )
        _browser = await _playwright.chromium.launch(headless=False)
        contexts = _browser.contexts
        _context = contexts[0] if contexts else await _browser.new_context()

    _context.on("page", _on_page)
    _page = await _context.new_page()

    return _page


@mcp.tool()
async def navigate(url: str) -> str:
    """Navigate to a URL and wait for it to load. The URL must be a full, valid URL starting with http:// or https://"""
    page = await _ensure_page()
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    return f"Navigated to {url}"


@mcp.tool()
async def get_interactive_dom() -> str:
    """Get a simplified interactive DOM tree. Returns ONLY interactive elements (links, buttons, inputs) with a unique 'polaris-id'. Use this ONLY when you need to find an element to click or fill. To read the main text content of the page, use get_page_content instead."""
    page = await _ensure_page()

    js_code = """
    () => {
        let counter = 1;
        const result = [];
        const interactiveSelectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [tabindex]:not([tabindex="-1"])';
        
        function processNode(node) {
            if (!node || !node.querySelectorAll) return;
            
            const elements = node.querySelectorAll(interactiveSelectors);
            elements.forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return;
                }

                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                const inViewport = rect.top >= 0 && rect.left >= 0 && 
                                   rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && 
                                   rect.right <= (window.innerWidth || document.documentElement.clientWidth);

                el.setAttribute('polaris-id', counter);
                
                let text = el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || '';
                text = text.trim().substring(0, 50);
                
                if (!text && el.tagName === 'INPUT') {
                    text = '[Input Field]';
                }

                if (text || el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
                    result.push({
                        id: counter,
                        tag: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || undefined,
                        text: text,
                        inViewport: inViewport
                    });
                }
                counter++;
            });

            const allElements = node.querySelectorAll('*');
            allElements.forEach(el => {
                if (el.shadowRoot) {
                    processNode(el.shadowRoot);
                }
            });
        }
        
        processNode(document);
        return result;
    }
    """
    try:
        dom_tree = await page.evaluate(js_code)
        formatted = []
        for e in dom_tree:
            role_str = f' role="{e["role"]}"' if e.get("role") else ""
            vp_str = "" if e.get("inViewport") else " (Out of Viewport)"
            formatted.append(
                f"[ID: {e['id']}] <{e['tag']}{role_str}> {e['text']} {vp_str}".strip()
            )

        res = "\\n".join(formatted)
        return res if res else "No interactive elements found."
    except Exception as e:
        return f"Error extracting DOM: {e}"


@mcp.tool()
async def action_by_id(id: int, action: str, text: str = "") -> str:
    """Perform an action on an element using its 'polaris-id' obtained from get_interactive_dom. 'fill' clears the input first. 'fill_and_enter' is highly recommended for search boxes to automatically submit.
    Args:
        id: The polaris-id of the element
        action: "click", "fill", "fill_and_enter", or "hover"
        text: Text to fill (if action is fill or fill_and_enter)
    """
    page = await _ensure_page()
    try:
        locator = page.locator(f'[polaris-id="{id}"]').first

        try:
            await locator.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        if action == "click":
            await locator.click(force=True)
        elif action == "fill":
            await locator.fill(text, force=True)
        elif action == "fill_and_enter":
            await locator.fill(text, force=True)
            await locator.press("Enter")
        elif action == "hover":
            await locator.hover(force=True)
        else:
            return f"Unknown action: {action}"

        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass

        await page.wait_for_timeout(500)
        return f"Action {action} performed successfully on element ID {id}."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def scroll_page(direction: str) -> str:
    """Scroll the page up or down by one viewport height.
    Args:
        direction: "down" or "up"
    """
    page = await _ensure_page()
    try:
        dir_mult = -1 if direction == "up" else 1
        await page.evaluate(f"window.scrollBy(0, window.innerHeight * {dir_mult});")
        await page.wait_for_timeout(500)
        return f"Scrolled {direction}."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def go_back() -> str:
    """Go back to the previous page in the browser history."""
    page = await _ensure_page()
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=5000)
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        return "Navigated back."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def close_tab() -> str:
    """Close the current active tab and switch to the previous one. Use this when you are done reading a link that opened in a new tab."""
    global _page, _context
    page = await _ensure_page()
    try:
        await page.close()
        if _context:
            pages = _context.pages
            if pages:
                _page = pages[-1]
                return "Tab closed. Switched to previous tab."
            else:
                _page = await _context.new_page()
                return "Tab closed. Opened a new empty tab as no other tabs were left."
        return "Tab closed."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def get_page_content() -> str:
    """Get the visible text content of the current page. Use this to read articles, search results, or extract information."""
    page = await _ensure_page()
    try:
        text = await page.evaluate("document.body.innerText || ''")
        return text[:40000]
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def get_current_state() -> str:
    """Get the current URL and page title to know exactly which page you are currently on."""
    page = await _ensure_page()
    try:
        url = page.url
        title = await page.title()
        return f"URL: {url}\\nTitle: {title}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()

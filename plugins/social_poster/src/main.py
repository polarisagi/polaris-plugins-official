import asyncio
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page, BrowserContext, Browser
import os
import sys
from pathlib import Path
from typing import Optional

mcp = FastMCP("social_poster")

# Global state for browser
_playwright = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None

async def _ensure_page() -> Page:
    global _playwright, _browser, _context, _page
    
    if _page is not None and not _page.is_closed():
        return _page

    if _playwright is None:
        _playwright = await async_playwright().start()

    try:
        home = Path.home()
        local_app_data = os.environ.get('LOCALAPPDATA', str(home / 'AppData' / 'Local'))
        
        port_files = [
            home / 'Library/Application Support/Google/Chrome/DevToolsActivePort',
            home / 'Library/Application Support/Microsoft Edge/DevToolsActivePort',
            Path(local_app_data) / 'Google/Chrome/User Data/DevToolsActivePort',
            Path(local_app_data) / 'Microsoft/Edge/User Data/DevToolsActivePort',
        ]

        endpoint_url = None
        for port_file in port_files:
            if port_file.exists():
                try:
                    content = port_file.read_text('utf-8').splitlines()
                    if content:
                        port = int(content[0].strip())
                        endpoint_url = f"http://127.0.0.1:{port}"
                        if len(content) > 1 and content[1].strip().startswith('/devtools/'):
                            endpoint_url = f"ws://127.0.0.1:{port}{content[1].strip()}"
                        break
                except Exception:
                    pass

        if endpoint_url:
            _browser = await _playwright.chromium.connect_over_cdp(endpoint_url)
            contexts = _browser.contexts
            _context = contexts[0] if contexts else await _browser.new_context()
        else:
            raise Exception("No active Chrome DevTools port found.")
            
    except Exception as e:
        error_msg = (
            f"Failed to connect to Chrome via DevTools CDP. {str(e)}\n"
            "Please ensure Chrome is running with remote debugging enabled.\n"
            "Command: Google Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-profile"
        )
        print(error_msg, file=sys.stderr)
        raise RuntimeError(error_msg)

    _page = await _context.new_page()
    return _page

@mcp.tool()
async def auto_post(platform: str, content: str, image_paths: list[str] = None):
    """
    Automatically post content to a specified social media platform.
    
    Args:
        platform: The target platform (twitter, weibo, xiaohongshu, douyin, wechat, instagram, facebook).
        content: The text content to post.
        image_paths: Optional list of absolute paths to images to upload.
    """
    platform = platform.lower()
    
    # 1. Content Management (Chunking/Formatting)
    from .content_manager import format_content_for_platform
    formatted_content = await format_content_for_platform(platform, content)
    
    # 2. Get the appropriate adapter
    from .adapters.twitter import TwitterAdapter
    from .adapters.weibo import WeiboAdapter
    from .adapters.xiaohongshu import XiaohongshuAdapter
    from .adapters.douyin import DouyinAdapter
    from .adapters.wechat import WechatAdapter
    from .adapters.instagram import InstagramAdapter
    from .adapters.facebook import FacebookAdapter
    
    adapters = {
        "twitter": TwitterAdapter,
        "weibo": WeiboAdapter,
        "xiaohongshu": XiaohongshuAdapter,
        "douyin": DouyinAdapter,
        "wechat": WechatAdapter,
        "instagram": InstagramAdapter,
        "facebook": FacebookAdapter,
    }
    
    if platform not in adapters:
        return f"Error: Platform '{platform}' is not supported."
        
    page = await _ensure_page()
    AdapterClass = adapters[platform]
    adapter = AdapterClass(page)
    
    # 3. Execute Browser Automation Steps
    try:
        await adapter.open_platform()
        if image_paths:
            await adapter.upload_media(image_paths)
        await adapter.fill_content(formatted_content)
        await adapter.submit_post()
        return f"Successfully posted to {platform}."
    except Exception as e:
        return f"Failed to post to {platform}: {str(e)}"

@mcp.tool()
async def delete_post(platform: str, post_identifier: str):
    """
    Delete a specific post on a given social media platform.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return adapter
    
    try:
        await adapter.delete_post(post_identifier)
        return f"Successfully deleted post on {platform}."
    except Exception as e:
        return f"Failed to delete post on {platform}: {str(e)}"

@mcp.tool()
async def get_comments(platform: str, post_identifier: str) -> list[dict]:
    """
    Get comments for a specific post. Returns a list of comments with temporary IDs.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return [{"error": adapter}]
    
    try:
        return await adapter.get_comments(post_identifier)
    except Exception as e:
        return [{"error": f"Failed to get comments on {platform}: {str(e)}"}]

@mcp.tool()
async def reply_comment(platform: str, post_identifier: str, comment_id: str, text: str):
    """
    Reply to a specific comment on a post using its temporary ID.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return adapter
    
    try:
        await adapter.reply_to_comment(post_identifier, comment_id, text)
        return f"Successfully replied to comment {comment_id} on {platform}."
    except Exception as e:
        return f"Failed to reply to comment on {platform}: {str(e)}"

@mcp.tool()
async def delete_comment(platform: str, post_identifier: str, comment_id: str):
    """
    Delete or hide a specific comment on a post using its temporary ID.
    Use this to manage inappropriate or spam comments.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return adapter
    
    try:
        await adapter.delete_comment(post_identifier, comment_id)
        return f"Successfully deleted/hid comment {comment_id} on {platform}."
    except Exception as e:
        return f"Failed to delete comment on {platform}: {str(e)}"

@mcp.tool()
async def search_posts(platform: str, query: str) -> list[dict]:
    """
    Search for posts on a given platform.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return [{"error": adapter}]
    
    try:
        return await adapter.search_posts(query)
    except Exception as e:
        return [{"error": f"Failed to search on {platform}: {str(e)}"}]

@mcp.tool()
async def read_post(platform: str, post_identifier: str) -> str:
    """
    Read the full text content of a specific post.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str): return adapter
    
    try:
        return await adapter.read_post(post_identifier)
    except Exception as e:
        return f"Failed to read post on {platform}: {str(e)}"

@mcp.tool()
def get_platform_skill(platform: str) -> str:
    """
    Retrieve the content creation and compliance guidelines (skill/prompt) for a specific platform.
    Call this BEFORE generating content to ensure safety, avoid shadowbans, and match the platform's style.
    """
    import os
    skill_map = {
        "xiaohongshu": "xiaohongshu_skill.md",
        "douyin": "douyin_skill.md",
        "wechat": "wechat_skill.md",
        "weibo": "weibo_skill.md",
        "twitter": "western_social_skill.md",
        "instagram": "western_social_skill.md",
        "facebook": "western_social_skill.md"
    }
    
    if platform not in skill_map:
        return "No specific skill/compliance guidelines found for this platform."
        
    skill_file = skill_map[platform]
    # __file__ is in src/main.py, so we go up one level to the root of the plugin, then into skills/
    src_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(src_dir)
    file_path = os.path.join(plugin_dir, "skills", skill_file)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to load skill file: {e}"

@mcp.tool()
def get_content_template(template_type: str) -> str:
    """
    Retrieve a specific post styling template (e.g., 'product_review', 'daily_vlog', 'meme_joke').
    Call this to get structural guidance when writing a new post.
    """
    import os
    src_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(src_dir)
    file_path = os.path.join(plugin_dir, "skills", "templates", f"{template_type}.md")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to load template '{template_type}': {e}. Available templates: product_review, daily_vlog, meme_joke."

@mcp.tool()
async def search_free_image(query: str) -> str:
    """
    Search for and download a royalty-free image based on a query using the connected browser.
    Returns the absolute local path to the downloaded image, which MUST be passed to the auto_post tool's image_paths argument.
    """
    import urllib.parse
    import urllib.request
    import tempfile
    import os
    import time
    
    page = await _ensure_page()
    encoded_query = urllib.parse.quote(query)
    
    # Using Pexels for high quality royalty-free images
    search_url = f"https://www.pexels.com/search/{encoded_query}/"
    
    try:
        print(f"Searching for image: {query}")
        await page.goto(search_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        
        # Try to find the first photo image source
        img_element = page.locator('article img').first
        if await img_element.count() == 0:
            return "Error: Could not find any images for this query."
            
        img_url = await img_element.get_attribute('src')
        if not img_url:
            return "Error: Could not extract image URL."
            
        print(f"Downloading image from: {img_url}")
        
        # Download image to temp directory
        temp_dir = tempfile.gettempdir()
        file_name = f"social_post_img_{int(time.time())}.jpg"
        file_path = os.path.join(temp_dir, file_name)
        
        # Run synchronous urlretrieve in thread pool to not block asyncio event loop
        await asyncio.to_thread(urllib.request.urlretrieve, img_url, file_path)
        
        print(f"Image downloaded to: {file_path}")
        return file_path
        
    except Exception as e:
        return f"Failed to search/download image: {str(e)}"

if __name__ == "__main__":
    mcp.run()

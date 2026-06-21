"""
Polaris Social Poster — MCP server entry point.

Supported platforms:
  twitter, instagram, facebook, weibo, xiaohongshu, douyin, wechat,
  tiktok, linkedin, threads
"""

from typing import Optional
import asyncio
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("social_poster")

# ─── Adapter registry ─────────────────────────────────────────────────────────


def _get_adapters():
    from .adapters.twitter import TwitterAdapter
    from .adapters.weibo import WeiboAdapter
    from .adapters.xiaohongshu import XiaohongshuAdapter
    from .adapters.douyin import DouyinAdapter
    from .adapters.wechat import WechatAdapter
    from .adapters.instagram import InstagramAdapter
    from .adapters.facebook import FacebookAdapter
    from .adapters.tiktok import TikTokAdapter
    from .adapters.linkedin import LinkedInAdapter
    from .adapters.threads import ThreadsAdapter

    return {
        "twitter": TwitterAdapter,
        "weibo": WeiboAdapter,
        "xiaohongshu": XiaohongshuAdapter,
        "douyin": DouyinAdapter,
        "wechat": WechatAdapter,
        "instagram": InstagramAdapter,
        "facebook": FacebookAdapter,
        "tiktok": TikTokAdapter,
        "linkedin": LinkedInAdapter,
        "threads": ThreadsAdapter,
    }


SUPPORTED_PLATFORMS = [
    "twitter",
    "instagram",
    "facebook",
    "weibo",
    "xiaohongshu",
    "douyin",
    "wechat",
    "tiktok",
    "linkedin",
    "threads",
]


async def _get_adapter(platform: str):
    """Return an initialized adapter or an error string."""
    from .utils.browser import ensure_page

    adapters = _get_adapters()
    p = platform.lower()
    if p not in adapters:
        return f"Error: Platform '{p}' is not supported. Supported: {', '.join(SUPPORTED_PLATFORMS)}"
    page = await ensure_page()
    return adapters[p](page)


# ─── ① Publishing ─────────────────────────────────────────────────────────────


@mcp.tool()
async def auto_post(
    platform: str,
    content: str,
    media_paths: Optional[list[str]] = None,
):
    """
    Post text + images/videos to a social media platform.

    Args:
        platform: Target platform (twitter/instagram/facebook/weibo/xiaohongshu/douyin/wechat/tiktok/linkedin/threads).
        content:  Text content of the post.
        media_paths: Optional list of absolute local paths to images or videos.
    """
    from .content_manager import format_content_for_platform

    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter

    formatted = await format_content_for_platform(platform.lower(), content)
    try:
        await adapter.open_platform()
        if media_paths:
            await adapter.upload_media(media_paths)
        await adapter.fill_content(formatted)
        await adapter.submit_post()
        return f"✅ Successfully posted to {platform}."
    except Exception as e:
        return f"❌ Failed to post to {platform}: {e}"


@mcp.tool()
async def batch_post(
    platforms: list[str],
    content: str,
    media_paths: Optional[list[str]] = None,
):
    """
    Post the same content to multiple platforms simultaneously.

    Args:
        platforms: List of platforms, e.g. ["twitter", "weibo", "xiaohongshu"].
        content:   Text content.
        media_paths: Optional list of absolute media file paths.

    Returns a per-platform result dict.
    """
    results = {}
    for platform in platforms:
        result = await auto_post(platform, content, media_paths)
        results[platform] = result
    return results


@mcp.tool()
async def post_video(
    platform: str,
    video_path: str,
    description: str,
    cover_path: Optional[str] = None,
    music_path: Optional[str] = None,
):
    """
    Upload and publish a video with extended metadata (cover, music).
    Best suited for: douyin, tiktok, instagram (Reels).

    Args:
        platform:    Target platform.
        video_path:  Absolute path to the video file.
        description: Caption / description text.
        cover_path:  Optional thumbnail image path.
        music_path:  Optional audio file for background music (douyin/tiktok).
    """
    media = [video_path]
    if cover_path:
        media.append(cover_path)
    if music_path:
        media.append(music_path)
    return await auto_post(platform, description, media)


@mcp.tool()
async def post_story(
    platform: str,
    media_path: str,
    text: str = "",
):
    """
    Post an ephemeral story (Instagram Story, Facebook Story).

    Args:
        platform:   instagram or facebook.
        media_path: Absolute path to image or short video.
        text:       Optional overlay text.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.post_story([media_path], text)
        return f"✅ Story posted to {platform}."
    except NotImplementedError:
        return f"⚠️ {platform} does not support stories via this plugin yet."
    except Exception as e:
        return f"❌ Failed to post story to {platform}: {e}"


@mcp.tool()
async def post_thread(
    platform: str,
    tweets: list[str],
    media_paths: Optional[list[str]] = None,
):
    """
    Post a thread / series of connected posts (Twitter thread, LinkedIn long-form).
    For Twitter, pass each tweet as a separate string (max 280 chars each).
    Use split_text_into_thread to auto-split long text first.

    Args:
        platform:    twitter or linkedin.
        tweets:      Ordered list of text chunks.
        media_paths: Optional media to attach to the first post.
    """
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.post_thread(tweets, media_paths)
        return f"✅ Thread of {len(tweets)} posts published to {platform}."
    except NotImplementedError:
        return f"⚠️ {platform} does not support threads via this plugin."
    except Exception as e:
        return f"❌ Failed to post thread to {platform}: {e}"


# ─── ② Scheduled Publishing ───────────────────────────────────────────────────


@mcp.tool()
async def schedule_post(
    platform: str,
    content: str,
    scheduled_time: str,
    media_paths: Optional[list[str]] = None,
    post_type: str = "post",
):
    """
    Schedule a post for a future time.

    Args:
        platform:       Target platform.
        content:        Text content.
        scheduled_time: ISO-8601 datetime, e.g. "2025-07-01T09:00:00".
        media_paths:    Optional media file paths.
        post_type:      "post" | "video" | "story" | "thread".

    Returns the task_id. Run `run_scheduled_posts` later to execute due tasks.
    """
    from . import scheduler

    task_id = scheduler.add_task(
        platform, content, media_paths or [], scheduled_time, post_type
    )
    return f"✅ Post scheduled (task_id={task_id}) for {scheduled_time} on {platform}."


@mcp.tool()
async def list_scheduled_posts(platform: Optional[str] = None):
    """
    List all pending scheduled posts.

    Args:
        platform: Optional filter by platform name.
    """
    from . import scheduler

    tasks = scheduler.list_tasks(platform)
    if not tasks:
        return "No pending scheduled posts."
    return tasks


@mcp.tool()
async def cancel_scheduled_post(task_id: str):
    """
    Cancel a scheduled post by its task_id.
    """
    from . import scheduler

    ok = scheduler.cancel_task(task_id)
    return (
        f"✅ Task {task_id} cancelled."
        if ok
        else f"❌ Task {task_id} not found or already processed."
    )


@mcp.tool()
async def run_scheduled_posts():
    """
    Execute all scheduled posts whose scheduled_time has passed.
    Call this periodically (e.g., every minute) to process the queue.
    """
    from . import scheduler

    due = scheduler.get_due_tasks()
    if not due:
        return "No posts due right now."
    results = {}
    for task in due:
        try:
            if task["post_type"] == "video":
                r = await post_video(
                    task["platform"], task["media_paths"][0], task["content"]
                )
            elif task["post_type"] == "thread":
                r = await post_thread(
                    task["platform"], task["content"].split("\n---\n")
                )
            else:
                r = await auto_post(
                    task["platform"], task["content"], task["media_paths"]
                )
            scheduler.mark_done(task["id"], True)
            results[task["id"]] = r
        except Exception as e:
            scheduler.mark_done(task["id"], False, str(e))
            results[task["id"]] = f"❌ {e}"
    return results


# ─── ③ Post Management ────────────────────────────────────────────────────────


@mcp.tool()
async def delete_post(platform: str, post_identifier: str):
    """Delete a specific post. post_identifier is usually the post URL."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.delete_post(post_identifier)
        return f"✅ Post deleted on {platform}."
    except Exception as e:
        return f"❌ Failed to delete post on {platform}: {e}"


@mcp.tool()
async def edit_post(platform: str, post_identifier: str, new_content: str):
    """Edit an existing post (supported: twitter with Premium, weibo, linkedin)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.edit_post(post_identifier, new_content)
        return f"✅ Post edited on {platform}."
    except NotImplementedError:
        return f"⚠️ {platform} does not support post editing."
    except Exception as e:
        return f"❌ Failed to edit post on {platform}: {e}"


@mcp.tool()
async def get_my_posts(platform: str, limit: int = 10):
    """Fetch a list of your own recent posts on a platform."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.get_my_posts(limit)
    except NotImplementedError:
        return [{"error": f"get_my_posts not supported on {platform}."}]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def pin_post(platform: str, post_identifier: str):
    """Pin a post to the top of your profile."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.pin_post(post_identifier)
        return f"✅ Post pinned on {platform}."
    except NotImplementedError:
        return f"⚠️ {platform} does not support pinning via this plugin."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def save_draft(
    platform: str, content: str, media_paths: Optional[list[str]] = None
):
    """Save a post as a draft (without publishing)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.save_draft(content, media_paths)
        return f"✅ Draft saved on {platform}."
    except NotImplementedError:
        return f"⚠️ {platform} does not support drafts via this plugin."
    except Exception as e:
        return f"❌ {e}"


# ─── ④ Comment Management ─────────────────────────────────────────────────────


@mcp.tool()
async def get_comments(platform: str, post_identifier: str) -> list[dict]:
    """Get comments for a specific post. Returns [{id, author, content}]."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.get_comments(post_identifier)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def reply_comment(
    platform: str, post_identifier: str, comment_id: str, text: str
):
    """Reply to a specific comment using its id from get_comments."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.reply_to_comment(post_identifier, comment_id, text)
        return f"✅ Replied to comment {comment_id} on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def delete_comment(platform: str, post_identifier: str, comment_id: str):
    """Delete or hide a comment."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.delete_comment(post_identifier, comment_id)
        return f"✅ Comment {comment_id} deleted/hidden on {platform}."
    except Exception as e:
        return f"❌ {e}"


# ─── ⑤ Engagement ────────────────────────────────────────────────────────────


@mcp.tool()
async def like_post(platform: str, post_identifier: str):
    """Like / heart a post."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.like_post(post_identifier)
        return f"✅ Liked post on {platform}."
    except NotImplementedError:
        return f"⚠️ like_post not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def unlike_post(platform: str, post_identifier: str):
    """Remove a like from a post."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.unlike_post(post_identifier)
        return f"✅ Unliked post on {platform}."
    except NotImplementedError:
        return f"⚠️ unlike_post not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def repost(platform: str, post_identifier: str):
    """Retweet / repost / share a post without comment."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.repost(post_identifier)
        return f"✅ Reposted on {platform}."
    except NotImplementedError:
        return f"⚠️ repost not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def quote_post(platform: str, post_identifier: str, comment: str):
    """Quote-repost with an added comment (Twitter quote-tweet, LinkedIn quote)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.quote_post(post_identifier, comment)
        return f"✅ Quote-posted on {platform}."
    except NotImplementedError:
        return f"⚠️ quote_post not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


# ─── ⑥ Search & Discovery ────────────────────────────────────────────────────


@mcp.tool()
async def search_posts(platform: str, query: str) -> list[dict]:
    """Search for posts on a platform. Returns [{url, snippet}]."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.search_posts(query)
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def read_post(platform: str, post_identifier: str) -> str:
    """Read the full text content of a specific post."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        return await adapter.read_post(post_identifier)
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def get_trending_topics(platform: str, limit: int = 10) -> list[dict]:
    """Get trending topics / hashtags on a platform."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.get_trending_topics(limit)
    except NotImplementedError:
        return [{"error": f"get_trending_topics not supported on {platform}."}]
    except Exception as e:
        return [{"error": str(e)}]


# ─── ⑦ User Operations ───────────────────────────────────────────────────────


@mcp.tool()
async def get_user_profile(platform: str, username: str) -> dict:
    """Get a user's profile info (name, bio, followers, etc.)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return {"error": adapter}
    try:
        return await adapter.get_user_profile(username)
    except NotImplementedError:
        return {"error": f"get_user_profile not supported on {platform}."}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def follow_user(platform: str, username: str):
    """Follow a user on a platform."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.follow_user(username)
        return f"✅ Now following {username} on {platform}."
    except NotImplementedError:
        return f"⚠️ follow_user not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def unfollow_user(platform: str, username: str):
    """Unfollow a user on a platform."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.unfollow_user(username)
        return f"✅ Unfollowed {username} on {platform}."
    except NotImplementedError:
        return f"⚠️ unfollow_user not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def block_user(platform: str, username: str):
    """Block a user on a platform."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.block_user(username)
        return f"✅ Blocked {username} on {platform}."
    except NotImplementedError:
        return f"⚠️ block_user not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def mute_user(platform: str, username: str):
    """Mute a user (hide their content without unfollowing)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.mute_user(username)
        return f"✅ Muted {username} on {platform}."
    except NotImplementedError:
        return f"⚠️ mute_user not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


@mcp.tool()
async def send_dm(platform: str, username: str, text: str):
    """Send a direct message / private message to a user."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return adapter
    try:
        await adapter.send_dm(username, text)
        return f"✅ DM sent to {username} on {platform}."
    except NotImplementedError:
        return f"⚠️ send_dm not supported on {platform}."
    except Exception as e:
        return f"❌ {e}"


# ─── ⑧ Analytics ─────────────────────────────────────────────────────────────


@mcp.tool()
async def get_post_analytics(platform: str, post_identifier: str) -> dict:
    """Get engagement metrics for a post: likes, comments, shares, views."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return {"error": adapter}
    try:
        return await adapter.get_post_analytics(post_identifier)
    except NotImplementedError:
        return {"error": f"get_post_analytics not supported on {platform}."}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_account_analytics(platform: str) -> dict:
    """Get account-level stats: followers, impressions, reach, etc."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return {"error": adapter}
    try:
        return await adapter.get_account_analytics()
    except NotImplementedError:
        return {"error": f"get_account_analytics not supported on {platform}."}
    except Exception as e:
        return {"error": str(e)}


# ─── ⑨ Notifications ─────────────────────────────────────────────────────────


@mcp.tool()
async def get_notifications(platform: str, limit: int = 20) -> list[dict]:
    """Get recent notifications (likes, follows, comments, mentions)."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.get_notifications(limit)
    except NotImplementedError:
        return [{"error": f"get_notifications not supported on {platform}."}]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.tool()
async def get_mentions(platform: str, limit: int = 20) -> list[dict]:
    """Get recent posts/comments where you are @mentioned."""
    adapter = await _get_adapter(platform)
    if isinstance(adapter, str):
        return [{"error": adapter}]
    try:
        return await adapter.get_mentions(limit)
    except NotImplementedError:
        return [{"error": f"get_mentions not supported on {platform}."}]
    except Exception as e:
        return [{"error": str(e)}]


# ─── ⑩ Content Helpers ───────────────────────────────────────────────────────


@mcp.tool()
def get_platform_skill(platform: str) -> str:
    """
    Return the content creation and compliance guidelines for a platform.
    Call BEFORE generating content to match the platform's style and avoid shadowbans.
    """
    skill_map = {
        "xiaohongshu": "xiaohongshu_skill.md",
        "douyin": "douyin_skill.md",
        "wechat": "wechat_skill.md",
        "weibo": "weibo_skill.md",
        "twitter": "western_social_skill.md",
        "instagram": "western_social_skill.md",
        "facebook": "western_social_skill.md",
        "tiktok": "tiktok_skill.md",
        "linkedin": "linkedin_skill.md",
        "threads": "western_social_skill.md",
    }
    if platform not in skill_map:
        return f"No specific guidelines found for '{platform}'."
    src_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(src_dir)
    path = os.path.join(plugin_dir, "skills", skill_map[platform])
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Failed to load skill file: {e}"


@mcp.tool()
def get_content_template(template_type: str) -> str:
    """
    Return a post content template.
    Available: product_review, daily_vlog, meme_joke, video_short, thread_story.
    """
    src_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_dir = os.path.dirname(src_dir)
    path = os.path.join(plugin_dir, "skills", "templates", f"{template_type}.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return (
            f"Template '{template_type}' not found. "
            "Available: product_review, daily_vlog, meme_joke, video_short, thread_story."
        )


@mcp.tool()
def suggest_hashtags(content: str, platform: str, max_tags: int = 5) -> list[str]:
    """
    Suggest relevant hashtags for the given content and platform.

    Args:
        content:  Post text to analyze.
        platform: Target platform (affects hashtag count and style).
        max_tags: Maximum number of hashtags to return.
    """
    from .content_manager import suggest_hashtags as _suggest

    return _suggest(content, platform, max_tags)


@mcp.tool()
def split_text_into_thread(text: str, max_chars: int = 260) -> list[str]:
    """
    Split long text into tweet-sized chunks suitable for post_thread.
    Adds (n/total) counters automatically.

    Args:
        text:      Long text to split.
        max_chars: Max characters per chunk (default 260, leaving room for counters).
    """
    from .content_manager import split_into_thread

    return split_into_thread(text, max_chars)


@mcp.tool()
async def search_free_image(query: str) -> str:
    """
    Search and download a royalty-free image from Pexels.
    Returns the absolute local path — pass it to auto_post's media_paths.

    Args:
        query: Search keyword (e.g. "mountain sunset", "coffee shop").
    """
    import urllib.parse
    import urllib.request
    import tempfile
    import time
    from .utils.browser import ensure_page

    page = await ensure_page()
    encoded = urllib.parse.quote(query)
    try:
        await page.goto(
            f"https://www.pexels.com/search/{encoded}/", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)
        img = page.locator("article img").first
        if await img.count() == 0:
            return "Error: No images found for this query."
        img_url = await img.get_attribute("src")
        if not img_url:
            return "Error: Could not extract image URL."
        tmp = tempfile.gettempdir()
        fname = f"social_post_{int(time.time())}.jpg"
        fpath = os.path.join(tmp, fname)
        await asyncio.to_thread(urllib.request.urlretrieve, img_url, fpath)
        return fpath
    except Exception as e:
        return f"Failed to search/download image: {e}"


@mcp.tool()
def list_supported_platforms() -> dict:
    """Return all supported platforms and their implemented capabilities."""
    return {
        "twitter": [
            "post",
            "video",
            "thread",
            "like",
            "repost",
            "quote",
            "dm",
            "analytics",
            "trending",
            "schedule",
        ],
        "instagram": ["post", "video", "story", "like", "schedule"],
        "facebook": ["post", "video", "story", "like", "schedule"],
        "weibo": ["post", "video", "like", "schedule"],
        "xiaohongshu": ["post", "video", "like", "schedule"],
        "douyin": ["post", "video", "like", "analytics", "trending", "schedule"],
        "wechat": ["post", "schedule"],
        "tiktok": ["post", "video", "like", "analytics", "trending", "schedule"],
        "linkedin": [
            "post",
            "video",
            "like",
            "repost",
            "quote",
            "dm",
            "analytics",
            "schedule",
        ],
        "threads": ["post", "video", "like", "repost", "schedule"],
    }


if __name__ == "__main__":
    mcp.run()

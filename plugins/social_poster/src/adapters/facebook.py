"""Facebook adapter."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class FacebookAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Facebook: Navigating to facebook.com...")
        await self._goto("https://www.facebook.com/")
        await self.page.wait_for_selector(
            'div:text-matches("What\'s on your mind", "i")', timeout=15000
        )
        await self.page.click('div:text-matches("What\'s on your mind", "i")')
        await asyncio.sleep(2)

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Facebook: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator('input[type="file"]').first
        await file_input.set_input_files(files)
        await asyncio.sleep(3)

    async def fill_content(self, text: str):
        print("Facebook: Filling content...")
        editor = self.page.locator('div[aria-label*="What\'s on your mind"]').first
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Facebook: Clicking post button...")
        submit_btn = self.page.locator('div[aria-label="Post"]').first
        await submit_btn.click()
        await asyncio.sleep(5)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print(f"Facebook: Deleting {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        await self.page.locator(
            'div[aria-label*="Actions for this post"]'
        ).first.click()
        await asyncio.sleep(1)
        await self.page.locator('span:has-text("Move to trash")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('div[aria-label="Move"]').first.click()
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("Facebook: Fetching my posts...")
        await self._goto("https://www.facebook.com/me")
        await asyncio.sleep(3)
        posts = await self.page.locator('div[role="article"]').all()
        results = []
        for post in posts[:limit]:
            try:
                link_el = post.locator(
                    'a[href*="/posts/"], a[href*="/permalink/"]'
                ).first
                href = (
                    await link_el.get_attribute("href")
                    if await link_el.count() > 0
                    else ""
                )
                text = await post.inner_text()
                results.append({"url": href, "snippet": text[:150]})
            except Exception:
                pass
        return results

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        """Facebook doesn't expose draft saving — compose then close without posting."""
        await self.open_platform()
        if media_paths:
            await self.upload_media(media_paths)
        await self.fill_content(content)
        # Close the composer without posting
        close_btn = self.page.locator('div[aria-label="Close"]').first
        if await close_btn.count() > 0:
            await close_btn.click()
        await asyncio.sleep(1)

    # ─── Comments ────────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"Facebook: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('div[aria-label*="Comment by"]').all()
        comments = []
        for i, el in enumerate(items):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('div[aria-label*="Comment by"]').all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('div:has-text("Reply")').first.click()
        await asyncio.sleep(1)
        await self.page.keyboard.type(text)
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('div[aria-label*="Comment by"]').all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].hover()
        await asyncio.sleep(1)
        dots = items[idx].locator('div[aria-label*="More"]').first
        if await dots.count() > 0:
            await dots.click()
            await asyncio.sleep(1)
            await self.page.locator('span:has-text("Delete")').first.click()
            await asyncio.sleep(1)
            await self.page.locator('div[aria-label="Delete"]').first.click()
            await asyncio.sleep(2)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def like_post(self, post_url: str):
        print(f"Facebook: Liking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        like_btn = self.page.locator(
            'div[aria-label="Like"], span:has-text("Like"):not(:has-text("Unlike"))'
        ).first
        await like_btn.wait_for(state="visible", timeout=5000)
        await like_btn.click()
        await asyncio.sleep(1)

    async def unlike_post(self, post_url: str):
        print(f"Facebook: Unliking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        unlike_btn = self.page.locator(
            'div[aria-label="Unlike"], span:has-text("Unlike")'
        ).first
        await unlike_btn.wait_for(state="visible", timeout=5000)
        await unlike_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        print(f"Facebook: Sharing {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        share_btn = self.page.locator(
            'div[aria-label*="Share"], span:has-text("Share")'
        ).first
        await share_btn.click()
        await asyncio.sleep(2)
        share_now = self.page.locator(
            'span:has-text("Share now"), div[aria-label="Share now"]'
        ).first
        if await share_now.count() > 0:
            await share_now.click()
        await asyncio.sleep(2)

    async def quote_post(self, post_url: str, comment: str):
        print(f"Facebook: Sharing {post_url} with comment...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        share_btn = self.page.locator('span:has-text("Share")').first
        await share_btn.click()
        await asyncio.sleep(2)
        # Select "Share to Feed" with a message
        feed_option = self.page.locator('span:has-text("Share to your feed")').first
        if await feed_option.count() > 0:
            await feed_option.click()
            await asyncio.sleep(1)
        editor = self.page.locator('div[aria-label*="Say something"]').first
        if await editor.count() > 0:
            await editor.fill(comment)
        share_now = self.page.locator('div[aria-label="Post"]').first
        await share_now.click()
        await asyncio.sleep(3)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"Facebook: Searching for '{query}'...")
        await self._goto(f"https://www.facebook.com/search/posts/?q={query}")
        await asyncio.sleep(3)
        posts = await self.page.locator('div[role="feed"] > div').all()
        results = []
        for post in posts[:10]:
            try:
                link_el = post.locator('a[role="link"]').first
                href = await link_el.get_attribute("href")
                text = await post.inner_text()
                if href:
                    results.append({"url": href, "snippet": text[:100]})
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await asyncio.sleep(2)
        el = self.page.locator('div[data-ad-preview="message"]').first
        return await el.inner_text() if await el.count() > 0 else ""

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("Facebook: Fetching trending topics...")
        await self._goto("https://www.facebook.com/")
        await asyncio.sleep(3)
        # Trending section in right sidebar
        items = await self.page.locator('span[dir="auto"]').all()
        results, seen = [], set()
        for el in items:
            try:
                text = (await el.inner_text()).strip()
                if text.startswith("#") and text not in seen:
                    seen.add(text)
                    results.append({"topic": text})
                    if len(results) >= limit:
                        break
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        print(f"Facebook: Fetching profile {username}...")
        url = (
            f"https://www.facebook.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(3)
        name_el = self.page.locator("h1").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        intro_el = self.page.locator('div[data-key="tab_profile_intro"] span').first
        intro = await intro_el.inner_text() if await intro_el.count() > 0 else ""
        return {"name": name.strip(), "intro": intro.strip(), "url": url}

    async def follow_user(self, username: str):
        print(f"Facebook: Following {username}...")
        url = (
            f"https://www.facebook.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        follow_btn = self.page.locator(
            'div[aria-label="Follow"], span:has-text("Follow")'
        ).first
        if await follow_btn.count() > 0:
            await follow_btn.click()
        await asyncio.sleep(1)

    async def send_dm(self, username: str, text: str):
        print(f"Facebook: Sending message to {username}...")
        await self._goto("https://www.facebook.com/messages/")
        await asyncio.sleep(3)
        new_btn = self.page.locator(
            'div[aria-label="New message"], a[aria-label="New message"]'
        ).first
        await new_btn.click()
        await asyncio.sleep(2)
        search = self.page.locator('input[placeholder*="Search"]').first
        await search.fill(username)
        await asyncio.sleep(2)
        result = self.page.locator(f'span:has-text("{username}")').first
        await result.click()
        await asyncio.sleep(1)
        next_btn = self.page.locator(
            'div[aria-label="Next"], button:has-text("Next")'
        ).first
        if await next_btn.count() > 0:
            await next_btn.click()
        await asyncio.sleep(2)
        msg_box = self.page.locator('div[aria-label="Message"]').first
        await msg_box.fill(text)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        print(f"Facebook: Getting analytics for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        result = {}
        react_el = self.page.locator('span[aria-label*="reaction"]').first
        result["reactions"] = (
            await react_el.inner_text() if await react_el.count() > 0 else "?"
        )
        comment_el = self.page.locator('span:has-text("comment")').first
        result["comments"] = (
            await comment_el.inner_text() if await comment_el.count() > 0 else "?"
        )
        share_el = self.page.locator('span:has-text("share")').first
        result["shares"] = (
            await share_el.inner_text() if await share_el.count() > 0 else "?"
        )
        return result

    async def get_account_analytics(self) -> dict:
        print("Facebook: Getting page insights...")
        await self._goto("https://www.facebook.com/insights/")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_insights_text": text[:3000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("Facebook: Fetching notifications...")
        await self._goto("https://www.facebook.com/notifications")
        await asyncio.sleep(3)
        items = await self.page.locator('div[role="listitem"]').all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        print("Facebook: Fetching mentions...")
        await self._goto("https://www.facebook.com/notifications")
        await asyncio.sleep(3)
        items = await self.page.locator('div[role="listitem"]').all()
        results = []
        for item in items:
            try:
                text = await item.inner_text()
                if "mentioned" in text.lower():
                    results.append({"content": text[:150]})
                    if len(results) >= limit:
                        break
            except Exception:
                pass
        return results

    # ─── Special Formats ─────────────────────────────────────────────────────

    async def post_story(self, media_paths: list, text: str = ""):
        print(f"Facebook: Posting story with {media_paths}...")
        await self._goto("https://www.facebook.com/")
        await asyncio.sleep(2)
        story_btn = self.page.locator(
            'span:has-text("Create story"), div[aria-label*="Create a story"]'
        ).first
        if await story_btn.count() == 0:
            raise Exception("Story creation button not found.")
        await story_btn.click()
        await asyncio.sleep(2)
        # Upload media
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(media_paths[:1])
        await asyncio.sleep(3)
        if text:
            text_btn = self.page.locator(
                'div[aria-label*="Text"], span:has-text("Aa")'
            ).first
            if await text_btn.count() > 0:
                await text_btn.click()
                await asyncio.sleep(1)
                editor = self.page.locator('[contenteditable="true"]').first
                await editor.fill(text)
        share_btn = self.page.locator(
            'div[aria-label*="Share to story"], button:has-text("Share to story")'
        ).first
        await share_btn.wait_for(state="visible", timeout=10000)
        await share_btn.click()
        await asyncio.sleep(3)

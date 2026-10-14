"""Instagram adapter."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class InstagramAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Instagram: Navigating to instagram.com...")
        await self._goto("https://www.instagram.com/")
        await self.page.wait_for_selector('svg[aria-label="New post"]', timeout=15000)
        await self.page.click('svg[aria-label="New post"]')
        await asyncio.sleep(1)

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Instagram: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator(
            'input[type="file"][accept*="image"], input[type="file"][accept*="video"]'
        ).first
        await file_input.set_input_files(files)
        await asyncio.sleep(2)
        # Click "Next" steps to reach caption page
        for _ in range(2):
            next_btn = self.page.locator('button:has-text("Next")').first
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(1)

    async def fill_content(self, text: str):
        print("Instagram: Filling caption...")
        editor = self.page.locator('div[aria-label="Write a caption..."]').first
        await editor.wait_for(state="visible", timeout=5000)
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Instagram: Sharing post...")
        submit_btn = self.page.locator('button:has-text("Share")').first
        await submit_btn.wait_for(state="visible", timeout=5000)
        await submit_btn.click()
        await asyncio.sleep(5)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print(f"Instagram: Deleting {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        await self.page.locator('svg[aria-label="More options"]').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()  # confirm
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("Instagram: Fetching my posts...")
        await self._goto("https://www.instagram.com/")
        await asyncio.sleep(2)
        # Navigate to own profile
        profile_link = self.page.locator(
            'a[href*="/accounts/"], nav a[role="link"]:last-child'
        ).last
        href = await profile_link.get_attribute("href")
        if href:
            await self._goto(
                f"https://www.instagram.com{href}" if href.startswith("/") else href
            )
        await asyncio.sleep(2)
        links = await self.page.locator('article a[href*="/p/"]').all()
        results = []
        for link_el in links[:limit]:
            try:
                href = await link_el.get_attribute("href")
                results.append(
                    {
                        "url": f"https://www.instagram.com{href}"
                        if href.startswith("/")
                        else href,
                        "snippet": "Instagram post",
                    }
                )
            except Exception:
                pass
        return results

    async def pin_post(self, post_url: str):
        print(f"Instagram: Pinning {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        await self.page.locator('svg[aria-label="More options"]').first.click()
        await asyncio.sleep(1)
        pin_btn = self.page.locator('button:has-text("Pin to your profile")').first
        if await pin_btn.count() == 0:
            raise Exception("Pin option not available for this post.")
        await pin_btn.click()
        await asyncio.sleep(2)

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        print("Instagram: Saving draft...")
        await self.open_platform()
        if media_paths:
            await self.upload_media(media_paths)
            await self.fill_content(content)
        # Discard — Instagram saves draft when you discard
        discard_btn = self.page.locator('button:has-text("Discard")').first
        if await discard_btn.count() > 0:
            await discard_btn.click()
        # Then save draft
        save_btn = self.page.locator('button:has-text("Save Draft")').first
        if await save_btn.count() > 0:
            await save_btn.click()
        await asyncio.sleep(1)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"Instagram: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("ul > li").all()
        comments = []
        for i, el in enumerate(items):
            try:
                text = await el.inner_text()
                comments.append({"id": str(i), "content": text[:200]})
            except Exception:
                pass
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("ul > li").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('button:has-text("Reply")').click()
        await asyncio.sleep(1)
        await self.page.locator("textarea").fill(text)
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Post")').click()
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("ul > li").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].hover()
        await asyncio.sleep(1)
        dots = items[idx].locator('svg[aria-label="More options"]').first
        if await dots.count() > 0:
            await dots.click()
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("Delete")').first.click()
            await asyncio.sleep(2)

    async def like_post(self, post_url: str):
        print(f"Instagram: Liking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        like_btn = self.page.locator(
            'svg[aria-label="Like"], button[aria-label="Like"]'
        ).first
        if await like_btn.count() == 0:
            raise Exception("Like button not found — post may already be liked.")
        await like_btn.click()
        await asyncio.sleep(1)

    async def unlike_post(self, post_url: str):
        print(f"Instagram: Unliking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        unlike_btn = self.page.locator(
            'svg[aria-label="Unlike"], button[aria-label="Unlike"]'
        ).first
        if await unlike_btn.count() == 0:
            raise Exception("Unlike button not found — post may not be liked.")
        await unlike_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        """Instagram has no native repost — shares via DM instead."""
        print(f"Instagram: Sharing {post_url} via DM...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        share_btn = self.page.locator(
            'svg[aria-label="Share Post"], button[aria-label*="Share"]'
        ).first
        await share_btn.click()
        await asyncio.sleep(2)
        # Click "Share" in the share sheet
        await self.page.locator('button:has-text("Share")').first.click()
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"Instagram: Searching #{query}...")
        await self._goto(f"https://www.instagram.com/explore/tags/{query}/")
        await asyncio.sleep(3)
        links = await self.page.locator("article a").all()
        results = []
        for link_el in links[:10]:
            try:
                href = await link_el.get_attribute("href")
                results.append(
                    {
                        "url": f"https://www.instagram.com{href}",
                        "snippet": "Instagram post",
                    }
                )
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await asyncio.sleep(2)
        el = self.page.locator("h1").first
        return await el.inner_text() if await el.count() > 0 else ""

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("Instagram: Fetching trending topics from Explore...")
        await self._goto("https://www.instagram.com/explore/")
        await asyncio.sleep(3)
        # Extract hashtags from explore page
        links = await self.page.locator('a[href*="/explore/tags/"]').all()
        seen, results = set(), []
        for link_el in links:
            try:
                href = await link_el.get_attribute("href")
                tag = href.strip("/").split("/")[-1]
                if tag and tag not in seen:
                    seen.add(tag)
                    results.append({"topic": f"#{tag}"})
                    if len(results) >= limit:
                        break
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        print(f"Instagram: Fetching profile @{username}...")
        await self._goto(f"https://www.instagram.com/{username}/")
        await asyncio.sleep(2)
        name_el = self.page.locator('h2, span[class*="username"]').first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        bio_el = self.page.locator('div[class*="biography"] span, .-vDIg span').first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        stats = {}
        for metric in ["posts", "followers", "following"]:
            el = self.page.locator(
                f'a[href*="/{metric}/"] span, span:has-text("{metric}")'
            ).first
            stats[metric] = await el.inner_text() if await el.count() > 0 else "?"
        return {"name": name.strip(), "bio": bio.strip(), **stats}

    async def follow_user(self, username: str):
        print(f"Instagram: Following @{username}...")
        await self._goto(f"https://www.instagram.com/{username}/")
        await asyncio.sleep(2)
        follow_btn = self.page.locator('button:has-text("Follow")').first
        await follow_btn.wait_for(state="visible", timeout=5000)
        await follow_btn.click()
        await asyncio.sleep(1)

    async def unfollow_user(self, username: str):
        print(f"Instagram: Unfollowing @{username}...")
        await self._goto(f"https://www.instagram.com/{username}/")
        await asyncio.sleep(2)
        following_btn = self.page.locator('button:has-text("Following")').first
        await following_btn.wait_for(state="visible", timeout=5000)
        await following_btn.click()
        await asyncio.sleep(1)
        unfollow_btn = self.page.locator('button:has-text("Unfollow")').first
        if await unfollow_btn.count() > 0:
            await unfollow_btn.click()
        await asyncio.sleep(1)

    async def block_user(self, username: str):
        await self._goto(f"https://www.instagram.com/{username}/")
        await asyncio.sleep(2)
        more_btn = self.page.locator(
            'svg[aria-label="More options"], button[aria-label="More options"]'
        ).first
        await more_btn.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Block")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Block")').first.click()  # confirm
        await asyncio.sleep(2)

    async def send_dm(self, username: str, text: str):
        print(f"Instagram: Sending DM to @{username}...")
        await self._goto(f"https://www.instagram.com/{username}/")
        await asyncio.sleep(2)
        msg_btn = self.page.locator('button:has-text("Message")').first
        if await msg_btn.count() == 0:
            await self._goto("https://www.instagram.com/direct/new/")
            await asyncio.sleep(2)
            search = self.page.locator('input[placeholder*="Search"]').first
            await search.fill(username)
            await asyncio.sleep(2)
            await self.page.locator(f'span:has-text("{username}")').first.click()
            await self.page.locator('button:has-text("Next")').first.click()
            await asyncio.sleep(1)
        else:
            await msg_btn.click()
            await asyncio.sleep(2)
        msg_input = self.page.locator(
            'div[aria-label*="Message"], textarea[placeholder*="Message"]'
        ).first
        await msg_input.wait_for(state="visible", timeout=5000)
        await msg_input.fill(text)
        await asyncio.sleep(1)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        print(f"Instagram: Getting analytics for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        result = {}
        # Like count
        like_el = self.page.locator(
            'section span:has-text("like"), a:has-text("like")'
        ).first
        result["likes"] = (
            await like_el.inner_text() if await like_el.count() > 0 else "?"
        )
        # Comment count
        comment_el = self.page.locator(
            'a[href*="/comments/"] span, ul + div span'
        ).first
        result["comments"] = (
            await comment_el.inner_text() if await comment_el.count() > 0 else "?"
        )
        return result

    async def get_account_analytics(self) -> dict:
        print("Instagram: Getting account analytics...")
        await self._goto("https://www.instagram.com/insights/")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("Instagram: Fetching notifications...")
        await self._goto("https://www.instagram.com/")
        await asyncio.sleep(2)
        notif_btn = self.page.locator(
            'svg[aria-label="Notifications"], a[href*="/notifications"]'
        ).first
        await notif_btn.click()
        await asyncio.sleep(2)
        items = await self.page.locator('[role="listitem"]').all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        print("Instagram: Fetching @mentions...")
        await self.get_notifications(limit * 2)
        # Filter from notifications (mentions appear in the notifications panel)
        items = await self.page.locator('[role="listitem"]').all()
        results = []
        for item in items:
            try:
                text = await item.inner_text()
                if "mentioned" in text.lower():
                    link_el = item.locator("a").first
                    href = (
                        await link_el.get_attribute("href")
                        if await link_el.count() > 0
                        else ""
                    )
                    results.append({"content": text[:150], "url": href})
                    if len(results) >= limit:
                        break
            except Exception:
                pass
        return results

    # ─── Special Formats ─────────────────────────────────────────────────────

    async def post_story(self, media_paths: list, text: str = ""):
        print(f"Instagram: Posting story with {media_paths}...")
        await self._goto("https://www.instagram.com/")
        await asyncio.sleep(2)
        # Click the "+" (Your Story) button in the Stories bar
        story_btn = self.page.locator(
            'button[aria-label*="Your story"], svg[aria-label*="Your story"]'
        ).first
        if await story_btn.count() == 0:
            # Try the "+" in the sidebar or Stories carousel
            story_btn = self.page.locator('a[href*="/stories/create"]').first
        if await story_btn.count() == 0:
            raise Exception(
                "Story creation button not found. Instagram UI may have changed."
            )
        await story_btn.click()
        await asyncio.sleep(2)
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(media_paths[:1])
        await asyncio.sleep(3)
        if text:
            text_btn = self.page.locator(
                'button[aria-label*="Text"], svg[aria-label*="Text"]'
            ).first
            if await text_btn.count() > 0:
                await text_btn.click()
                await asyncio.sleep(1)
                editor = self.page.locator('[contenteditable="true"]').first
                await editor.fill(text)
                await asyncio.sleep(1)
        share_btn = self.page.locator(
            'button:has-text("Share to story"), button:has-text("Send To")'
        ).first
        await share_btn.wait_for(state="visible", timeout=10000)
        await share_btn.click()
        await asyncio.sleep(3)

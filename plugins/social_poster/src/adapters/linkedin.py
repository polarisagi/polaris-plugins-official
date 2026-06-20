"""LinkedIn adapter — professional network."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class LinkedInAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("LinkedIn: Opening post composer...")
        await self._goto("https://www.linkedin.com/feed/")
        try:
            # Click the "Start a post" button
            start_btn = self.page.locator(
                'button:has-text("Start a post"), [aria-label*="Start a post"]'
            ).first
            await start_btn.wait_for(state="visible", timeout=15000)
            await start_btn.click()
            await asyncio.sleep(1)
        except Exception:
            if "login" in self.page.url or "authwall" in self.page.url:
                raise Exception(
                    "Login required for LinkedIn. Please log in manually in Chrome."
                )
            raise Exception("Failed to open LinkedIn composer. UI may have changed.")

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"LinkedIn: Uploading media {media_paths}...")
        media = split_by_type(media_paths)

        if media["images"]:
            # Click photo button in composer
            photo_btn = self.page.locator(
                'button[aria-label*="Photo"], button[aria-label*="photo"]'
            ).first
            if await photo_btn.count() > 0:
                await photo_btn.click()
                await asyncio.sleep(1)
            file_input = self.page.locator('input[type="file"][accept*="image"]').first
            await file_input.wait_for(state="attached", timeout=5000)
            await file_input.set_input_files(media["images"])
            await asyncio.sleep(4)
        elif media["videos"]:
            video_btn = self.page.locator(
                'button[aria-label*="Video"], button[aria-label*="video"]'
            ).first
            if await video_btn.count() > 0:
                await video_btn.click()
                await asyncio.sleep(1)
            file_input = self.page.locator('input[type="file"][accept*="video"]').first
            await file_input.wait_for(state="attached", timeout=5000)
            await file_input.set_input_files(media["videos"][:1])
            await asyncio.sleep(8)

    async def fill_content(self, text: str):
        print("LinkedIn: Filling content...")
        editor = self.page.locator(
            '.ql-editor, [contenteditable="true"][aria-label*="Text editor"]'
        ).first
        await editor.wait_for(state="visible", timeout=5000)
        await editor.click()
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("LinkedIn: Publishing post...")
        post_btn = self.page.locator(
            'button.share-actions__primary-action, button:has-text("Post")'
        ).first
        await post_btn.wait_for(state="visible", timeout=5000)
        await post_btn.click()
        await asyncio.sleep(4)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print(f"LinkedIn: Deleting post at {post_url}...")
        await self._goto(post_url)
        more_btn = self.page.locator(
            'button[aria-label*="More options"], button[aria-label*="Open control menu"]'
        ).first
        await more_btn.wait_for(state="visible", timeout=10000)
        await more_btn.click()
        await asyncio.sleep(1)
        await self.page.locator(
            'button:has-text("Delete post"), span:has-text("Delete post")'
        ).first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("LinkedIn: Fetching my posts...")
        await self._goto("https://www.linkedin.com/in/me/recent-activity/shares/")
        await asyncio.sleep(3)
        items = await self.page.locator(".feed-shared-update-v2").all()
        results = []
        for item in items[:limit]:
            try:
                link = await item.locator(
                    'a[data-control-name="actor"]'
                ).first.get_attribute("href")
                text = await item.locator(".feed-shared-text").first.inner_text()
                results.append(
                    {"url": f"https://www.linkedin.com{link}", "snippet": text[:150]}
                )
            except Exception:
                pass
        return results

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        print("LinkedIn: Saving draft...")
        await self.open_platform()
        await self.fill_content(content)
        if media_paths:
            await self.upload_media(media_paths)
        # LinkedIn auto-saves drafts when closing the modal; click X to save
        close_btn = self.page.locator('button[aria-label*="Dismiss"]').first
        await close_btn.click()
        save_btn = self.page.locator('button:has-text("Save")').first
        if await save_btn.count() > 0:
            await save_btn.click()
        await asyncio.sleep(1)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"LinkedIn: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator(".comments-comment-item").all()
        comments = []
        for i, el in enumerate(items):
            try:
                author = await el.locator(
                    ".comments-post-meta__name-text"
                ).first.inner_text()
                text = await el.locator(
                    ".comments-comment-item__main-content"
                ).first.inner_text()
                comments.append({"id": str(i), "author": author, "content": text[:200]})
            except Exception:
                pass
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator(".comments-comment-item").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('button:has-text("Reply")').first.click()
        await asyncio.sleep(1)
        input_box = self.page.locator(
            ".comments-comment-texteditor__contenteditable"
        ).first
        await input_box.fill(text)
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Post reply")').first.click()
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator(".comments-comment-item").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        more = items[idx].locator('button[aria-label*="more"]').first
        await more.click()
        await asyncio.sleep(0.5)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()  # confirm
        await asyncio.sleep(2)

    async def like_post(self, post_url: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        like_btn = self.page.locator(
            'button[aria-label*="Like"], button[data-control-name="like"]'
        ).first
        await like_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        repost_btn = self.page.locator(
            'button[aria-label*="Repost"], button:has-text("Repost")'
        ).first
        await repost_btn.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Repost instantly")').first.click()
        await asyncio.sleep(2)

    async def quote_post(self, post_url: str, comment: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        repost_btn = self.page.locator(
            'button[aria-label*="Repost"], button:has-text("Repost")'
        ).first
        await repost_btn.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Quote")').first.click()
        await asyncio.sleep(1)
        editor = self.page.locator('[contenteditable="true"]').first
        await editor.fill(comment)
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Post")').first.click()
        await asyncio.sleep(3)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"LinkedIn: Searching '{query}'...")
        await self._goto(
            f"https://www.linkedin.com/search/results/content/?keywords={query}"
        )
        await asyncio.sleep(3)
        items = await self.page.locator(".search-results__list li").all()
        results = []
        for item in items[:10]:
            try:
                link = await item.locator("a").first.get_attribute("href")
                text = await item.inner_text()
                results.append({"url": link, "snippet": text[:120]})
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await asyncio.sleep(2)
        el = self.page.locator(".feed-shared-text, .attributed-text-segment-list").first
        return await el.inner_text() if await el.count() > 0 else ""

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        await self._goto(f"https://www.linkedin.com/in/{username}/")
        await asyncio.sleep(2)
        name_el = self.page.locator("h1.text-heading-xlarge").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        headline_el = self.page.locator(".text-body-medium").first
        headline = (
            await headline_el.inner_text() if await headline_el.count() > 0 else ""
        )
        followers_el = self.page.locator('span:has-text("followers")').first
        followers = (
            await followers_el.inner_text() if await followers_el.count() > 0 else "?"
        )
        return {"name": name, "headline": headline, "followers": followers}

    async def follow_user(self, username: str):
        await self._goto(f"https://www.linkedin.com/in/{username}/")
        await asyncio.sleep(2)
        follow_btn = self.page.locator('button:has-text("Follow")').first
        await follow_btn.click()
        await asyncio.sleep(1)

    async def send_dm(self, username: str, text: str):
        await self._goto(f"https://www.linkedin.com/in/{username}/")
        await asyncio.sleep(2)
        msg_btn = self.page.locator('button:has-text("Message")').first
        await msg_btn.click()
        await asyncio.sleep(2)
        editor = self.page.locator(".msg-form__contenteditable").first
        await editor.wait_for(state="visible", timeout=5000)
        await editor.fill(text)
        await self.page.locator("button.msg-form__send-button").first.click()
        await asyncio.sleep(2)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        await self._goto(post_url)
        await asyncio.sleep(2)
        result = {}
        reaction_el = self.page.locator(
            ".social-details-social-counts__reactions-count"
        ).first
        result["reactions"] = (
            await reaction_el.inner_text() if await reaction_el.count() > 0 else "?"
        )
        comment_el = self.page.locator(".social-details-social-counts__comments").first
        result["comments"] = (
            await comment_el.inner_text() if await comment_el.count() > 0 else "?"
        )
        return result

    # ─── Special Formats ─────────────────────────────────────────────────────

    async def post_thread(self, tweets: list, media_paths: Optional[list] = None):
        """LinkedIn doesn't have true threads; post as a document/carousel or single post."""
        combined = "\n\n".join(tweets)
        await self.open_platform()
        if media_paths:
            await self.upload_media(media_paths)
        await self.fill_content(combined)
        await self.submit_post()

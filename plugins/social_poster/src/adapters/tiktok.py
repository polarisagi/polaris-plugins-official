"""TikTok (international) adapter — video-first platform."""

import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class TikTokAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("TikTok: Opening upload page...")
        await self._goto("https://www.tiktok.com/creator-center/upload")
        try:
            await self.page.wait_for_selector(
                'input[type="file"], .upload-btn-input', timeout=15000
            )
        except Exception:
            if "login" in self.page.url or "passport" in self.page.url:
                raise Exception(
                    "Login required for TikTok. Please log in manually in Chrome."
                )
            raise Exception("TikTok upload page failed to load. UI may have changed.")

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"TikTok: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        # TikTok prefers video; images are used for photo posts
        files = media["videos"] or media["images"]
        if not files:
            raise Exception("TikTok requires at least one video or image file.")
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(files[:1])  # TikTok: one video at a time
        # Wait for upload progress / preview
        await asyncio.sleep(8)

    async def fill_content(self, text: str):
        print("TikTok: Filling caption...")
        # TikTok caption box
        caption = self.page.locator(
            '[data-e2e="caption-input"], .public-DraftStyleDefault-block, [contenteditable="true"]'
        ).first
        await caption.wait_for(state="visible", timeout=8000)
        await caption.click()
        await caption.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("TikTok: Publishing...")
        post_btn = self.page.locator(
            'button:has-text("Post"), button:has-text("Publish")'
        ).first
        await post_btn.wait_for(state="visible", timeout=10000)
        await post_btn.click()
        await asyncio.sleep(5)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print("TikTok: Deleting post via creator center...")
        await self._goto("https://www.tiktok.com/creator-center/content")
        await asyncio.sleep(3)
        # Click the 3-dot menu on the first video matching the URL or just first video
        more_btn = self.page.locator('[data-e2e="video-manage-item"] button').first
        await more_btn.click()
        await asyncio.sleep(1)
        await self.page.locator('li:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("TikTok: Fetching my posts...")
        await self._goto("https://www.tiktok.com/creator-center/content")
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="video-manage-item"]').all()
        results = []
        for item in items[:limit]:
            try:
                link = await item.locator("a").first.get_attribute("href")
                title = await item.locator("p, span").first.inner_text()
                results.append(
                    {
                        "url": link
                        if link.startswith("http")
                        else f"https://www.tiktok.com{link}",
                        "snippet": title[:100],
                    }
                )
            except Exception:
                pass
        return results

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"TikTok: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="comment-item"]').all()
        comments = []
        for i, el in enumerate(items):
            try:
                text = await el.locator(
                    '[data-e2e="comment-level-1-user-comment"]'
                ).first.inner_text()
                author = await el.locator(
                    '[data-e2e="comment-username"]'
                ).first.inner_text()
                comments.append({"id": str(i), "author": author, "content": text[:200]})
            except Exception:
                pass
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"TikTok: Replying to comment {comment_id}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="comment-item"]').all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('span:has-text("Reply")').first.click()
        await asyncio.sleep(1)
        input_box = self.page.locator('[data-e2e="comment-input"]').first
        await input_box.fill(text)
        await asyncio.sleep(1)
        await self.page.locator('[data-e2e="comment-post"]').first.click()
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"TikTok: Deleting comment {comment_id}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="comment-item"]').all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].hover()
        await asyncio.sleep(0.5)
        await items[idx].locator('[data-e2e="comment-more"]').first.click()
        await asyncio.sleep(0.5)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()  # confirm
        await asyncio.sleep(2)

    async def like_post(self, post_url: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        await self.page.locator('[data-e2e="like-icon"]').first.click()
        await asyncio.sleep(1)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"TikTok: Searching '{query}'...")
        await self._goto(f"https://www.tiktok.com/search?q={query}")
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="search_video-item"]').all()
        results = []
        for item in items[:10]:
            try:
                link = await item.locator("a").first.get_attribute("href")
                title = await item.locator("span").first.inner_text()
                results.append(
                    {
                        "url": link
                        if link.startswith("http")
                        else f"https://www.tiktok.com{link}",
                        "snippet": title[:100],
                    }
                )
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await asyncio.sleep(2)
        desc = self.page.locator('[data-e2e="video-desc"]').first
        return await desc.inner_text() if await desc.count() > 0 else ""

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("TikTok: Fetching trending topics...")
        await self._goto("https://www.tiktok.com/explore")
        await asyncio.sleep(3)
        items = await self.page.locator('[data-e2e="challenge-item"]').all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"topic": text.strip().split("\n")[0]})
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        await self._goto(f"https://www.tiktok.com/@{username}")
        await asyncio.sleep(2)
        name_el = self.page.locator('[data-e2e="user-title"]').first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        bio_el = self.page.locator('[data-e2e="user-bio"]').first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        followers_el = self.page.locator('[data-e2e="followers-count"]').first
        followers = (
            await followers_el.inner_text() if await followers_el.count() > 0 else "?"
        )
        return {"name": name, "bio": bio, "followers": followers}

    async def follow_user(self, username: str):
        await self._goto(f"https://www.tiktok.com/@{username}")
        await asyncio.sleep(2)
        await self.page.locator('[data-e2e="follow-button"]').first.click()
        await asyncio.sleep(1)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        await self._goto(post_url)
        await asyncio.sleep(2)
        result = {}
        for metric, testid in [
            ("likes", "like-count"),
            ("comments", "comment-count"),
            ("shares", "share-count"),
        ]:
            el = self.page.locator(f'[data-e2e="{testid}"]').first
            result[metric] = await el.inner_text() if await el.count() > 0 else "?"
        return result

    async def get_account_analytics(self) -> dict:
        await self._goto("https://www.tiktok.com/creator-center/analytics/overview")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

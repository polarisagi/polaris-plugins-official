"""Threads (Meta) adapter."""

import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class ThreadsAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Threads: Opening composer...")
        await self._goto("https://www.threads.net/")
        try:
            compose_btn = self.page.locator(
                'a[href*="intent/post"], svg[aria-label*="Compose"], [aria-label*="New thread"]'
            ).first
            await compose_btn.wait_for(state="visible", timeout=15000)
            await compose_btn.click()
            await asyncio.sleep(1)
        except Exception:
            if "login" in self.page.url:
                raise Exception(
                    "Login required for Threads. Please log in manually in Chrome."
                )
            raise Exception("Failed to open Threads composer. UI may have changed.")

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Threads: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(files)
        await asyncio.sleep(4)

    async def fill_content(self, text: str):
        print("Threads: Filling content...")
        editor = self.page.locator(
            '[contenteditable="true"], textarea[placeholder*="thread"]'
        ).first
        await editor.wait_for(state="visible", timeout=8000)
        await editor.click()
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Threads: Publishing...")
        post_btn = self.page.locator('button:has-text("Post")').first
        await post_btn.wait_for(state="visible", timeout=5000)
        await post_btn.click()
        await asyncio.sleep(4)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        await self._goto(post_url)
        more_btn = self.page.locator(
            'svg[aria-label*="More"], button[aria-label*="More"]'
        ).first
        await more_btn.wait_for(state="visible", timeout=10000)
        await more_btn.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()  # confirm
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        await self._goto("https://www.threads.net/@me")
        await asyncio.sleep(3)
        items = await self.page.locator("article").all()
        results = []
        for item in items[:limit]:
            try:
                link = await item.locator('a[href*="/post/"]').first.get_attribute(
                    "href"
                )
                text = await item.locator("span").first.inner_text()
                results.append(
                    {
                        "url": f"https://www.threads.net{link}"
                        if link.startswith("/")
                        else link,
                        "snippet": text[:150],
                    }
                )
            except Exception:
                pass
        return results

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("article").all()
        comments = []
        for i, el in enumerate(items[1:]):  # skip the main post
            try:
                text = await el.locator("span").first.inner_text()
                comments.append({"id": str(i), "content": text[:200]})
            except Exception:
                pass
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("article").all()
        idx = int(comment_id) + 1
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('svg[aria-label*="Reply"]').first.click()
        await asyncio.sleep(1)
        editor = self.page.locator('[contenteditable="true"]').first
        await editor.fill(text)
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Post")').first.click()
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await asyncio.sleep(3)
        items = await self.page.locator("article").all()
        idx = int(comment_id) + 1
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        more = items[idx].locator('svg[aria-label*="More"]').first
        await more.click()
        await asyncio.sleep(0.5)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(2)

    async def like_post(self, post_url: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        await self.page.locator('svg[aria-label*="Like"]').first.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        await self._goto(post_url)
        await asyncio.sleep(2)
        await self.page.locator('svg[aria-label*="Repost"]').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Repost")').first.click()
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        await self._goto(f"https://www.threads.net/search?q={query}")
        await asyncio.sleep(3)
        items = await self.page.locator("article").all()
        results = []
        for item in items[:10]:
            try:
                link = await item.locator('a[href*="/post/"]').first.get_attribute(
                    "href"
                )
                text = await item.locator("span").first.inner_text()
                results.append(
                    {
                        "url": f"https://www.threads.net{link}"
                        if link.startswith("/")
                        else link,
                        "snippet": text[:120],
                    }
                )
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await asyncio.sleep(2)
        article = self.page.locator("article").first
        return await article.inner_text() if await article.count() > 0 else ""

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        await self._goto(f"https://www.threads.net/@{username}")
        await asyncio.sleep(2)
        name_el = self.page.locator("h1").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        bio_el = self.page.locator('span[dir="auto"]').first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        followers_el = self.page.locator('a[href*="followers"] span').first
        followers = (
            await followers_el.inner_text() if await followers_el.count() > 0 else "?"
        )
        return {"name": name, "bio": bio, "followers": followers}

    async def follow_user(self, username: str):
        await self._goto(f"https://www.threads.net/@{username}")
        await asyncio.sleep(2)
        await self.page.locator('button:has-text("Follow")').first.click()
        await asyncio.sleep(1)

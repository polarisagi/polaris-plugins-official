"""Douyin (抖音) adapter — video-first Chinese platform."""

import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class DouyinAdapter(BaseAdapter):
    async def open_platform(self):
        print("Douyin: Navigating to creator center...")
        await self.page.goto(
            "https://creator.douyin.com/creator-micro/content/upload",
            wait_until="domcontentloaded",
        )
        await self.page.wait_for_selector(".upload-btn-input", timeout=15000)

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Douyin: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["videos"] or media["images"]
        if not files:
            raise Exception("Douyin requires at least one video or image file.")
        file_input = self.page.locator(
            'input[type="file"][accept*="video"], input[type="file"][accept*="image"]'
        ).first
        await file_input.set_input_files(files[:1])
        await asyncio.sleep(6)  # wait for upload processing

    async def fill_content(self, text: str):
        print("Douyin: Filling content...")
        editor = self.page.locator(".editor-kit-editor")
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Douyin: Clicking post button...")
        submit_btn = self.page.locator('button:has-text("发布")')
        await submit_btn.click()
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"Douyin: Navigating to {post_url} to delete...")
        await self.page.goto(
            "https://creator.douyin.com/creator-micro/content/manage",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(3)
        await self.page.locator('div:has-text("删除")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确定")').first.click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Douyin: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        comments_elements = await self.page.locator(
            'div[data-e2e="comment-item"]'
        ).all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Douyin: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        comments_elements = await self.page.locator(
            'div[data-e2e="comment-item"]'
        ).all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('span:has-text("回复")').click()
            await asyncio.sleep(1)
            await self.page.locator('div[data-e2e="comment-input"]').fill(text)
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("发送")').click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Douyin: Deleting comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        comments_elements = await self.page.locator(
            'div[data-e2e="comment-item"]'
        ).all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].hover()
            await asyncio.sleep(1)
            await comments_elements[idx].locator('span:has-text("删除")').first.click()
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("确定")').first.click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Douyin: Searching for {query}...")
        await self.page.goto(
            f"https://www.douyin.com/search/{query}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)
        videos = await self.page.locator("ul > li").all()
        results = []
        for vid in videos[:10]:
            try:
                link = await vid.locator("a").first.get_attribute("href")
                title = await vid.inner_text()
                if link and link.startswith("//"):
                    link = "https:" + link
                results.append({"url": link, "snippet": title[:100]})
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Douyin: Reading {post_url}...")
        await self.page.goto(post_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        return await self.page.locator("h1").first.inner_text()

    async def like_post(self, post_url: str):
        await self.page.goto(post_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self.page.locator('[data-e2e="like-icon"]').first.click()
        await asyncio.sleep(1)

    async def get_user_profile(self, username: str) -> dict:
        await self.page.goto(
            f"https://www.douyin.com/user/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(2)
        name_el = self.page.locator('[data-e2e="user-info-nickName"]').first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        fans_el = self.page.locator('[data-e2e="user-info-fans"]').first
        fans = await fans_el.inner_text() if await fans_el.count() > 0 else "?"
        return {"name": name, "fans": fans}

    async def follow_user(self, username: str):
        await self.page.goto(
            f"https://www.douyin.com/user/{username}", wait_until="domcontentloaded"
        )
        await asyncio.sleep(2)
        await self.page.locator('button:has-text("关注")').first.click()
        await asyncio.sleep(1)

    async def get_post_analytics(self, post_url: str) -> dict:
        await self.page.goto(post_url, wait_until="domcontentloaded")
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

    async def get_my_posts(self, limit: int = 10) -> list:
        await self.page.goto(
            "https://creator.douyin.com/creator-micro/content/manage",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(3)
        items = await self.page.locator(".video-item").all()
        results = []
        for item in items[:limit]:
            try:
                link = await item.locator("a").first.get_attribute("href")
                title = await item.locator(".title").first.inner_text()
                results.append(
                    {"url": f"https://www.douyin.com{link}", "snippet": title[:100]}
                )
            except Exception:
                pass
        return results

    async def get_trending_topics(self, limit: int = 10) -> list:
        await self.page.goto(
            "https://www.douyin.com/hot", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)
        items = await self.page.locator(".board-item").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"topic": text.strip().split("\n")[0]})
            except Exception:
                pass
        return results

    async def get_account_analytics(self) -> dict:
        await self.page.goto(
            "https://creator.douyin.com/creator-micro/data/overview",
            wait_until="domcontentloaded",
        )
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

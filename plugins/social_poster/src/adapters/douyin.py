from .base_adapter import BaseAdapter
import asyncio

class DouyinAdapter(BaseAdapter):
    async def open_platform(self):
        print("Douyin: Navigating to creator center...")
        await self.page.goto('https://creator.douyin.com/creator-micro/content/upload', wait_until='domcontentloaded')
        await self.page.wait_for_selector('.upload-btn-input', timeout=15000)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Douyin: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][accept*="video"], input[type="file"][accept*="image"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(4)

    async def fill_content(self, text: str):
        print("Douyin: Filling content...")
        editor = self.page.locator('.editor-kit-editor')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Douyin: Clicking post button...")
        submit_btn = self.page.locator('button:has-text("发布")')
        await submit_btn.click()
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"Douyin: Navigating to {post_url} to delete...")
        await self.page.goto('https://creator.douyin.com/creator-micro/content/manage', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await self.page.locator('div:has-text("删除")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确定")').first.click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Douyin: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('div[data-e2e="comment-item"]').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Douyin: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('div[data-e2e="comment-item"]').all()
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

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Douyin: Searching for {query}...")
        await self.page.goto(f"https://www.douyin.com/search/{query}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        videos = await self.page.locator('ul > li').all()
        results = []
        for vid in videos[:10]:
            try:
                link = await vid.locator('a').first.get_attribute('href')
                title = await vid.inner_text()
                if link and link.startswith('//'): link = "https:" + link
                results.append({"url": link, "snippet": title[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Douyin: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        return await self.page.locator('h1').first.inner_text()

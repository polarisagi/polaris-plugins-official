from .base_adapter import BaseAdapter
import asyncio

class XiaohongshuAdapter(BaseAdapter):
    async def open_platform(self):
        print("Xiaohongshu: Navigating to creator center...")
        await self.page.goto('https://creator.xiaohongshu.com/publish/publish', wait_until='domcontentloaded')
        # Wait for the upload container to appear
        await self.page.wait_for_selector('.upload-container', timeout=15000)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Xiaohongshu: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][accept*="image"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(3) # Wait for images to render

    async def fill_content(self, text: str):
        print("Xiaohongshu: Filling content...")
        # Fill title and content. Assuming 'text' contains both, we might just fill content or split by first newline.
        # For simplicity, filling the main editor:
        editor = self.page.locator('.post-content-container .ql-editor')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Xiaohongshu: Clicking post button...")
        submit_btn = self.page.locator('button.submit-btn, button:has-text("发布")')
        await submit_btn.click()
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"Xiaohongshu: Navigating to {post_url} to delete...")
        # Usually delete happens in creator center
        await self.page.goto('https://creator.xiaohongshu.com/creator/notes', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        # Assuming post_url or ID can be found in the list, for simplicity clicking first delete
        await self.page.locator('text="删除"').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确定")').first.click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Xiaohongshu: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('.comment-item').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Xiaohongshu: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('.comment-item').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('.reply-btn').click()
            await asyncio.sleep(1)
            await self.page.locator('.comment-input').fill(text)
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("发送")').click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Xiaohongshu: Searching for {query}...")
        await self.page.goto(f"https://www.xiaohongshu.com/search_result?keyword={query}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        notes = await self.page.locator('.note-item').all()
        results = []
        for note in notes[:10]:
            try:
                link = await note.locator('a').first.get_attribute('href')
                title = await note.locator('.title').first.inner_text()
                results.append({"url": f"https://www.xiaohongshu.com{link}", "snippet": title})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Xiaohongshu: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.desc', timeout=10000)
        return await self.page.locator('.desc').first.inner_text()

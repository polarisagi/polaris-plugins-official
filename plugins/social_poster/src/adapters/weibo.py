from .base_adapter import BaseAdapter
import asyncio

class WeiboAdapter(BaseAdapter):
    async def open_platform(self):
        print("Weibo: Navigating to weibo.com...")
        await self.page.goto('https://weibo.com/', wait_until='domcontentloaded')
        await self.page.wait_for_selector('textarea[title="微博输入框"]', timeout=15000)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Weibo: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][accept*="image"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(2)

    async def fill_content(self, text: str):
        print("Weibo: Filling content...")
        editor = self.page.locator('textarea[title="微博输入框"]')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Weibo: Clicking post button...")
        submit_btn = self.page.locator('button[title="发布"]')
        await submit_btn.click()
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"Weibo: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        # Weibo uses a dropdown for delete
        await self.page.locator('i.icon-arrow-down').first.click()
        await asyncio.sleep(1)
        await self.page.locator('a:has-text("删除")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('a[action-type="ok"]').click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Weibo: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3) # Wait for comments to load
        comments_elements = await self.page.locator('.list_li').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Weibo: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('.list_li').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('a:has-text("回复")').click()
            await asyncio.sleep(1)
            await comments_elements[idx].locator('textarea').fill(text)
            await asyncio.sleep(1)
            await comments_elements[idx].locator('a:has-text("评论")').click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Weibo: Searching for {query}...")
        await self.page.goto(f"https://s.weibo.com/weibo?q={query}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        cards = await self.page.locator('.card-wrap').all()
        results = []
        for card in cards[:10]:
            try:
                link = await card.locator('.from a').first.get_attribute('href')
                text = await card.locator('.txt').first.inner_text()
                if link and not link.startswith('http'): link = "https:" + link
                results.append({"url": link, "snippet": text[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Weibo: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.detail_wbtext_4CRf9', timeout=10000)
        return await self.page.locator('.detail_wbtext_4CRf9').first.inner_text()

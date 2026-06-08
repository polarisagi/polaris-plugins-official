from .base_adapter import BaseAdapter
import asyncio

class WechatAdapter(BaseAdapter):
    async def open_platform(self):
        print("WeChat: Navigating to Official Accounts platform...")
        await self.page.goto('https://mp.weixin.qq.com/', wait_until='domcontentloaded')
        await self.page.wait_for_selector('.weui-desktop-rich-editor', timeout=15000)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"WeChat: Uploading media {image_paths}...")
        # WeChat media upload is complex, typically involves clicking insert image then file input
        file_input = self.page.locator('input[type="file"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(3)

    async def fill_content(self, text: str):
        print("WeChat: Filling content into editor...")
        editor = self.page.locator('.weui-desktop-rich-editor')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("WeChat: Clicking post button...")
        submit_btn = self.page.locator('button:has-text("群发"), button:has-text("发布")').first
        await submit_btn.click()
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"WeChat: Navigating to publish history to delete...")
        await self.page.goto('https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await self.page.locator('a.weui-desktop-icon-btn_delete').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确认")').first.click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"WeChat: Fetching comments in backend...")
        await self.page.goto('https://mp.weixin.qq.com/misc/appmsgcomment', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('.weui-desktop-table__row').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"WeChat: Replying to comment {comment_id}...")
        await self.page.goto('https://mp.weixin.qq.com/misc/appmsgcomment', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('.weui-desktop-table__row').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('a:has-text("回复")').first.click()
            await asyncio.sleep(1)
            await self.page.locator('textarea.weui-desktop-form__textarea').first.fill(text)
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("发送")').first.click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"WeChat: Searching for {query} via Sogou...")
        await self.page.goto(f"https://weixin.sogou.com/weixin?type=2&query={query}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        articles = await self.page.locator('.news-list li').all()
        results = []
        for art in articles[:10]:
            try:
                link = await art.locator('h3 a').first.get_attribute('href')
                title = await art.locator('h3').first.inner_text()
                if link and link.startswith('/link'): link = "https://weixin.sogou.com" + link
                results.append({"url": link, "snippet": title})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"WeChat: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('#js_content', timeout=10000)
        return await self.page.locator('#js_content').first.inner_text()

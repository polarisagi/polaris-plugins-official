from .base_adapter import BaseAdapter
import asyncio

class WeiboAdapter(BaseAdapter):
    async def open_platform(self):
        print("Weibo: Navigating to composer...")
        await self.page.goto('https://weibo.com', wait_until='domcontentloaded')
        
        try:
            await self.page.wait_for_selector('textarea[title="微博输入框"], .Form_input_3JT2Q', timeout=10000, state='visible')
        except:
            if "login" in self.page.url or await self.page.locator('a[action-type="login"]').count() > 0:
                raise Exception("Login required for Weibo. Please login manually in Chrome first.")
            else:
                raise Exception("Failed to load Weibo composer. The UI might have changed.")

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Weibo: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][accept*="image"]').first
        await file_input.wait_for(state='attached', timeout=5000)
        await file_input.set_input_files(image_paths)
        # Wait for thumbnail
        await self.page.wait_for_selector('.woo-picture-main', timeout=15000, state='visible')

    async def fill_content(self, text: str):
        print("Weibo: Filling content...")
        textbox = self.page.locator('textarea[title="微博输入框"], .Form_input_3JT2Q').first
        await textbox.wait_for(state='visible', timeout=5000)
        await textbox.fill(text)

    async def submit_post(self):
        print("Weibo: Clicking post button...")
        submit_btn = self.page.locator('button.Tool_btn_2EHg0, button:has-text("发送")').first
        await submit_btn.wait_for(state='visible', timeout=5000)
        await submit_btn.click()
        await self.page.wait_for_selector('.woo-toast', timeout=10000, state='visible')

    async def delete_post(self, post_url: str):
        print(f"Weibo: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        
        arrow_btn = self.page.locator('.woo-pop-ctrl').first
        await arrow_btn.wait_for(state='visible', timeout=10000)
        await arrow_btn.click()
        
        delete_btn = self.page.locator('text="删除"').first
        await delete_btn.wait_for(state='visible', timeout=5000)
        await delete_btn.click()
        
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state='visible', timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state='hidden', timeout=5000)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Weibo: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.list_li', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.list_li').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.locator('.text').first.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Weibo: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.list_li', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.list_li').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            reply_btn = comments_elements[idx].locator('a:has-text("回复")').first
            await reply_btn.click()
            
            input_box = comments_elements[idx].locator('textarea').first
            await input_box.wait_for(state='visible', timeout=5000)
            await input_box.fill(text)
            
            send_btn = comments_elements[idx].locator('button:has-text("回复")').first
            await send_btn.click()
            await input_box.wait_for(state='hidden', timeout=5000)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Weibo: Deleting comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.list_li', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.list_li').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].hover()
            
            delete_btn = comments_elements[idx].locator('a:has-text("删除")').first
            await delete_btn.wait_for(state='visible', timeout=5000)
            await delete_btn.click()
            
            confirm_btn = self.page.locator('button:has-text("确定")').first
            await confirm_btn.wait_for(state='visible', timeout=5000)
            await confirm_btn.click()
            await confirm_btn.wait_for(state='hidden', timeout=5000)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Weibo: Searching for {query}...")
        await self.page.goto(f"https://s.weibo.com/weibo?q={query}", wait_until='domcontentloaded')
        await self.page.wait_for_selector('.card-wrap', timeout=10000, state='visible')
        notes = await self.page.locator('.card-wrap').all()
        results = []
        for note in notes[:10]:
            try:
                link = await note.locator('a[from="weibo"]').first.get_attribute('href')
                if not link.startswith('http'):
                    link = "https:" + link
                title = await note.locator('.txt').first.inner_text()
                results.append({"url": link, "snippet": title[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Weibo: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.detail_txt', timeout=10000, state='visible')
        return await self.page.locator('.detail_txt').first.inner_text()

from .base_adapter import BaseAdapter
import asyncio

class XiaohongshuAdapter(BaseAdapter):
    async def open_platform(self):
        print("Xiaohongshu: Navigating to creator center...")
        await self.page.goto('https://creator.xiaohongshu.com/publish/publish', wait_until='domcontentloaded')
        
        try:
            await self.page.wait_for_selector('.upload-container', timeout=10000, state='visible')
        except:
            if "login" in self.page.url or await self.page.locator('text="登录"').count() > 0:
                raise Exception("Login required for Xiaohongshu. Please login manually in Chrome first.")
            else:
                raise Exception("Failed to load Xiaohongshu creator center. The UI might have changed.")

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Xiaohongshu: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][accept*="image"]').first
        await file_input.wait_for(state='attached', timeout=5000)
        await file_input.set_input_files(image_paths)
        # Wait for images to render (image previews appear)
        await self.page.wait_for_selector('.image-preview, .preview-container', timeout=15000, state='visible')

    async def fill_content(self, text: str):
        print("Xiaohongshu: Filling content...")
        editor = self.page.locator('.post-content-container .ql-editor').first
        await editor.wait_for(state='visible', timeout=5000)
        await editor.fill(text)

    async def submit_post(self):
        print("Xiaohongshu: Clicking post button...")
        submit_btn = self.page.locator('button.submit-btn, button:has-text("发布")').first
        await submit_btn.wait_for(state='visible', timeout=5000)
        await submit_btn.click()
        # Wait for success toast or redirect
        await self.page.wait_for_url('**/creator/notes**', timeout=15000)

    async def delete_post(self, post_url: str):
        print(f"Xiaohongshu: Navigating to {post_url} to delete...")
        await self.page.goto('https://creator.xiaohongshu.com/creator/notes', wait_until='domcontentloaded')
        
        delete_btn = self.page.locator('text="删除"').first
        await delete_btn.wait_for(state='visible', timeout=10000)
        await delete_btn.click()
        
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state='visible', timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state='hidden', timeout=5000)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Xiaohongshu: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.comment-item', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.comment-item').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Xiaohongshu: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.comment-item', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.comment-item').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            reply_btn = comments_elements[idx].locator('.reply-btn')
            await reply_btn.click()
            
            input_box = self.page.locator('.comment-input').first
            await input_box.wait_for(state='visible', timeout=5000)
            await input_box.fill(text)
            
            send_btn = self.page.locator('button:has-text("发送")').first
            await send_btn.click()
            await input_box.wait_for(state='hidden', timeout=5000)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Xiaohongshu: Deleting comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('.comment-item', timeout=10000, state='visible')
        comments_elements = await self.page.locator('.comment-item').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].hover()
            
            delete_btn = comments_elements[idx].locator('span:has-text("删除"), svg.delete-icon').first
            await delete_btn.wait_for(state='visible', timeout=5000)
            await delete_btn.click()
            
            confirm_btn = self.page.locator('button:has-text("确定")').first
            await confirm_btn.wait_for(state='visible', timeout=5000)
            await confirm_btn.click()
            await confirm_btn.wait_for(state='hidden', timeout=5000)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Xiaohongshu: Searching for {query}...")
        await self.page.goto(f"https://www.xiaohongshu.com/search_result?keyword={query}", wait_until='domcontentloaded')
        await self.page.wait_for_selector('.note-item', timeout=10000, state='visible')
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
        await self.page.wait_for_selector('.desc', timeout=10000, state='visible')
        return await self.page.locator('.desc').first.inner_text()

from .base_adapter import BaseAdapter
import asyncio

class FacebookAdapter(BaseAdapter):
    async def open_platform(self):
        print("Facebook: Navigating to facebook.com...")
        await self.page.goto('https://www.facebook.com/', wait_until='domcontentloaded')
        # Click the "What's on your mind?" button
        await self.page.wait_for_selector('div:text-matches("What\'s on your mind", "i")', timeout=15000)
        await self.page.click('div:text-matches("What\'s on your mind", "i")')
        await asyncio.sleep(2)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Facebook: Uploading media {image_paths}...")
        # Facebook has an add photo/video button in the composer
        file_input = self.page.locator('input[type="file"][accept*="image"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(3)

    async def fill_content(self, text: str):
        print("Facebook: Filling content...")
        # The composer text area
        editor = self.page.locator('div[aria-label*="What\'s on your mind"]')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Facebook: Clicking post button...")
        submit_btn = self.page.locator('div[aria-label="Post"]')
        await submit_btn.click()
        await asyncio.sleep(5)

    async def delete_post(self, post_url: str):
        print(f"Facebook: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await self.page.locator('div[aria-label*="Actions for this post"]').first.click()
        await asyncio.sleep(1)
        await self.page.locator('span:has-text("Move to trash")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('div[aria-label="Move"]').first.click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Facebook: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        # Highly heuristic selector for FB comments
        comments_elements = await self.page.locator('div[aria-label*="Comment by"]').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Facebook: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('div[aria-label*="Comment by"]').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('div:has-text("Reply")').first.click()
            await asyncio.sleep(1)
            await self.page.keyboard.type(text) # FB uses contenteditable, keyboard type is safer
            await asyncio.sleep(1)
            await self.page.keyboard.press('Enter')
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Facebook: Deleting comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('div[aria-label*="Comment by"]').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].hover()
            await asyncio.sleep(1)
            dots = comments_elements[idx].locator('div[aria-label*="More"]').first
            if await dots.count() > 0:
                await dots.click()
                await asyncio.sleep(1)
                await self.page.locator('span:has-text("Delete")').first.click()
                await asyncio.sleep(1)
                await self.page.locator('div[aria-label="Delete"]').first.click()
                await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Facebook: Searching for {query}...")
        await self.page.goto(f"https://www.facebook.com/search/posts/?q={query}", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        posts = await self.page.locator('div[role="feed"] > div').all()
        results = []
        for post in posts[:10]:
            try:
                link = await post.locator('a[role="link"]').first.get_attribute('href')
                text = await post.inner_text()
                if link: results.append({"url": link, "snippet": text[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Facebook: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        return await self.page.locator('div[data-ad-preview="message"]').first.inner_text()

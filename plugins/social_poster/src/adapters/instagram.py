from .base_adapter import BaseAdapter
import asyncio

class InstagramAdapter(BaseAdapter):
    async def open_platform(self):
        print("Instagram: Navigating to instagram.com...")
        await self.page.goto('https://www.instagram.com/', wait_until='domcontentloaded')
        # Instagram's "New post" button in the sidebar
        await self.page.wait_for_selector('svg[aria-label="New post"]', timeout=15000)
        await self.page.click('svg[aria-label="New post"]')
        await asyncio.sleep(1)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Instagram: Uploading media {image_paths}...")
        # Instagram uses a file input for dragging and dropping photos
        file_input = self.page.locator('input[type="file"][accept*="image"], input[type="file"][accept*="video"]')
        await file_input.set_input_files(image_paths)
        await asyncio.sleep(2)
        # Usually need to click "Next" twice to get to caption
        next_button = self.page.locator('button:has-text("Next")')
        if await next_button.count() > 0:
            await next_button.first.click()
            await asyncio.sleep(1)
            await next_button.first.click()
            await asyncio.sleep(1)

    async def fill_content(self, text: str):
        print("Instagram: Filling content...")
        editor = self.page.locator('div[aria-label="Write a caption..."]')
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Instagram: Clicking post button...")
        submit_btn = self.page.locator('button:has-text("Share")')
        await submit_btn.click()
        await asyncio.sleep(5)

    async def delete_post(self, post_url: str):
        print(f"Instagram: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        await self.page.locator('svg[aria-label="More options"]').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("Delete")').first.click() # confirm
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Instagram: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('ul > li').all()
        comments = []
        for i, el in enumerate(comments_elements):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Instagram: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('ul > li').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].locator('button:has-text("Reply")').click()
            await asyncio.sleep(1)
            await self.page.locator('textarea').fill(text)
            await asyncio.sleep(1)
            await self.page.locator('button:has-text("Post")').click()
            await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Instagram: Deleting comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(3)
        comments_elements = await self.page.locator('ul > li').all()
        idx = int(comment_id)
        if idx < len(comments_elements):
            await comments_elements[idx].hover()
            await asyncio.sleep(1)
            # Instagram comment delete is under a 3-dot menu or a delete icon
            dots_btn = comments_elements[idx].locator('svg[aria-label="More options"]').first
            if await dots_btn.count() > 0:
                await dots_btn.click()
                await asyncio.sleep(1)
                await self.page.locator('button:has-text("Delete")').first.click()
                await asyncio.sleep(2)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Instagram: Searching for {query} via explore tags...")
        await self.page.goto(f"https://www.instagram.com/explore/tags/{query}/", wait_until='domcontentloaded')
        await asyncio.sleep(3)
        links = await self.page.locator('article a').all()
        results = []
        for link_el in links[:10]:
            try:
                href = await link_el.get_attribute('href')
                results.append({"url": f"https://www.instagram.com{href}", "snippet": "Instagram post"})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Instagram: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        return await self.page.locator('h1').first.inner_text()

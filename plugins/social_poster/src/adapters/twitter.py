from .base_adapter import BaseAdapter
import asyncio

class TwitterAdapter(BaseAdapter):
    async def open_platform(self):
        print("Twitter: Navigating to compose tweet page...")
        await self.page.goto('https://twitter.com/compose/tweet', wait_until='domcontentloaded')
        # Wait for the tweet composer to appear
        await self.page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=10000)

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Twitter: Uploading media {image_paths}...")
        # In Twitter, there's usually a hidden input for file upload
        file_input = self.page.locator('input[type="file"][data-testid="fileInput"]').first
        await file_input.set_input_files(image_paths)
        # Wait a moment for upload to process
        await asyncio.sleep(2)

    async def fill_content(self, text: str):
        print("Twitter: Filling content...")
        # The tweet input is a contenteditable div
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("Twitter: Clicking post button...")
        button = self.page.locator('[data-testid="tweetButton"]').first
        await button.click()
        # Wait for the tweet to send
        await asyncio.sleep(3)

    async def delete_post(self, post_url: str):
        print(f"Twitter: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="caret"]', timeout=10000)
        await self.page.locator('[data-testid="caret"]').first.click()
        await asyncio.sleep(1)
        await self.page.locator('menuitem:has-text("Delete")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('[data-testid="confirmationSheetConfirm"]').click()
        await asyncio.sleep(2)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Twitter: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        # The first tweet is usually the main post, the rest are comments
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        comments = []
        for i, tweet in enumerate(tweets[1:]): # skip main post
            text = await tweet.inner_text()
            comments.append({"id": str(i), "content": text[:200] + "..." if len(text) > 200 else text})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Twitter: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        idx = int(comment_id) + 1 # offset by 1 because of main post
        if idx < len(tweets):
            reply_btn = tweets[idx].locator('[data-testid="reply"]')
            await reply_btn.click()
            await asyncio.sleep(1)
            textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
            await textbox.fill(text)
            await asyncio.sleep(1)
            await self.page.locator('[data-testid="tweetButton"]').first.click()
            await asyncio.sleep(3)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Twitter: Searching for {query}...")
        await self.page.goto(f"https://twitter.com/search?q={query}&f=live", wait_until='domcontentloaded')
        await asyncio.sleep(5) # wait for search results
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        results = []
        for tweet in tweets[:10]:
            try:
                # find the timestamp link which is usually the post URL
                link = await tweet.locator('a[dir="ltr"]:has(time)').first.get_attribute('href')
                text = await tweet.inner_text()
                results.append({"url": f"https://twitter.com{link}", "snippet": text[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Twitter: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweetText"]', timeout=10000)
        return await self.page.locator('[data-testid="tweetText"]').first.inner_text()

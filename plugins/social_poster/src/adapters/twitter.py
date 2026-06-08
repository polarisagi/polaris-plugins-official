from .base_adapter import BaseAdapter
import asyncio

class TwitterAdapter(BaseAdapter):
    async def open_platform(self):
        print("Twitter: Navigating to compose tweet page...")
        await self.page.goto('https://twitter.com/compose/tweet', wait_until='domcontentloaded')
        
        # Check for login redirect
        try:
            # If the URL changes to login or we see the login input, we are logged out.
            # Using a short timeout to check if the tweet textarea appears. If it doesn't, check login state.
            await self.page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=8000, state='visible')
        except:
            if "login" in self.page.url or await self.page.locator('input[autocomplete="username"]').count() > 0:
                raise Exception("Login required for Twitter. Please login manually in Chrome first.")
            else:
                raise Exception("Failed to load Twitter compose page. The UI might have changed or network is slow.")

    async def upload_media(self, image_paths: list[str]):
        if not image_paths:
            return
        print(f"Twitter: Uploading media {image_paths}...")
        file_input = self.page.locator('input[type="file"][data-testid="fileInput"]').first
        await file_input.wait_for(state='attached', timeout=5000)
        await file_input.set_input_files(image_paths)
        # Wait for the media thumbnail to appear indicating upload finished
        await self.page.wait_for_selector('[data-testid="attachments"]', timeout=15000, state='visible')

    async def fill_content(self, text: str):
        print("Twitter: Filling content...")
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.wait_for(state='visible', timeout=5000)
        await textbox.fill(text)

    async def submit_post(self):
        print("Twitter: Clicking post button...")
        button = self.page.locator('[data-testid="tweetButton"]').first
        await button.wait_for(state='visible', timeout=5000)
        await button.click()
        # Wait for the composer to disappear
        await self.page.wait_for_selector('[data-testid="tweetTextarea_0"]', state='hidden', timeout=10000)

    async def delete_post(self, post_url: str):
        print(f"Twitter: Navigating to {post_url} to delete...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        
        caret = self.page.locator('[data-testid="caret"]').first
        await caret.wait_for(state='visible', timeout=10000)
        await caret.click()
        
        delete_btn = self.page.locator('menuitem:has-text("Delete")').first
        await delete_btn.wait_for(state='visible', timeout=5000)
        await delete_btn.click()
        
        confirm_btn = self.page.locator('[data-testid="confirmationSheetConfirm"]')
        await confirm_btn.wait_for(state='visible', timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state='hidden', timeout=5000)

    async def get_comments(self, post_url: str) -> list[dict]:
        print(f"Twitter: Fetching comments for {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000, state='visible')
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        comments = []
        for i, tweet in enumerate(tweets[1:]): # skip main post
            text = await tweet.inner_text()
            comments.append({"id": str(i), "content": text[:200] + "..." if len(text) > 200 else text})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Twitter: Replying to comment {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000, state='visible')
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        idx = int(comment_id) + 1
        if idx < len(tweets):
            reply_btn = tweets[idx].locator('[data-testid="reply"]')
            await reply_btn.click()
            
            textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
            await textbox.wait_for(state='visible', timeout=5000)
            await textbox.fill(text)
            
            button = self.page.locator('[data-testid="tweetButton"]').first
            await button.click()
            await textbox.wait_for(state='hidden', timeout=10000)
        else:
            raise Exception("Comment ID not found.")

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Twitter: Hiding reply {comment_id} on {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000, state='visible')
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        idx = int(comment_id) + 1
        if idx < len(tweets):
            caret = tweets[idx].locator('[data-testid="caret"]')
            await caret.click()
            
            hide_btn = self.page.locator('menuitem:has-text("Hide reply"), menuitem:has-text("Hide")').first
            await hide_btn.wait_for(state='visible', timeout=5000)
            await hide_btn.click()
            # Wait for confirmation dialog if any, or just wait for menu to close
            await hide_btn.wait_for(state='hidden', timeout=5000)
        else:
            raise Exception("Comment ID not found.")

    async def search_posts(self, query: str) -> list[dict]:
        print(f"Twitter: Searching for {query}...")
        await self.page.goto(f"https://twitter.com/search?q={query}&f=live", wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweet"]', timeout=15000, state='visible')
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        results = []
        for tweet in tweets[:10]:
            try:
                link = await tweet.locator('a[dir="ltr"]:has(time)').first.get_attribute('href')
                text = await tweet.inner_text()
                results.append({"url": f"https://twitter.com{link}", "snippet": text[:100]})
            except:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Twitter: Reading {post_url}...")
        await self.page.goto(post_url, wait_until='domcontentloaded')
        await self.page.wait_for_selector('[data-testid="tweetText"]', timeout=10000, state='visible')
        return await self.page.locator('[data-testid="tweetText"]').first.inner_text()

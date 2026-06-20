"""Twitter / X adapter."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class TwitterAdapter(BaseAdapter):
    # ─── Helpers ─────────────────────────────────────────────────────────────

    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        try:
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    async def _wait(self, selector: str, timeout: int = 10000):
        await self.page.wait_for_selector(selector, state="visible", timeout=timeout)

    async def _click(self, selector: str):
        el = self.page.locator(selector).first
        await el.wait_for(state="visible", timeout=5000)
        await el.click()

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Twitter: Opening tweet composer...")
        await self._goto("https://twitter.com/compose/tweet")
        try:
            await self._wait('[data-testid="tweetTextarea_0"]', timeout=8000)
        except Exception:
            if "login" in self.page.url:
                raise Exception(
                    "Login required for Twitter. Please log in manually in Chrome."
                )
            raise Exception("Failed to open Twitter composer. The UI may have changed.")

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Twitter: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        # Upload images first (up to 4), then video (only 1 allowed)
        to_upload = (media["images"] + media["videos"])[:4]
        if not to_upload:
            return
        file_input = self.page.locator(
            'input[type="file"][data-testid="fileInput"]'
        ).first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(to_upload)
        await self._wait('[data-testid="attachments"]', timeout=20000)

    async def fill_content(self, text: str):
        print("Twitter: Filling content...")
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.wait_for(state="visible", timeout=5000)
        await textbox.fill(text)

    async def submit_post(self):
        print("Twitter: Submitting post...")
        await self._click('[data-testid="tweetButton"]')
        await self.page.wait_for_selector(
            '[data-testid="tweetTextarea_0"]', state="hidden", timeout=15000
        )

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print(f"Twitter: Deleting {post_url}...")
        await self._goto(post_url)
        await self._click('[data-testid="caret"]')
        await self._click('menuitem:has-text("Delete")')
        await self._click('[data-testid="confirmationSheetConfirm"]')
        await self.page.wait_for_selector(
            '[data-testid="confirmationSheetConfirm"]', state="hidden", timeout=5000
        )

    async def edit_post(self, post_url: str, new_content: str):
        """Twitter supports post editing (Premium accounts)."""
        print(f"Twitter: Editing {post_url}...")
        await self._goto(post_url)
        await self._click('[data-testid="caret"]')
        edit_btn = self.page.locator('menuitem:has-text("Edit")').first
        if await edit_btn.count() == 0:
            raise Exception(
                "Edit not available — account may not have Twitter Blue/Premium."
            )
        await edit_btn.click()
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.wait_for(state="visible", timeout=5000)
        await textbox.fill(new_content)
        await self._click('[data-testid="tweetButton"]')
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("Twitter: Fetching my posts...")
        # Navigate to home profile (requires knowing handle — use /home to find profile link)
        await self._goto("https://twitter.com/home")
        profile_link = self.page.locator(
            'a[data-testid="AppTabBar_Profile_Link"]'
        ).first
        href = await profile_link.get_attribute("href")
        await self._goto(f"https://twitter.com{href}")
        await self._wait('[data-testid="tweet"]', timeout=10000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        results = []
        for tweet in tweets[:limit]:
            try:
                link_el = tweet.locator('a[dir="ltr"]:has(time)').first
                href = await link_el.get_attribute("href")
                text = await tweet.locator(
                    '[data-testid="tweetText"]'
                ).first.inner_text()
                time_el = tweet.locator("time").first
                ts = await time_el.get_attribute("datetime")
                results.append(
                    {
                        "url": f"https://twitter.com{href}",
                        "snippet": text[:150],
                        "timestamp": ts,
                    }
                )
            except Exception:
                pass
        return results

    async def pin_post(self, post_url: str):
        print(f"Twitter: Pinning {post_url}...")
        await self._goto(post_url)
        await self._click('[data-testid="caret"]')
        await self._click('menuitem:has-text("Pin to your profile")')
        # Confirm if dialog appears
        confirm = self.page.locator('[data-testid="confirmationSheetConfirm"]')
        if await confirm.count() > 0:
            await confirm.click()
        await asyncio.sleep(2)

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        print("Twitter: Saving draft...")
        await self._goto("https://twitter.com/compose/tweet")
        await self._wait('[data-testid="tweetTextarea_0"]')
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.fill(content)
        if media_paths:
            await self.upload_media(media_paths)
        # Close composer — Twitter auto-saves as draft
        close_btn = self.page.locator('[data-testid="app-bar-close"]').first
        await close_btn.click()
        save_btn = self.page.locator('button:has-text("Save")').first
        if await save_btn.count() > 0:
            await save_btn.click()
        await asyncio.sleep(1)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"Twitter: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=15000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        comments = []
        for i, tweet in enumerate(tweets[1:]):  # skip main post
            try:
                author_el = tweet.locator('[data-testid="User-Name"]').first
                author = (
                    await author_el.inner_text()
                    if await author_el.count() > 0
                    else "unknown"
                )
                text = await tweet.locator(
                    '[data-testid="tweetText"]'
                ).first.inner_text()
                comments.append(
                    {
                        "id": str(i),
                        "author": author.split("\n")[0],
                        "content": text[:200],
                    }
                )
            except Exception:
                pass
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        print(f"Twitter: Replying to comment {comment_id}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=15000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        idx = int(comment_id) + 1
        if idx >= len(tweets):
            raise Exception("Comment ID not found.")
        await tweets[idx].locator('[data-testid="reply"]').click()
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.wait_for(state="visible", timeout=5000)
        await textbox.fill(text)
        await self._click('[data-testid="tweetButton"]')
        await textbox.wait_for(state="hidden", timeout=10000)

    async def delete_comment(self, post_url: str, comment_id: str):
        print(f"Twitter: Hiding reply {comment_id}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=15000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        idx = int(comment_id) + 1
        if idx >= len(tweets):
            raise Exception("Comment ID not found.")
        await tweets[idx].locator('[data-testid="caret"]').click()
        hide_btn = self.page.locator(
            'menuitem:has-text("Hide reply"), menuitem:has-text("Delete")'
        ).first
        await hide_btn.wait_for(state="visible", timeout=5000)
        await hide_btn.click()
        confirm = self.page.locator('[data-testid="confirmationSheetConfirm"]')
        if await confirm.count() > 0:
            await confirm.click()
        await asyncio.sleep(1)

    async def like_post(self, post_url: str):
        print(f"Twitter: Liking {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=10000)
        like_btn = self.page.locator('[data-testid="like"]').first
        if await like_btn.count() == 0:
            raise Exception("Like button not found — post may already be liked.")
        await like_btn.click()
        await asyncio.sleep(1)

    async def unlike_post(self, post_url: str):
        print(f"Twitter: Unliking {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=10000)
        unlike_btn = self.page.locator('[data-testid="unlike"]').first
        if await unlike_btn.count() == 0:
            raise Exception("Unlike button not found — post may not be liked.")
        await unlike_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        print(f"Twitter: Retweeting {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=10000)
        await self._click('[data-testid="retweet"]')
        await self._click('menuitem:has-text("Repost")')
        await asyncio.sleep(1)

    async def quote_post(self, post_url: str, comment: str):
        print(f"Twitter: Quote-posting {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=10000)
        await self._click('[data-testid="retweet"]')
        await self._click('menuitem:has-text("Quote")')
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.wait_for(state="visible", timeout=5000)
        await textbox.fill(comment)
        await self._click('[data-testid="tweetButton"]')
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"Twitter: Searching '{query}'...")
        await self._goto(f"https://twitter.com/search?q={query}&f=live")
        await self._wait('[data-testid="tweet"]', timeout=15000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        results = []
        for tweet in tweets[:10]:
            try:
                link_el = tweet.locator('a[dir="ltr"]:has(time)').first
                href = await link_el.get_attribute("href")
                text = await tweet.locator(
                    '[data-testid="tweetText"]'
                ).first.inner_text()
                results.append(
                    {"url": f"https://twitter.com{href}", "snippet": text[:120]}
                )
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        print(f"Twitter: Reading {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweetText"]', timeout=10000)
        return await self.page.locator('[data-testid="tweetText"]').first.inner_text()

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("Twitter: Fetching trending topics...")
        await self._goto("https://twitter.com/explore/tabs/trending")
        await asyncio.sleep(3)
        items = await self.page.locator('[data-testid="trend"]').all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"topic": text.strip().split("\n")[0]})
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        print(f"Twitter: Fetching profile for @{username}...")
        await self._goto(f"https://twitter.com/{username}")
        await self._wait('[data-testid="UserName"]', timeout=10000)
        name = await self.page.locator('[data-testid="UserName"]').first.inner_text()
        bio_el = self.page.locator('[data-testid="UserDescription"]').first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        # followers / following
        stats = {}
        for stat in ["followers", "following"]:
            el = self.page.locator(f'a[href*="/{stat}"] span').first
            stats[stat] = await el.inner_text() if await el.count() > 0 else "?"
        return {"name": name.strip(), "bio": bio.strip(), **stats}

    async def follow_user(self, username: str):
        print(f"Twitter: Following @{username}...")
        await self._goto(f"https://twitter.com/{username}")
        follow_btn = self.page.locator('[data-testid$="-follow"]').first
        await follow_btn.wait_for(state="visible", timeout=5000)
        await follow_btn.click()
        await asyncio.sleep(1)

    async def unfollow_user(self, username: str):
        print(f"Twitter: Unfollowing @{username}...")
        await self._goto(f"https://twitter.com/{username}")
        # The button text says "Following" when already followed
        following_btn = self.page.locator('[data-testid$="-unfollow"]').first
        await following_btn.wait_for(state="visible", timeout=5000)
        await following_btn.click()
        # Confirm unfollow in dialog
        confirm = self.page.locator('[data-testid="confirmationSheetConfirm"]')
        if await confirm.count() > 0:
            await confirm.click()
        await asyncio.sleep(1)

    async def block_user(self, username: str):
        print(f"Twitter: Blocking @{username}...")
        await self._goto(f"https://twitter.com/{username}")
        await self._click('[data-testid="userActions"]')
        await self._click(f'menuitem:has-text("Block @{username}")')
        await self._click('[data-testid="confirmationSheetConfirm"]')
        await asyncio.sleep(1)

    async def mute_user(self, username: str):
        print(f"Twitter: Muting @{username}...")
        await self._goto(f"https://twitter.com/{username}")
        await self._click('[data-testid="userActions"]')
        await self._click(f'menuitem:has-text("Mute @{username}")')
        await asyncio.sleep(1)

    async def send_dm(self, username: str, text: str):
        print(f"Twitter: Sending DM to @{username}...")
        await self._goto(
            f"https://twitter.com/messages/compose?recipient_id={username}"
        )
        await asyncio.sleep(2)
        # Fall back to searching for the user
        search = self.page.locator('[data-testid="DmSearchInput"]').first
        if await search.count() == 0:
            await self._goto("https://twitter.com/messages/new")
            await asyncio.sleep(1)
            search = self.page.locator('[data-testid="DmSearchInput"]').first
        await search.fill(username)
        await asyncio.sleep(2)
        result = self.page.locator('[data-testid="TypeaheadUser"]').first
        await result.wait_for(state="visible", timeout=5000)
        await result.click()
        next_btn = self.page.locator('[data-testid="nextButton"]').first
        if await next_btn.count() > 0:
            await next_btn.click()
        await asyncio.sleep(1)
        msg_input = self.page.locator('[data-testid="dmComposerTextInput"]').first
        await msg_input.wait_for(state="visible", timeout=5000)
        await msg_input.fill(text)
        await self._click('[data-testid="dmComposerSendButton"]')
        await asyncio.sleep(2)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        print(f"Twitter: Getting analytics for {post_url}...")
        await self._goto(post_url)
        await self._wait('[data-testid="tweet"]', timeout=10000)
        tweet = self.page.locator('[data-testid="tweet"]').first

        def _extract(testid: str) -> str:
            tweet.locator(f'[data-testid="{testid}"]')
            return "?"

        # Try to read visible engagement numbers
        result = {}
        for metric, testid in [
            ("replies", "reply"),
            ("reposts", "retweet"),
            ("likes", "like"),
            ("bookmarks", "bookmark"),
        ]:
            try:
                el = tweet.locator(f'[data-testid="{testid}"] span').first
                val = await el.inner_text() if await el.count() > 0 else "0"
                result[metric] = val.strip()
            except Exception:
                result[metric] = "?"
        return result

    async def get_account_analytics(self) -> dict:
        print("Twitter: Getting account analytics...")
        await self._goto("https://analytics.twitter.com/user/home")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:2000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("Twitter: Fetching notifications...")
        await self._goto("https://twitter.com/notifications")
        await self._wait('[data-testid="cellInnerDiv"]', timeout=10000)
        items = await self.page.locator('[data-testid="cellInnerDiv"]').all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        print("Twitter: Fetching @mentions...")
        await self._goto("https://twitter.com/notifications/mentions")
        await self._wait('[data-testid="tweet"]', timeout=10000)
        tweets = await self.page.locator('[data-testid="tweet"]').all()
        results = []
        for tweet in tweets[:limit]:
            try:
                link_el = tweet.locator('a[dir="ltr"]:has(time)').first
                href = await link_el.get_attribute("href")
                text = await tweet.locator(
                    '[data-testid="tweetText"]'
                ).first.inner_text()
                results.append(
                    {"url": f"https://twitter.com{href}", "content": text[:200]}
                )
            except Exception:
                pass
        return results

    # ─── Special Formats ─────────────────────────────────────────────────────

    async def post_thread(self, tweets: list, media_paths: Optional[list] = None):
        """Post a Twitter thread (series of connected tweets)."""
        if not tweets:
            return
        print(f"Twitter: Posting thread of {len(tweets)} tweets...")
        await self._goto("https://twitter.com/compose/tweet")
        await self._wait('[data-testid="tweetTextarea_0"]')

        # Fill first tweet
        textbox = self.page.locator('[data-testid="tweetTextarea_0"]').first
        await textbox.fill(tweets[0])

        # For each subsequent tweet, click "Add another tweet" and fill
        for i, tweet_text in enumerate(tweets[1:], 1):
            add_btn = self.page.locator('[data-testid="addButton"]').first
            await add_btn.wait_for(state="visible", timeout=5000)
            await add_btn.click()
            await asyncio.sleep(0.5)
            # Each new tweet gets a new textarea indexed by position
            textareas = await self.page.locator('[data-testid^="tweetTextarea_"]').all()
            if i < len(textareas):
                await textareas[i].fill(tweet_text)
            await asyncio.sleep(0.3)

        # Upload media to first tweet if provided
        if media_paths:
            file_input = self.page.locator(
                'input[type="file"][data-testid="fileInput"]'
            ).first
            await file_input.set_input_files(media_paths[:4])
            await self._wait('[data-testid="attachments"]', timeout=20000)

        # Submit the whole thread
        await self._click('[data-testid="tweetButton"]')
        await asyncio.sleep(3)

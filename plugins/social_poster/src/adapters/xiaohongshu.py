"""小红书 (Xiaohongshu) adapter."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class XiaohongshuAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Xiaohongshu: Navigating to creator center...")
        await self._goto("https://creator.xiaohongshu.com/publish/publish")
        try:
            await self.page.wait_for_selector(
                ".upload-container", timeout=10000, state="visible"
            )
        except Exception:
            if (
                "login" in self.page.url
                or await self.page.locator('text="登录"').count() > 0
            ):
                raise Exception(
                    "Login required for Xiaohongshu. Please login manually in Chrome first."
                )
            raise Exception(
                "Failed to load Xiaohongshu creator center. The UI might have changed."
            )

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Xiaohongshu: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(files)
        await self.page.wait_for_selector(
            ".image-preview, .preview-container", timeout=15000, state="visible"
        )

    async def fill_content(self, text: str):
        print("Xiaohongshu: Filling content...")
        editor = self.page.locator(".post-content-container .ql-editor").first
        await editor.wait_for(state="visible", timeout=5000)
        await editor.fill(text)

    async def submit_post(self):
        print("Xiaohongshu: Publishing...")
        submit_btn = self.page.locator(
            'button.submit-btn, button:has-text("发布")'
        ).first
        await submit_btn.wait_for(state="visible", timeout=5000)
        await submit_btn.click()
        await self.page.wait_for_url("**/creator/notes**", timeout=15000)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print("Xiaohongshu: Deleting post...")
        await self._goto("https://creator.xiaohongshu.com/creator/notes")
        delete_btn = self.page.locator('text="删除"').first
        await delete_btn.wait_for(state="visible", timeout=10000)
        await delete_btn.click()
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state="hidden", timeout=5000)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("Xiaohongshu: Fetching my posts...")
        await self._goto("https://creator.xiaohongshu.com/creator/notes")
        await asyncio.sleep(3)
        items = await self.page.locator(".note-item, .works-item").all()
        results = []
        for item in items[:limit]:
            try:
                link_el = item.locator("a").first
                href = (
                    await link_el.get_attribute("href")
                    if await link_el.count() > 0
                    else ""
                )
                title_el = item.locator(".title, .works-title").first
                title = (
                    await title_el.inner_text() if await title_el.count() > 0 else ""
                )
                results.append(
                    {
                        "url": f"https://creator.xiaohongshu.com{href}"
                        if href.startswith("/")
                        else href,
                        "snippet": title,
                    }
                )
            except Exception:
                pass
        return results

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        print("Xiaohongshu: Saving draft...")
        await self.open_platform()
        if media_paths:
            await self.upload_media(media_paths)
        await self.fill_content(content)
        draft_btn = self.page.locator(
            'button:has-text("存草稿"), button:has-text("暂存")'
        ).first
        if await draft_btn.count() > 0:
            await draft_btn.click()
            await asyncio.sleep(2)
        else:
            # Navigate away — some versions auto-save as draft
            await self._goto("https://creator.xiaohongshu.com/creator/notes")

    # ─── Comments ────────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"Xiaohongshu: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await self.page.wait_for_selector(
            ".comment-item", timeout=10000, state="visible"
        )
        items = await self.page.locator(".comment-item").all()
        comments = []
        for i, el in enumerate(items):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await self.page.wait_for_selector(
            ".comment-item", timeout=10000, state="visible"
        )
        items = await self.page.locator(".comment-item").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator(".reply-btn").click()
        input_box = self.page.locator(".comment-input").first
        await input_box.wait_for(state="visible", timeout=5000)
        await input_box.fill(text)
        await self.page.locator('button:has-text("发送")').first.click()
        await input_box.wait_for(state="hidden", timeout=5000)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await self.page.wait_for_selector(
            ".comment-item", timeout=10000, state="visible"
        )
        items = await self.page.locator(".comment-item").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].hover()
        delete_btn = items[idx].locator('span:has-text("删除"), svg.delete-icon').first
        await delete_btn.wait_for(state="visible", timeout=5000)
        await delete_btn.click()
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state="hidden", timeout=5000)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def like_post(self, post_url: str):
        print(f"Xiaohongshu: Liking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        like_btn = self.page.locator(
            '.like-wrapper:not(.liked), button[aria-label="点赞"]'
        ).first
        await like_btn.wait_for(state="visible", timeout=5000)
        await like_btn.click()
        await asyncio.sleep(1)

    async def unlike_post(self, post_url: str):
        print(f"Xiaohongshu: Unliking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        unlike_btn = self.page.locator(".like-wrapper.liked, .liked").first
        await unlike_btn.wait_for(state="visible", timeout=5000)
        await unlike_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        """小红书无转发功能，改为分享链接。"""
        await self._goto(post_url)
        await asyncio.sleep(2)
        share_btn = self.page.locator('.share-wrapper, button[aria-label="分享"]').first
        if await share_btn.count() == 0:
            raise NotImplementedError("小红书不支持转发功能。")
        await share_btn.click()
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"Xiaohongshu: Searching '{query}'...")
        await self._goto(f"https://www.xiaohongshu.com/search_result?keyword={query}")
        await self.page.wait_for_selector(".note-item", timeout=10000, state="visible")
        notes = await self.page.locator(".note-item").all()
        results = []
        for note in notes[:10]:
            try:
                link = await note.locator("a").first.get_attribute("href")
                title = await note.locator(".title").first.inner_text()
                results.append(
                    {"url": f"https://www.xiaohongshu.com{link}", "snippet": title}
                )
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await self.page.wait_for_selector(".desc", timeout=10000, state="visible")
        return await self.page.locator(".desc").first.inner_text()

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("Xiaohongshu: Fetching trending topics...")
        await self._goto("https://www.xiaohongshu.com/explore")
        await asyncio.sleep(3)
        # Hashtag links in the explore feed
        tags = await self.page.locator('a[href*="/search_result?keyword="]').all()
        seen, results = set(), []
        for tag_el in tags:
            try:
                text = (await tag_el.inner_text()).strip()
                if text and text not in seen:
                    seen.add(text)
                    results.append({"topic": text})
                    if len(results) >= limit:
                        break
            except Exception:
                pass
        # Also check the discovery/trending section
        if not results:
            hot_items = await self.page.locator(".topic-item, .hot-topic").all()
            for item in hot_items[:limit]:
                try:
                    text = (await item.inner_text()).strip()
                    if text and text not in seen:
                        seen.add(text)
                        results.append({"topic": text})
                except Exception:
                    pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        print(f"Xiaohongshu: Fetching profile {username}...")
        url = (
            f"https://www.xiaohongshu.com/user/profile/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(3)
        name_el = self.page.locator(".user-name, h1").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        bio_el = self.page.locator(".user-desc, .bio").first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        fans_el = self.page.locator('span:has-text("粉丝") + span, .fans-count').first
        fans = await fans_el.inner_text() if await fans_el.count() > 0 else "?"
        return {"name": name.strip(), "bio": bio.strip(), "fans": fans}

    async def follow_user(self, username: str):
        print(f"Xiaohongshu: Following {username}...")
        url = (
            f"https://www.xiaohongshu.com/user/profile/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        follow_btn = self.page.locator(
            'button:has-text("关注"), button.follow-btn:not(.following)'
        ).first
        await follow_btn.wait_for(state="visible", timeout=5000)
        await follow_btn.click()
        await asyncio.sleep(1)

    async def unfollow_user(self, username: str):
        print(f"Xiaohongshu: Unfollowing {username}...")
        url = (
            f"https://www.xiaohongshu.com/user/profile/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        following_btn = self.page.locator(
            'button:has-text("已关注"), button.following'
        ).first
        await following_btn.wait_for(state="visible", timeout=5000)
        await following_btn.click()
        await asyncio.sleep(1)
        cancel_btn = self.page.locator('button:has-text("取消关注")').first
        if await cancel_btn.count() > 0:
            await cancel_btn.click()
        await asyncio.sleep(1)

    async def send_dm(self, username: str, text: str):
        print(f"Xiaohongshu: Sending DM to {username}...")
        url = (
            f"https://www.xiaohongshu.com/user/profile/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        msg_btn = self.page.locator('button:has-text("私信")').first
        if await msg_btn.count() == 0:
            raise Exception("私信 button not found. The user may not allow DMs.")
        await msg_btn.click()
        await asyncio.sleep(2)
        msg_input = self.page.locator(
            'textarea[placeholder*="发送消息"], div[contenteditable="true"]'
        ).first
        await msg_input.wait_for(state="visible", timeout=5000)
        await msg_input.fill(text)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    async def block_user(self, username: str):
        url = (
            f"https://www.xiaohongshu.com/user/profile/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        more_btn = self.page.locator(
            'button[aria-label="更多"], svg[aria-label="更多"]'
        ).first
        await more_btn.click()
        await asyncio.sleep(1)
        block_btn = self.page.locator(
            'span:has-text("拉黑"), button:has-text("拉黑")'
        ).first
        await block_btn.click()
        await asyncio.sleep(1)
        confirm_btn = self.page.locator('button:has-text("确定")').first
        if await confirm_btn.count() > 0:
            await confirm_btn.click()
        await asyncio.sleep(1)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        print(f"Xiaohongshu: Getting analytics for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        result = {}
        like_el = self.page.locator(".like-wrapper span, .likes-count").first
        result["likes"] = (
            await like_el.inner_text() if await like_el.count() > 0 else "?"
        )
        collect_el = self.page.locator(".collect-wrapper span, .collects-count").first
        result["collects"] = (
            await collect_el.inner_text() if await collect_el.count() > 0 else "?"
        )
        comment_el = self.page.locator(".comment-wrapper span, .comments-count").first
        result["comments"] = (
            await comment_el.inner_text() if await comment_el.count() > 0 else "?"
        )
        return result

    async def get_account_analytics(self) -> dict:
        print("Xiaohongshu: Getting account analytics...")
        await self._goto("https://creator.xiaohongshu.com/statistics")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("Xiaohongshu: Fetching notifications...")
        await self._goto("https://www.xiaohongshu.com/notification")
        await asyncio.sleep(3)
        items = await self.page.locator(".notification-item, .msg-item").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        print("Xiaohongshu: Fetching @mentions...")
        await self._goto("https://www.xiaohongshu.com/notification?type=at")
        await asyncio.sleep(3)
        items = await self.page.locator(".notification-item, .msg-item").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

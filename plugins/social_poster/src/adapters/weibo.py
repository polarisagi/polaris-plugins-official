"""Weibo adapter."""

import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class WeiboAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("Weibo: Navigating to composer...")
        await self._goto("https://weibo.com")
        try:
            await self.page.wait_for_selector(
                'textarea[title="微博输入框"], .Form_input_3JT2Q',
                timeout=10000,
                state="visible",
            )
        except Exception:
            if (
                "login" in self.page.url
                or await self.page.locator('a[action-type="login"]').count() > 0
            ):
                raise Exception(
                    "Login required for Weibo. Please login manually in Chrome first."
                )
            raise Exception("Failed to load Weibo composer. The UI might have changed.")

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"Weibo: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(files)
        await self.page.wait_for_selector(
            ".woo-picture-main", timeout=15000, state="visible"
        )

    async def fill_content(self, text: str):
        print("Weibo: Filling content...")
        textbox = self.page.locator(
            'textarea[title="微博输入框"], .Form_input_3JT2Q'
        ).first
        await textbox.wait_for(state="visible", timeout=5000)
        await textbox.fill(text)

    async def submit_post(self):
        print("Weibo: Posting...")
        submit_btn = self.page.locator(
            'button.Tool_btn_2EHg0, button:has-text("发送")'
        ).first
        await submit_btn.wait_for(state="visible", timeout=5000)
        await submit_btn.click()
        await self.page.wait_for_selector(".woo-toast", timeout=10000, state="visible")

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print(f"Weibo: Deleting {post_url}...")
        await self._goto(post_url)
        arrow_btn = self.page.locator(".woo-pop-ctrl").first
        await arrow_btn.wait_for(state="visible", timeout=10000)
        await arrow_btn.click()
        delete_btn = self.page.locator('text="删除"').first
        await delete_btn.wait_for(state="visible", timeout=5000)
        await delete_btn.click()
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state="hidden", timeout=5000)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("Weibo: Fetching my posts...")
        await self._goto("https://weibo.com/u/home")
        await asyncio.sleep(3)
        items = await self.page.locator(
            ".wbpro-scroller-item, .vue-recycle-scroller__item-view"
        ).all()
        results = []
        for item in items[:limit]:
            try:
                link_el = item.locator("a[href*='/detail/']").first
                href = (
                    await link_el.get_attribute("href")
                    if await link_el.count() > 0
                    else ""
                )
                text = await item.inner_text()
                results.append(
                    {
                        "url": f"https://weibo.com{href}"
                        if href.startswith("/")
                        else href,
                        "snippet": text[:150],
                    }
                )
            except Exception:
                pass
        return results

    async def edit_post(self, post_url: str, new_content: str):
        """Weibo doesn't support editing published posts — raises informative error."""
        raise NotImplementedError("微博不支持编辑已发布的帖子，请删除后重新发布。")

    # ─── Comments ────────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print(f"Weibo: Fetching comments for {post_url}...")
        await self._goto(post_url)
        await self.page.wait_for_selector(".list_li", timeout=10000, state="visible")
        items = await self.page.locator(".list_li").all()
        comments = []
        for i, el in enumerate(items):
            text = await el.locator(".text").first.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto(post_url)
        await self.page.wait_for_selector(".list_li", timeout=10000, state="visible")
        items = await self.page.locator(".list_li").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('a:has-text("回复")').first.click()
        input_box = items[idx].locator("textarea").first
        await input_box.wait_for(state="visible", timeout=5000)
        await input_box.fill(text)
        await items[idx].locator('button:has-text("回复")').first.click()
        await input_box.wait_for(state="hidden", timeout=5000)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto(post_url)
        await self.page.wait_for_selector(".list_li", timeout=10000, state="visible")
        items = await self.page.locator(".list_li").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].hover()
        delete_btn = items[idx].locator('a:has-text("删除")').first
        await delete_btn.wait_for(state="visible", timeout=5000)
        await delete_btn.click()
        confirm_btn = self.page.locator('button:has-text("确定")').first
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()
        await confirm_btn.wait_for(state="hidden", timeout=5000)

    # ─── Engagement ──────────────────────────────────────────────────────────

    async def like_post(self, post_url: str):
        print(f"Weibo: Liking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        like_btn = self.page.locator('button[title="赞"], a[action-type="like"]').first
        if await like_btn.count() == 0:
            like_btn = self.page.locator('.woo-like-main, [data-likealready="0"]').first
        await like_btn.wait_for(state="visible", timeout=5000)
        await like_btn.click()
        await asyncio.sleep(1)

    async def unlike_post(self, post_url: str):
        print(f"Weibo: Unliking {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        unlike_btn = self.page.locator('[data-likealready="1"], .woo-like-active').first
        await unlike_btn.wait_for(state="visible", timeout=5000)
        await unlike_btn.click()
        await asyncio.sleep(1)

    async def repost(self, post_url: str):
        print(f"Weibo: Retweeting {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        repost_btn = self.page.locator(
            'a[action-type="forward"], button[title="转发"]'
        ).first
        await repost_btn.wait_for(state="visible", timeout=5000)
        await repost_btn.click()
        await asyncio.sleep(2)
        submit_btn = self.page.locator('button:has-text("转发")').first
        await submit_btn.click()
        await asyncio.sleep(2)

    async def quote_post(self, post_url: str, comment: str):
        print(f"Weibo: Quote-retweeting {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(2)
        repost_btn = self.page.locator(
            'a[action-type="forward"], button[title="转发"]'
        ).first
        await repost_btn.wait_for(state="visible", timeout=5000)
        await repost_btn.click()
        await asyncio.sleep(2)
        text_area = self.page.locator(
            'textarea[placeholder*="转发理由"], .WB_detail textarea'
        ).first
        if await text_area.count() > 0:
            await text_area.fill(comment)
        submit_btn = self.page.locator('button:has-text("转发")').first
        await submit_btn.click()
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"Weibo: Searching '{query}'...")
        await self._goto(f"https://s.weibo.com/weibo?q={query}")
        await self.page.wait_for_selector(".card-wrap", timeout=10000, state="visible")
        notes = await self.page.locator(".card-wrap").all()
        results = []
        for note in notes[:10]:
            try:
                link = await note.locator('a[from="weibo"]').first.get_attribute("href")
                if not link.startswith("http"):
                    link = "https:" + link
                title = await note.locator(".txt").first.inner_text()
                results.append({"url": link, "snippet": title[:100]})
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await self.page.wait_for_selector(".detail_txt", timeout=10000, state="visible")
        return await self.page.locator(".detail_txt").first.inner_text()

    async def get_trending_topics(self, limit: int = 10) -> list:
        print("Weibo: Fetching hot search topics...")
        await self._goto("https://s.weibo.com/top/summary")
        await asyncio.sleep(3)
        rows = await self.page.locator("table tr").all()
        results = []
        for row in rows[1 : limit + 1]:
            try:
                text_el = row.locator("td:nth-child(2) a").first
                topic = await text_el.inner_text()
                href = await text_el.get_attribute("href")
                results.append({"topic": topic.strip(), "url": href or ""})
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        print(f"Weibo: Fetching profile {username}...")
        url = (
            f"https://weibo.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(3)
        name_el = self.page.locator(".ProfileHeader_name_lfkbz, h1").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        bio_el = self.page.locator(
            ".ProfileHeader_desc_1SbzS, .ProfileHeader_info_1S0tL"
        ).first
        bio = await bio_el.inner_text() if await bio_el.count() > 0 else ""
        fans_el = self.page.locator(
            'a[href*="fans"] strong, span:has-text("粉丝") + span'
        ).first
        fans = await fans_el.inner_text() if await fans_el.count() > 0 else "?"
        return {"name": name.strip(), "bio": bio.strip(), "fans": fans}

    async def follow_user(self, username: str):
        print(f"Weibo: Following {username}...")
        url = (
            f"https://weibo.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        follow_btn = self.page.locator(
            'button:has-text("关注"), a:has-text("+关注")'
        ).first
        await follow_btn.wait_for(state="visible", timeout=5000)
        await follow_btn.click()
        await asyncio.sleep(1)

    async def unfollow_user(self, username: str):
        print(f"Weibo: Unfollowing {username}...")
        url = (
            f"https://weibo.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        following_btn = self.page.locator('button:has-text("已关注")').first
        await following_btn.wait_for(state="visible", timeout=5000)
        await following_btn.click()
        await asyncio.sleep(1)
        cancel_btn = self.page.locator(
            'button:has-text("取消关注"), li:has-text("取消关注")'
        ).first
        if await cancel_btn.count() > 0:
            await cancel_btn.click()
        await asyncio.sleep(1)

    async def send_dm(self, username: str, text: str):
        print(f"Weibo: Sending DM to {username}...")
        url = (
            f"https://weibo.com/{username}"
            if not username.startswith("http")
            else username
        )
        await self._goto(url)
        await asyncio.sleep(2)
        msg_btn = self.page.locator('button:has-text("私信"), a:has-text("私信")').first
        if await msg_btn.count() == 0:
            await self._goto("https://weibo.com/message/msglist")
            await asyncio.sleep(2)
            compose_btn = self.page.locator(
                'button:has-text("写私信"), a:has-text("发私信")'
            ).first
            await compose_btn.click()
            await asyncio.sleep(1)
            search = self.page.locator('input[placeholder*="搜索"]').first
            await search.fill(username)
            await asyncio.sleep(2)
            await self.page.locator(f'span:has-text("{username}")').first.click()
        else:
            await msg_btn.click()
        await asyncio.sleep(2)
        msg_input = self.page.locator(
            'textarea[placeholder*="输入消息"], div[contenteditable="true"]'
        ).first
        await msg_input.wait_for(state="visible", timeout=5000)
        await msg_input.fill(text)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(2)

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        print(f"Weibo: Getting analytics for {post_url}...")
        await self._goto(post_url)
        await asyncio.sleep(3)
        result = {}
        like_el = self.page.locator('.woo-like-count, [action-type="like"] em').first
        result["likes"] = (
            await like_el.inner_text() if await like_el.count() > 0 else "?"
        )
        comment_el = self.page.locator('[action-type="comment"] em').first
        result["comments"] = (
            await comment_el.inner_text() if await comment_el.count() > 0 else "?"
        )
        repost_el = self.page.locator('[action-type="forward"] em').first
        result["reposts"] = (
            await repost_el.inner_text() if await repost_el.count() > 0 else "?"
        )
        return result

    async def get_account_analytics(self) -> dict:
        print("Weibo: Getting account analytics...")
        await self._goto("https://data.weibo.com/index")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("Weibo: Fetching notifications...")
        await self._goto("https://weibo.com/notification/")
        await asyncio.sleep(3)
        items = await self.page.locator(
            ".wbpro-notification-item, .WB_detail, li.S_line2"
        ).all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        print("Weibo: Fetching @mentions...")
        await self._goto("https://weibo.com/notification/?type=at")
        await asyncio.sleep(3)
        items = await self.page.locator(".wbpro-notification-item, .WB_detail").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

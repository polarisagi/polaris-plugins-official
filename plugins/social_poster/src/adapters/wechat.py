"""WeChat Official Accounts adapter."""

from typing import Optional
import asyncio
from .base_adapter import BaseAdapter
from ..utils.media import split_by_type


class WechatAdapter(BaseAdapter):
    async def _goto(self, url: str):
        await self.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(2)

    # ─── Core Publishing ─────────────────────────────────────────────────────

    async def open_platform(self):
        print("WeChat: Navigating to Official Accounts platform...")
        await self._goto("https://mp.weixin.qq.com/")
        await self.page.wait_for_selector(".weui-desktop-rich-editor", timeout=15000)

    async def upload_media(self, media_paths: list):
        if not media_paths:
            return
        print(f"WeChat: Uploading media {media_paths}...")
        media = split_by_type(media_paths)
        files = media["images"] + media["videos"]
        if not files:
            return
        file_input = self.page.locator('input[type="file"]').first
        await file_input.set_input_files(files)
        await asyncio.sleep(3)

    async def fill_content(self, text: str):
        print("WeChat: Filling content into editor...")
        editor = self.page.locator(".weui-desktop-rich-editor").first
        await editor.fill(text)
        await asyncio.sleep(1)

    async def submit_post(self):
        print("WeChat: Publishing...")
        submit_btn = self.page.locator(
            'button:has-text("群发"), button:has-text("发布")'
        ).first
        await submit_btn.click()
        await asyncio.sleep(3)

    # ─── Post Management ─────────────────────────────────────────────────────

    async def delete_post(self, post_url: str):
        print("WeChat: Deleting post from publish history...")
        await self._goto("https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list")
        await asyncio.sleep(3)
        await self.page.locator("a.weui-desktop-icon-btn_delete").first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确认")').first.click()
        await asyncio.sleep(2)

    async def get_my_posts(self, limit: int = 10) -> list:
        print("WeChat: Fetching published articles...")
        await self._goto("https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list")
        await asyncio.sleep(3)
        rows = await self.page.locator(".weui-desktop-table__row, .article-item").all()
        results = []
        for row in rows[:limit]:
            try:
                link_el = row.locator("a").first
                href = (
                    await link_el.get_attribute("href")
                    if await link_el.count() > 0
                    else ""
                )
                title_el = row.locator(".title, td:first-child").first
                title = (
                    await title_el.inner_text() if await title_el.count() > 0 else ""
                )
                results.append(
                    {
                        "url": href,
                        "snippet": title.strip(),
                    }
                )
            except Exception:
                pass
        return results

    async def edit_post(self, post_url: str, new_content: str):
        """WeChat supports editing draft articles before publish but not published ones."""
        await self._goto("https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list")
        await asyncio.sleep(3)
        edit_btn = self.page.locator(
            'a:has-text("编辑"), button:has-text("编辑")'
        ).first
        if await edit_btn.count() == 0:
            raise NotImplementedError("只有草稿可以编辑，已发布的图文不支持直接修改。")
        await edit_btn.click()
        await asyncio.sleep(2)
        editor = self.page.locator(".weui-desktop-rich-editor").first
        await editor.fill(new_content)
        await asyncio.sleep(1)
        save_btn = self.page.locator('button:has-text("保存")').first
        await save_btn.click()
        await asyncio.sleep(2)

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        print("WeChat: Saving draft...")
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

    # ─── Comments ────────────────────────────────────────────────────────────

    async def get_comments(self, post_url: str) -> list:
        print("WeChat: Fetching comments...")
        await self._goto("https://mp.weixin.qq.com/misc/appmsgcomment")
        await asyncio.sleep(3)
        items = await self.page.locator(".weui-desktop-table__row").all()
        comments = []
        for i, el in enumerate(items):
            text = await el.inner_text()
            comments.append({"id": str(i), "content": text[:200]})
        return comments

    async def reply_to_comment(self, post_url: str, comment_id: str, text: str):
        await self._goto("https://mp.weixin.qq.com/misc/appmsgcomment")
        await asyncio.sleep(3)
        items = await self.page.locator(".weui-desktop-table__row").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('a:has-text("回复")').first.click()
        await asyncio.sleep(1)
        await self.page.locator("textarea.weui-desktop-form__textarea").first.fill(text)
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("发送")').first.click()
        await asyncio.sleep(2)

    async def delete_comment(self, post_url: str, comment_id: str):
        await self._goto("https://mp.weixin.qq.com/misc/appmsgcomment")
        await asyncio.sleep(3)
        items = await self.page.locator(".weui-desktop-table__row").all()
        idx = int(comment_id)
        if idx >= len(items):
            raise Exception("Comment ID not found.")
        await items[idx].locator('a:has-text("删除")').first.click()
        await asyncio.sleep(1)
        await self.page.locator('button:has-text("确定")').first.click()
        await asyncio.sleep(2)

    # ─── Search & Discovery ──────────────────────────────────────────────────

    async def search_posts(self, query: str) -> list:
        print(f"WeChat: Searching '{query}' via Sogou...")
        await self._goto(f"https://weixin.sogou.com/weixin?type=2&query={query}")
        await asyncio.sleep(3)
        articles = await self.page.locator(".news-list li").all()
        results = []
        for art in articles[:10]:
            try:
                link = await art.locator("h3 a").first.get_attribute("href")
                title = await art.locator("h3").first.inner_text()
                if link and link.startswith("/link"):
                    link = "https://weixin.sogou.com" + link
                results.append({"url": link, "snippet": title})
            except Exception:
                pass
        return results

    async def read_post(self, post_url: str) -> str:
        await self._goto(post_url)
        await self.page.wait_for_selector("#js_content", timeout=10000)
        return await self.page.locator("#js_content").first.inner_text()

    async def get_trending_topics(self, limit: int = 10) -> list:
        """WeChat doesn't have public trending — returns top search terms from Sogou."""
        print("WeChat: Fetching trending topics via Sogou...")
        await self._goto("https://weixin.sogou.com/")
        await asyncio.sleep(3)
        items = await self.page.locator(".hot-item, .hot-word a").all()
        results = []
        for item in items[:limit]:
            try:
                text = (await item.inner_text()).strip()
                if text:
                    results.append({"topic": text})
            except Exception:
                pass
        return results

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        """WeChat Official Accounts — looks up account via Sogou search."""
        print(f"WeChat: Looking up account '{username}'...")
        await self._goto(f"https://weixin.sogou.com/weixin?type=1&query={username}")
        await asyncio.sleep(3)
        item = self.page.locator(".news-list li, .account-item").first
        name_el = item.locator("h3, .account-name").first
        name = await name_el.inner_text() if await name_el.count() > 0 else username
        desc_el = item.locator(".account-desc, p").first
        desc = await desc_el.inner_text() if await desc_el.count() > 0 else ""
        return {"name": name.strip(), "description": desc.strip()}

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_url: str) -> dict:
        """Opens the WeChat MP data center for the article stats."""
        print("WeChat: Getting article analytics...")
        await self._goto(
            "https://mp.weixin.qq.com/misc/articlestatshomepage?action=index"
        )
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

    async def get_account_analytics(self) -> dict:
        print("WeChat: Getting account analytics...")
        await self._goto("https://mp.weixin.qq.com/misc/datacube")
        await asyncio.sleep(4)
        text = await self.page.locator("body").inner_text()
        return {"raw_analytics_text": text[:3000]}

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        print("WeChat: Fetching notifications from MP backend...")
        await self._goto("https://mp.weixin.qq.com/")
        await asyncio.sleep(2)
        notif_el = self.page.locator(
            ".message-notice, .weui-desktop-notification, .notice-wrap"
        ).first
        if await notif_el.count() > 0:
            await notif_el.click()
            await asyncio.sleep(2)
        items = await self.page.locator(".notice-item, .weui-desktop-table__row").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

    async def get_mentions(self, limit: int = 20) -> list:
        """WeChat MP tracks user messages/comments — return recent messages."""
        print("WeChat: Fetching user messages (mentions)...")
        await self._goto("https://mp.weixin.qq.com/misc/messagedashboard")
        await asyncio.sleep(3)
        items = await self.page.locator(".weui-desktop-table__row, .msg-item").all()
        results = []
        for item in items[:limit]:
            try:
                text = await item.inner_text()
                results.append({"content": text[:150]})
            except Exception:
                pass
        return results

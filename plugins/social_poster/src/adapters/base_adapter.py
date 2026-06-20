"""Base adapter — defines the full capability interface for every platform."""

from abc import ABC, abstractmethod
from typing import Optional


class BaseAdapter(ABC):
    """
    All methods either:
    - Are @abstractmethod  → every adapter must implement them.
    - Raise NotImplementedError → optional; implement when the platform supports it.
    """

    def __init__(self, page):
        self.page = page

    # ─── Core Publishing ──────────────────────────────────────────────────────

    @abstractmethod
    async def open_platform(self):
        """Navigate to the platform's post-creation page."""

    @abstractmethod
    async def upload_media(self, media_paths: list):
        """Upload images / videos / audio files."""

    @abstractmethod
    async def fill_content(self, text: str):
        """Type the formatted text into the composer."""

    @abstractmethod
    async def submit_post(self):
        """Click the publish/post button and wait for confirmation."""

    # ─── Post Management ─────────────────────────────────────────────────────

    @abstractmethod
    async def delete_post(self, post_identifier: str):
        """Delete (or move to trash) a specific post."""

    async def edit_post(self, post_identifier: str, new_content: str):
        """Edit the text of an existing post (where supported)."""
        raise NotImplementedError("edit_post is not supported on this platform.")

    async def get_my_posts(self, limit: int = 10) -> list:
        """Return a list of own recent posts: [{url, snippet, timestamp}]."""
        raise NotImplementedError("get_my_posts is not supported on this platform.")

    async def pin_post(self, post_identifier: str):
        """Pin a post to the top of the profile."""
        raise NotImplementedError("pin_post is not supported on this platform.")

    async def save_draft(self, content: str, media_paths: Optional[list] = None):
        """Save a post as a draft instead of publishing."""
        raise NotImplementedError("save_draft is not supported on this platform.")

    # ─── Engagement ──────────────────────────────────────────────────────────

    @abstractmethod
    async def get_comments(self, post_identifier: str) -> list:
        """Return comments: [{id, author, content}]."""

    @abstractmethod
    async def reply_to_comment(self, post_identifier: str, comment_id: str, text: str):
        """Reply to a specific comment."""

    @abstractmethod
    async def delete_comment(self, post_identifier: str, comment_id: str):
        """Delete or hide a comment."""

    async def like_post(self, post_identifier: str):
        """Like / heart a post."""
        raise NotImplementedError("like_post is not supported on this platform.")

    async def unlike_post(self, post_identifier: str):
        """Remove a like from a post."""
        raise NotImplementedError("unlike_post is not supported on this platform.")

    async def repost(self, post_identifier: str):
        """Retweet / repost / share a post without extra comment."""
        raise NotImplementedError("repost is not supported on this platform.")

    async def quote_post(self, post_identifier: str, comment: str):
        """Quote-repost with an added comment."""
        raise NotImplementedError("quote_post is not supported on this platform.")

    async def pin_comment(self, post_identifier: str, comment_id: str):
        """Pin a comment to the top of the comment section."""
        raise NotImplementedError("pin_comment is not supported on this platform.")

    # ─── Search & Discovery ──────────────────────────────────────────────────

    @abstractmethod
    async def search_posts(self, query: str) -> list:
        """Search posts. Return [{url, snippet}]."""

    @abstractmethod
    async def read_post(self, post_identifier: str) -> str:
        """Read and return the full text of a post."""

    async def get_trending_topics(self, limit: int = 10) -> list:
        """Return trending topics/hashtags: [{topic, heat}]."""
        raise NotImplementedError(
            "get_trending_topics is not supported on this platform."
        )

    # ─── User Operations ─────────────────────────────────────────────────────

    async def get_user_profile(self, username: str) -> dict:
        """Return profile info: {name, bio, followers, following, posts}."""
        raise NotImplementedError("get_user_profile is not supported on this platform.")

    async def follow_user(self, username: str):
        """Follow a user."""
        raise NotImplementedError("follow_user is not supported on this platform.")

    async def unfollow_user(self, username: str):
        """Unfollow a user."""
        raise NotImplementedError("unfollow_user is not supported on this platform.")

    async def block_user(self, username: str):
        """Block a user."""
        raise NotImplementedError("block_user is not supported on this platform.")

    async def mute_user(self, username: str):
        """Mute a user."""
        raise NotImplementedError("mute_user is not supported on this platform.")

    async def send_dm(self, username: str, text: str):
        """Send a direct message to a user."""
        raise NotImplementedError("send_dm is not supported on this platform.")

    # ─── Analytics ───────────────────────────────────────────────────────────

    async def get_post_analytics(self, post_identifier: str) -> dict:
        """Return engagement metrics: {likes, comments, reposts, views, bookmarks}."""
        raise NotImplementedError(
            "get_post_analytics is not supported on this platform."
        )

    async def get_account_analytics(self) -> dict:
        """Return account-level stats: {followers, following, total_posts, impressions}."""
        raise NotImplementedError(
            "get_account_analytics is not supported on this platform."
        )

    # ─── Notifications ───────────────────────────────────────────────────────

    async def get_notifications(self, limit: int = 20) -> list:
        """Return recent notifications: [{type, actor, content, time}]."""
        raise NotImplementedError(
            "get_notifications is not supported on this platform."
        )

    async def get_mentions(self, limit: int = 20) -> list:
        """Return recent @mentions: [{url, author, content}]."""
        raise NotImplementedError("get_mentions is not supported on this platform.")

    # ─── Special Formats ─────────────────────────────────────────────────────

    async def post_story(self, media_paths: list, text: str = ""):
        """Post an ephemeral story (Instagram, Facebook, etc.)."""
        raise NotImplementedError("post_story is not supported on this platform.")

    async def post_thread(self, tweets: list, media_paths: Optional[list] = None):
        """Post a series of connected posts (Twitter thread, LinkedIn carousel, etc.)."""
        raise NotImplementedError("post_thread is not supported on this platform.")

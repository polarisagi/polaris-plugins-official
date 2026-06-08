from abc import ABC, abstractmethod

class BaseAdapter(ABC):
    """
    Base class for all social media platform adapters.
    Defines the standard workflow for posting content.
    """
    def __init__(self, page):
        self.page = page

    @abstractmethod
    async def open_platform(self):
        """
        Navigate to the platform's creation/posting page.
        """
        pass

    @abstractmethod
    async def upload_media(self, image_paths: list[str]):
        """
        Upload images or videos to the platform.
        """
        pass

    @abstractmethod
    async def fill_content(self, text: str):
        """
        Fill the formatted text into the platform's text area.
        """
        pass

    @abstractmethod
    async def submit_post(self):
        """
        Click the submit/post button.
        """
        pass

    @abstractmethod
    async def delete_post(self, post_identifier: str):
        pass

    @abstractmethod
    async def get_comments(self, post_identifier: str) -> list[dict]:
        pass

    @abstractmethod
    async def reply_to_comment(self, post_identifier: str, comment_id: str, text: str):
        pass

    @abstractmethod
    async def search_posts(self, query: str) -> list[dict]:
        pass

    @abstractmethod
    async def read_post(self, post_identifier: str) -> str:
        pass

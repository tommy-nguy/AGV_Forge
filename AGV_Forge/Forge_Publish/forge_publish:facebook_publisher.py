"""
Facebook Publisher (skeleton - sẽ triển khai sau).
"""

from pathlib import Path
from typing import Optional, Dict, Any
import structlog

from .base_publisher import BasePublisher, PublishError

logger = structlog.get_logger(__name__)


class FacebookPublisher(BasePublisher):
    """Upload video lên Facebook (Page)."""

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.app_id = credentials.get("app_id")
        self.app_secret = credentials.get("app_secret")
        self.page_id = credentials.get("page_id")
        self.access_token = credentials.get("access_token")
        logger.warning("FacebookPublisher is a skeleton, not fully implemented")

    def authenticate(self) -> bool:
        """Facebook thường dùng Page Access Token, không cần OAuth flow phức tạp."""
        if not self.access_token:
            raise PublishError("Facebook access token is required")
        self.authenticated = True
        return True

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Optional[Path] = None,
        **kwargs
    ) -> str:
        """Sẽ triển khai sau."""
        raise NotImplementedError("FacebookPublisher is not yet implemented")

    def get_publish_status(self, video_id: str) -> Dict[str, Any]:
        raise NotImplementedError("FacebookPublisher is not yet implemented")
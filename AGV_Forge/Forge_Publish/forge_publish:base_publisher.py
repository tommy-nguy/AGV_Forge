"""
Abstract base class cho các nền tảng publish.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class PublishError(Exception):
    """Lỗi khi publish."""
    pass


class BasePublisher(ABC):
    """Interface chung cho YouTube, Facebook,..."""

    def __init__(self, credentials: Dict[str, Any]):
        self.credentials = credentials
        self.authenticated = False

    @abstractmethod
    def authenticate(self) -> bool:
        """Xác thực với nền tảng."""
        pass

    @abstractmethod
    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Optional[Path] = None,
        **kwargs
    ) -> str:
        """
        Upload video lên nền tảng.
        Trả về ID của video đã publish.
        """
        pass

    @abstractmethod
    def get_publish_status(self, video_id: str) -> Dict[str, Any]:
        """Kiểm tra trạng thái publish."""
        pass
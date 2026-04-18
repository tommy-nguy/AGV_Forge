"""
Abstract base class cho image provider.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any


class BaseImageProvider(ABC):
    """Interface chung cho mọi image provider (API hoặc local)."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Path:
        """
        Tạo một ảnh từ prompt.

        Args:
            prompt: Mô tả ảnh.
            output_path: Đường dẫn file ảnh đầu ra.
            aspect_ratio: Tỉ lệ khung hình (16:9, 9:16, 1:1).
            negative_prompt: Những thứ cần tránh.
            **kwargs: Tham số bổ sung.

        Returns:
            Đường dẫn đến file ảnh đã tạo.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Kiểm tra provider có sẵn sàng không."""
        pass
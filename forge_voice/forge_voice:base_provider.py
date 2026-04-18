"""
Abstract base class cho voice provider (local và API).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any


class BaseVoiceProvider(ABC):
    """Interface chung cho mọi voice provider."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    def synthesize(self, text: str, voice_profile_id: str, output_path: Path, **kwargs) -> Path:
        """
        Tạo file audio từ text.

        Args:
            text: Văn bản cần đọc.
            voice_profile_id: ID của giọng đọc.
            output_path: Đường dẫn file đầu ra (thường là .wav hoặc .mp3).
            **kwargs: Tham số bổ sung (tốc độ, cảm xúc,...).

        Returns:
            Path đến file audio đã tạo.
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> list:
        """Trả về danh sách voice ID có sẵn."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Kiểm tra provider có sẵn sàng hoạt động không."""
        pass
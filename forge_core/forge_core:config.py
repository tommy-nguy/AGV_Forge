"""
AGV Forge - Configuration Module
Quản lý toàn bộ cấu hình hệ thống, đọc từ biến môi trường và file .env.
Tuân thủ nguyên tắc: frontend-first (có thể sửa qua UI sau này).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Tự động load biến môi trường từ file .env nếu có
load_dotenv()


@dataclass
class ForgeConfig:
    """
    Cấu hình toàn cục cho AGV Forge.
    Mọi đường dẫn mặc định đều nằm trong thư mục người dùng để đảm bảo quyền ghi.
    """

    # ========== LƯU TRỮ ==========
    storage_root: Path = field(
        default_factory=lambda: Path.home() / "AGV_forge_Data"
    )
    """Thư mục gốc chứa toàn bộ dữ liệu: channels, projects, logs."""

    # ========== AI PLANNER ==========
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    """API Key cho Google Gemini (dùng tài khoản cá nhân của người dùng)."""

    gemini_model: str = "gemini-2.0-flash-exp"
    """Model Gemini sử dụng cho planner."""

    # ========== VOICE ==========
    default_voice_mode: str = "trained_brand_voice"
    """
    Chế độ voice mặc định theo đặc tả (Mục 5).
    Các giá trị hợp lệ: trained_brand_voice, manual_audio_import, skip_voice.
    """

    local_tts_provider: str = "piper"
    """Provider TTS local mặc định (piper hoặc coqui)."""

    # ========== PUBLISH ==========
    youtube_client_id: str = field(
        default_factory=lambda: os.getenv("YOUTUBE_CLIENT_ID", "")
    )
    youtube_client_secret: str = field(
        default_factory=lambda: os.getenv("YOUTUBE_CLIENT_SECRET", "")
    )

    facebook_app_id: str = field(
        default_factory=lambda: os.getenv("FACEBOOK_APP_ID", "")
    )
    facebook_app_secret: str = field(
        default_factory=lambda: os.getenv("FACEBOOK_APP_SECRET", "")
    )

    # ========== RETRY & FALLBACK ==========
    max_retry_attempts: int = 5
    """Số lần retry tối đa cho các tác vụ thông minh (planner, detector, flow)."""

    external_api_retry_attempts: int = 3
    """Số lần retry cho các API bên ngoài (publish, render infrastructure)."""

    # ========== DATABASE ==========
    database_path: Optional[Path] = None
    """Đường dẫn đến file SQLite. Nếu None sẽ tự tạo trong storage_root."""

    def __post_init__(self):
        """Khởi tạo thư mục cần thiết sau khi dataclass được tạo."""
        self.storage_root.mkdir(parents=True, exist_ok=True)

        if self.database_path is None:
            self.database_path = self.storage_root / "agv_forge.db"

        # Tạo các thư mục con quan trọng
        (self.storage_root / "channels").mkdir(exist_ok=True)
        (self.storage_root / "projects").mkdir(exist_ok=True)
        (self.storage_root / "logs").mkdir(exist_ok=True)
        (self.storage_root / "voice_samples").mkdir(exist_ok=True)

    def validate(self) -> bool:
        """
        Kiểm tra cấu hình bắt buộc đã được thiết lập chưa.
        Trả về False nếu thiếu API key bắt buộc (có thể chấp nhận nếu dùng local).
        """
        # Gemini API key là bắt buộc cho planner
        if not self.gemini_api_key:
            # Trong môi trường dev có thể chấp nhận, nhưng sẽ log cảnh báo
            import warnings
            warnings.warn("GEMINI_API_KEY chưa được cấu hình. Planner sẽ không hoạt động.")
            return False
        return True


# Singleton instance để dùng toàn cục
_config_instance: Optional[ForgeConfig] = None


def get_config() -> ForgeConfig:
    """Lấy instance cấu hình toàn cục (singleton)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = ForgeConfig()
    return _config_instance


def reload_config() -> ForgeConfig:
    """Tải lại cấu hình (dùng khi file .env thay đổi)."""
    global _config_instance
    load_dotenv(override=True)
    _config_instance = ForgeConfig()
    return _config_instance
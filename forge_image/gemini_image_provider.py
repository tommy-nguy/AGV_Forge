"""
Gemini Imagen API provider (Nano Banana) - Placeholder version for testing.
"""

from pathlib import Path
from typing import Optional, Dict, Any
import structlog
from PIL import Image, ImageDraw

from .base_provider import BaseImageProvider

logger = structlog.get_logger(__name__)


class GeminiImageProvider(BaseImageProvider):
    """Tạo ảnh placeholder (đen trắng) thay vì gọi API Gemini thật."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        logger.warning("GeminiImageProvider is in PLACEHOLDER mode – generating blank images")

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Path:
        """Tạo một ảnh đen với text mô tả đơn giản."""
        output_path = output_path.with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Tạo ảnh với kích thước tương ứng aspect ratio
        if aspect_ratio == "16:9":
            width, height = 1280, 720
        elif aspect_ratio == "9:16":
            width, height = 720, 1280
        else:
            width, height = 800, 800

        img = Image.new('RGB', (width, height), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        # Viết prompt lên ảnh (cắt ngắn nếu quá dài)
        text = prompt[:100] + "..." if len(prompt) > 100 else prompt
        draw.text((20, height // 2), text, fill=(255, 255, 255))

        img.save(output_path)
        logger.info("Placeholder image generated", path=str(output_path))
        return output_path

    def is_available(self) -> bool:
        return True

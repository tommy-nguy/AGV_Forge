"""
Gemini Imagen API provider (Nano Banana) cho System 1.
"""

import time
from pathlib import Path
from typing import Optional, Dict, Any
import structlog
import google.generativeai as genai

from .base_provider import BaseImageProvider

logger = structlog.get_logger(__name__)


class GeminiImageProvider(BaseImageProvider):
    """Sử dụng Gemini Imagen để tạo ảnh."""

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        if not self.api_key:
            raise ValueError("Gemini API key is required")
        genai.configure(api_key=self.api_key)
        # Model tạo ảnh của Gemini (có thể thay đổi)
        self.model_name = self.config.get("model", "imagen-3.0-generate-001")
        self.model = genai.ImageGenerationModel(self.model_name)

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        **kwargs
    ) -> Path:
        """
        Gọi Gemini Imagen API để tạo ảnh.
        Lưu ý: Gemini Imagen có thể có giới hạn rate limit.
        """
        output_path = output_path.with_suffix(".png")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Map aspect_ratio sang định dạng Gemini hỗ trợ
        gemini_aspect = {
            "16:9": "16:9",
            "9:16": "9:16",
            "1:1": "1:1",
            "4:3": "4:3",
        }.get(aspect_ratio, "16:9")

        try:
            logger.info("Calling Gemini Imagen", prompt=prompt[:50], aspect=gemini_aspect)
            response = self.model.generate_images(
                prompt=prompt,
                number_of_images=1,
                aspect_ratio=gemini_aspect,
                negative_prompt=negative_prompt,
            )
            if not response or not response.images:
                raise RuntimeError("Gemini returned no images")

            # Lưu ảnh
            image = response.images[0]
            image.save(str(output_path))
            logger.info("Image generated", path=str(output_path))
            return output_path

        except Exception as e:
            logger.exception("Gemini image generation failed")
            raise RuntimeError(f"Gemini Imagen error: {e}") from e

    def is_available(self) -> bool:
        """Kiểm tra API key có hợp lệ không (có thể kiểm tra bằng cách gọi thử)."""
        try:
            # Gọi một request nhẹ để kiểm tra
            self.model.generate_images(
                prompt="test",
                number_of_images=1,
            )
            return True
        except Exception:
            return False
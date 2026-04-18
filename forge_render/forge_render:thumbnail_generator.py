"""
Tạo thumbnail từ thumbnail_prompt sử dụng Image Provider.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from PIL import Image, ImageDraw, ImageFont

from forge_image import BaseImageProvider, AssetManager

logger = structlog.get_logger(__name__)


class ThumbnailGenerator:
    """Tạo thumbnail và đăng ký vào asset manager."""

    def __init__(self, image_provider: BaseImageProvider, asset_manager: AssetManager):
        self.image_provider = image_provider
        self.asset_manager = asset_manager

    def generate(
        self,
        thumbnail_prompt: Dict[str, Any],
        thumbnail_text: Optional[str] = None,
    ) -> Path:
        """
        Tạo thumbnail từ prompt, overlay text nếu có.

        Args:
            thumbnail_prompt: Dict chứa asset_id, prompt, aspect_ratio, style_notes.
            thumbnail_text: Text overlay (tùy chọn).

        Returns:
            Đường dẫn file thumbnail đã đăng ký.
        """
        asset_id = thumbnail_prompt.get("asset_id", "thumbnail")
        prompt = thumbnail_prompt.get("prompt", "")
        aspect_ratio = thumbnail_prompt.get("aspect_ratio", "16:9")
        style_notes = thumbnail_prompt.get("style_notes", "")

        # Tạo ảnh gốc
        temp_path = self.asset_manager.job_path / "working" / f"{asset_id}_temp.png"
        full_prompt = prompt
        if style_notes:
            full_prompt += f" {style_notes}"

        self.image_provider.generate_image(
            prompt=full_prompt,
            output_path=temp_path,
            aspect_ratio=aspect_ratio,
        )

        # Overlay text nếu có
        final_path = temp_path
        if thumbnail_text:
            final_path = temp_path.with_name(f"{asset_id}_with_text.jpg")
            self._add_text_overlay(temp_path, final_path, thumbnail_text)

        # Đăng ký vào asset manager
        registered_path = self.asset_manager.register_thumbnail(asset_id, final_path, {
            "prompt": prompt,
            "text": thumbnail_text,
        })
        return registered_path

    def _add_text_overlay(self, image_path: Path, output_path: Path, text: str):
        """Thêm text overlay lên ảnh."""
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)

        # Cố gắng dùng font mặc định
        try:
            font = ImageFont.truetype("Arial.ttf", size=60)
        except:
            font = ImageFont.load_default()

        # Lấy kích thước text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Đặt text ở giữa dưới
        x = (img.width - text_width) // 2
        y = img.height - text_height - 50

        # Vẽ viền và text
        draw.text((x-2, y-2), text, font=font, fill="black")
        draw.text((x+2, y-2), text, font=font, fill="black")
        draw.text((x-2, y+2), text, font=font, fill="black")
        draw.text((x+2, y+2), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="white")

        img.save(output_path)
        logger.info("Text overlay added", text=text)
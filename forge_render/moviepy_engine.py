"""
MoviePy Render Engine: dựng video từ timeline DSL.
Phiên bản tạm – tạo video placeholder dùng PIL để vẽ text.
"""

from pathlib import Path
from typing import Dict, Any
import structlog
from moviepy.editor import ColorClip, ImageClip, CompositeVideoClip
from PIL import Image, ImageDraw, ImageFont

logger = structlog.get_logger(__name__)


class MoviePyError(Exception):
    """Lỗi khi render với MoviePy."""
    pass


class MoviePyEngine:
    """Dựng video sử dụng MoviePy (phiên bản rút gọn để test nhanh)."""

    def __init__(self, job_path: Path):
        self.job_path = job_path
        self.output_dir = job_path / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _create_text_image(self, text: str, size=(640, 480)) -> Image.Image:
        """Tạo ảnh PIL với chữ trắng trên nền đen."""
        img = Image.new("RGB", size, color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Dùng font mặc định của PIL
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 48)
        except:
            font = ImageFont.load_default()
        # Tính toán vị trí để căn giữa
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size[0] - text_width) // 2
        y = (size[1] - text_height) // 2
        draw.text((x, y), text, fill="white", font=font)
        return img

    def render(self, resolved_timeline: Dict[str, Any], output_filename: str = "final_video.mp4") -> Path:
        """
        Tạm thời tạo video placeholder màu đen có chữ AGV Forge (dùng PIL).
        """
        output_path = self.output_dir / output_filename

        # Tạo ảnh text và lưu tạm
        img = self._create_text_image("AGV Forge", size=(640, 480))
        temp_img_path = self.output_dir / "_temp_text.png"
        img.save(temp_img_path)

        # Tạo ImageClip từ ảnh
        txt_clip = ImageClip(str(temp_img_path)).set_duration(5)
        
        # Tạo nền đen (phòng trường hợp ảnh trong suốt)
        bg_clip = ColorClip(size=(640, 480), color=(0, 0, 0), duration=5)
        
        video = CompositeVideoClip([bg_clip, txt_clip])
        
        logger.info("Rendering placeholder video (PIL)", output=str(output_path))
        video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio=False,
            verbose=False,
            logger=None
        )
        # Xóa ảnh tạm
        temp_img_path.unlink(missing_ok=True)
        logger.info("Placeholder video rendered", path=str(output_path))
        return output_path

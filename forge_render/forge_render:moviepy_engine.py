"""
MoviePy Render Engine: dựng video từ timeline DSL.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import structlog
from moviepy.editor import (
    VideoFileClip, ImageClip, AudioFileClip, CompositeVideoClip,
    TextClip, CompositeAudioClip, concatenate_videoclips, vfx
)
from moviepy.video.fx import resize, crop

logger = structlog.get_logger(__name__)


class MoviePyError(Exception):
    """Lỗi khi render với MoviePy."""
    pass


class MoviePyEngine:
    """
    Dựng video sử dụng MoviePy.
    Hỗ trợ timeline DSL cơ bản (basic mode).
    """

    def __init__(self, job_path: Path):
        self.job_path = job_path
        self.output_dir = job_path / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(self, resolved_timeline: Dict[str, Any], output_filename: str = "final_video.mp4") -> Path:
        """
        Render video từ timeline đã resolve.

        Args:
            resolved_timeline: Kết quả từ TimelineResolver.resolve().
            output_filename: Tên file đầu ra.

        Returns:
            Đường dẫn file video đã render.
        """
        steps = resolved_timeline["steps"]
        master_audio = resolved_timeline.get("master_audio")

        # Tạo các clip cho từng layer
        layers = {}  # layer -> list of clips
        for step in steps:
            clip = self._create_clip_from_step(step)
            if clip is None:
                continue

            layer = step.get("layer", 1)
            start_ms = step.get("timeline_start_ms", 0)
            duration_ms = step.get("timeline_end_ms", 0) - start_ms

            if duration_ms <= 0:
                continue

            # Đặt vị trí trên timeline
            clip = clip.set_start(start_ms / 1000.0)
            clip = clip.set_duration(duration_ms / 1000.0)

            if layer not in layers:
                layers[layer] = []
            layers[layer].append(clip)

        # Sắp xếp layer và tạo composite
        sorted_layers = sorted(layers.items(), key=lambda x: x[0])
        all_clips = []
        for _, clips in sorted_layers:
            all_clips.extend(clips)

        if not all_clips:
            raise MoviePyError("No valid clips to render")

        # Tạo video composite
        video = CompositeVideoClip(all_clips)

        # Thêm audio nếu có
        if master_audio and Path(master_audio).exists():
            audio_clip = AudioFileClip(master_audio)
            video = video.set_audio(audio_clip)

        # Render
        output_path = self.output_dir / output_filename
        logger.info("Rendering video", output=str(output_path), duration=video.duration)
        video.write_videofile(
            str(output_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
        )
        logger.info("Video rendered", path=str(output_path))
        return output_path

    def _create_clip_from_step(self, step: Dict[str, Any]):
        """Tạo MoviePy clip từ một timeline step."""
        step_type = step.get("type")

        # Video clip
        if step_type in ("video_cut", "video_trim"):
            source = step.get("resolved_source")
            if not source or not Path(source).exists():
                logger.warning("Source video not found", source=source)
                return None
            clip = VideoFileClip(source)
            start = step.get("source_start_ms", 0) / 1000.0
            end = step.get("source_end_ms")
            if end:
                clip = clip.subclip(start, end / 1000.0)
            else:
                clip = clip.subclip(start)
            # Resize nếu cần (giữ nguyên tỉ lệ)
            return clip

        # Image clip
        elif step_type in ("insert_ai_image", "replace_with_ai_image", "hold_image"):
            asset = step.get("resolved_asset")
            if not asset or not Path(asset).exists():
                logger.warning("Image asset not found", asset=asset)
                # Tạo placeholder đen
                return ImageClip(self._create_placeholder((1280, 720)), is_mask=False)
            clip = ImageClip(asset)
            # Thêm hiệu ứng zoom/pan nếu có trong params
            params = step.get("params", {})
            if "zoom" in params:
                clip = clip.resize(lambda t: 1 + 0.1 * t)
            return clip

        # Text overlay
        elif step_type in ("overlay_text", "overlay_thumbnail_text", "overlay_cta"):
            text = step.get("params", {}).get("text", "")
            if not text:
                return None
            # Tạo text clip đơn giản
            txt_clip = TextClip(
                text,
                fontsize=step.get("params", {}).get("font_size", 48),
                color=step.get("params", {}).get("color", "white"),
                font=step.get("params", {}).get("font", "Arial"),
                stroke_color="black",
                stroke_width=2,
            )
            # Đặt vị trí
            position = step.get("params", {}).get("position", "center")
            txt_clip = txt_clip.set_position(position)
            return txt_clip

        # Chuyển cảnh (sẽ xử lý sau, tạm bỏ qua)
        elif step_type in ("hard_cut", "crossfade", "fade_to_black"):
            return None

        else:
            logger.warning("Unknown step type", type=step_type)
            return None

    def _create_placeholder(self, size: Tuple[int, int], color: Tuple[int, int, int] = (0, 0, 0)):
        """Tạo ảnh placeholder (đen)."""
        import numpy as np
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)
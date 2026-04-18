"""
Media Validator - Kiểm tra file đầu vào, trích xuất metadata.
Sử dụng ffprobe (FFmpeg) để lấy thông tin chi tiết.
"""

import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MediaInfo:
    """Thông tin cơ bản của file media."""
    file_path: Path
    format_name: str
    duration_ms: int
    bit_rate: int
    size_bytes: int
    video_streams: List[Dict[str, Any]]
    audio_streams: List[Dict[str, Any]]
    has_video: bool
    has_audio: bool

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000.0


class MediaValidator:
    """Kiểm tra và trích xuất metadata của file media."""

    def __init__(self, ffprobe_path: str = "ffprobe"):
        self.ffprobe_path = ffprobe_path
        self._check_ffprobe()

    def _check_ffprobe(self):
        """Kiểm tra ffprobe có sẵn không."""
        try:
            subprocess.run([self.ffprobe_path, "-version"],
                           capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffprobe not found. Please install FFmpeg.")

    def validate(self, file_path: Path) -> MediaInfo:
        """
        Kiểm tra file media, trả về MediaInfo nếu hợp lệ.

        Raises:
            FileNotFoundError: File không tồn tại.
            ValueError: File không phải media hợp lệ.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Gọi ffprobe để lấy thông tin
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(file_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"ffprobe failed: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from ffprobe: {e}") from e

        # Phân tích streams
        video_streams = []
        audio_streams = []
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_streams.append({
                    "index": stream.get("index"),
                    "codec_name": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "r_frame_rate": stream.get("r_frame_rate"),
                    "duration": float(stream.get("duration", 0)) * 1000 if stream.get("duration") else None,
                })
            elif stream.get("codec_type") == "audio":
                audio_streams.append({
                    "index": stream.get("index"),
                    "codec_name": stream.get("codec_name"),
                    "sample_rate": stream.get("sample_rate"),
                    "channels": stream.get("channels"),
                    "duration": float(stream.get("duration", 0)) * 1000 if stream.get("duration") else None,
                })

        format_info = data.get("format", {})
        duration_str = format_info.get("duration")
        duration_ms = int(float(duration_str) * 1000) if duration_str else 0

        info = MediaInfo(
            file_path=file_path,
            format_name=format_info.get("format_name", ""),
            duration_ms=duration_ms,
            bit_rate=int(format_info.get("bit_rate", 0)),
            size_bytes=int(format_info.get("size", 0)),
            video_streams=video_streams,
            audio_streams=audio_streams,
            has_video=len(video_streams) > 0,
            has_audio=len(audio_streams) > 0,
        )

        # Kiểm tra ràng buộc cơ bản
        if info.duration_ms <= 0:
            raise ValueError("Media has zero duration")

        if not info.has_video and not info.has_audio:
            raise ValueError("Media has no video and no audio")

        logger.info("Media validated", path=str(file_path), duration_ms=info.duration_ms,
                    video=info.has_video, audio=info.has_audio)

        return info
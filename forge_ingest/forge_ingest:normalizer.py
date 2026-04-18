"""
Media Normalizer - Chuẩn hóa video về định dạng chuẩn, trích xuất audio.
Sử dụng FFmpeg.
"""

import subprocess
from pathlib import Path
from typing import Optional, List
import structlog

from .media_validator import MediaInfo

logger = structlog.get_logger(__name__)


class NormalizerError(Exception):
    """Lỗi trong quá trình chuẩn hóa."""
    pass


class MediaNormalizer:
    """
    Chuẩn hóa video và audio.
    Output:
    - Video: H.264 MP4, 30fps, âm thanh AAC.
    - Audio: WAV 16kHz mono (cho ASR).
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        try:
            subprocess.run([self.ffmpeg_path, "-version"],
                           capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg not found. Please install FFmpeg.")

    def normalize_video(self, input_path: Path, output_path: Path,
                        video_codec: str = "libx264",
                        audio_codec: str = "aac",
                        crf: int = 23,
                        preset: str = "medium") -> Path:
        """
        Chuẩn hóa video về MP4 với H.264 và AAC.

        Args:
            input_path: File video gốc.
            output_path: File đầu ra (nên là .mp4).
            video_codec: Codec video.
            audio_codec: Codec audio.
            crf: Chất lượng video (18-28, càng thấp càng tốt).
            preset: Tốc độ encode (ultrafast, fast, medium, slow).

        Returns:
            Path file đã chuẩn hóa.
        """
        output_path = output_path.with_suffix(".mp4")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", video_codec,
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", audio_codec,
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",  # ghi đè
            str(output_path)
        ]
        try:
            logger.info("Normalizing video", input=str(input_path), output=str(output_path))
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Video normalized", output=str(output_path))
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error("Video normalization failed", stderr=e.stderr)
            raise NormalizerError(f"FFmpeg error: {e.stderr}") from e

    def extract_audio(self, input_path: Path, output_path: Path,
                      sample_rate: int = 16000,
                      channels: int = 1,
                      audio_codec: str = "pcm_s16le") -> Path:
        """
        Trích xuất audio từ video thành WAV 16kHz mono (phù hợp cho ASR).

        Args:
            input_path: File video hoặc audio.
            output_path: File đầu ra (nên là .wav).
            sample_rate: Tần số lấy mẫu (mặc định 16kHz cho Whisper).
            channels: Số kênh (1 = mono).
            audio_codec: Codec PCM (mặc định pcm_s16le cho WAV).

        Returns:
            Path file audio.
        """
        output_path = output_path.with_suffix(".wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-acodec", audio_codec,
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-y",
            str(output_path)
        ]
        try:
            logger.info("Extracting audio", input=str(input_path), output=str(output_path))
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Audio extracted", output=str(output_path))
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error("Audio extraction failed", stderr=e.stderr)
            raise NormalizerError(f"FFmpeg error: {e.stderr}") from e
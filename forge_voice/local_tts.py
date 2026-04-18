"""
Local TTS sử dụng Piper (offline, miễn phí).
"""

import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

from .base_provider import BaseVoiceProvider

logger = structlog.get_logger(__name__)


class PiperTTSProvider(BaseVoiceProvider):
    """
    Sử dụng Piper TTS (https://github.com/rhasspy/piper).
    Yêu cầu cài đặt piper và tải model voice tương ứng.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.piper_executable = self.config.get("piper_path", "piper")
        self.model_dir = Path(self.config.get("model_dir", Path.home() / "piper_models"))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.default_voice = self.config.get("default_voice", "en_US-lessac-medium")

    def synthesize(self, text: str, voice_profile_id: str, output_path: Path, **kwargs) -> Path:
        """Gọi piper để tạo file wav."""
        output_path = output_path.with_suffix(".wav")
        model_path = self.model_dir / f"{voice_profile_id}.onnx"
        if not model_path.exists():
            raise FileNotFoundError(f"Voice model not found: {model_path}")

        cmd = [
            self.piper_executable,
            "--model", str(model_path),
            "--output_file", str(output_path),
        ]
        # Thêm tùy chọn tốc độ, v.v. nếu piper hỗ trợ
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                check=True,
            )
            logger.debug("Piper synthesis completed", output=output_path)
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error("Piper synthesis failed", stderr=e.stderr)
            raise RuntimeError(f"Piper error: {e.stderr}") from e

    def get_available_voices(self) -> List[str]:
        """Liệt kê các file .onnx trong model_dir."""
        return [p.stem for p in self.model_dir.glob("*.onnx")]

    def is_available(self) -> bool:
        """Kiểm tra piper có thể chạy được không."""
        try:
            subprocess.run([self.piper_executable, "--help"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
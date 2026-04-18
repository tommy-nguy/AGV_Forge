"""
ElevenLabs API provider (chỉ dùng khi user bật và có API key).
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog
import requests

from .base_provider import BaseVoiceProvider

logger = structlog.get_logger(__name__)


class ElevenLabsProvider(BaseVoiceProvider):
    """Gọi ElevenLabs API để tạo giọng đọc."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required")

    def synthesize(self, text: str, voice_profile_id: str, output_path: Path, **kwargs) -> Path:
        url = f"{self.BASE_URL}/text-to-speech/{voice_profile_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": kwargs.get("stability", 0.5),
                "similarity_boost": kwargs.get("similarity_boost", 0.75),
            }
        }
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        output_path = output_path.with_suffix(".mp3")
        with open(output_path, "wb") as f:
            f.write(response.content)
        logger.info("ElevenLabs synthesis completed", output=output_path)
        return output_path

    def get_available_voices(self) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}/voices"
        headers = {"xi-api-key": self.api_key}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json().get("voices", [])

    def is_available(self) -> bool:
        try:
            self.get_available_voices()
            return True
        except Exception:
            return False
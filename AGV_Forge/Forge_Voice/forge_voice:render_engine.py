"""
Voice Render Engine: render toàn bộ script thành audio master.
Hỗ trợ nhiều provider, chọn provider theo voice_style.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from pydub import AudioSegment

from forge_core import ForgeConfig
from .base_provider import BaseVoiceProvider
from .local_tts import PiperTTSProvider
from .api_tts import ElevenLabsProvider

logger = structlog.get_logger(__name__)


class VoiceRenderEngine:
    def __init__(self, config: ForgeConfig, workspace_root: Path):
        self.config = config
        self.workspace = workspace_root
        self.providers: Dict[str, BaseVoiceProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Khởi tạo các provider dựa trên cấu hình."""
        # Local provider (luôn có nếu cài đặt)
        piper = PiperTTSProvider()
        if piper.is_available():
            self.providers["local_piper"] = piper
        else:
            logger.warning("Piper TTS not available; local voice will be disabled")

        # API provider (chỉ bật nếu user cung cấp key)
        if self.config.youtube_client_id:  # Tạm dùng biến khác, thực tế cần cấu hình riêng
            try:
                eleven = ElevenLabsProvider({"api_key": self.config.youtube_client_id})  # cần thay bằng key thực
                self.providers["api_elevenlabs"] = eleven
            except Exception as e:
                logger.warning("ElevenLabs provider init failed", error=str(e))

    def render_script(
        self,
        script_segments: List[Dict[str, Any]],
        voice_style: Dict[str, Any],
        output_filename: str = "master_audio.wav"
    ) -> Path:
        """
        Render từng segment, sau đó ghép lại thành file audio master.

        Args:
            script_segments: Danh sách segment từ planner (content_script.segments).
            voice_style: Dict chứa 'mode', 'provider', 'voice_profile_id', và các tham số.
            output_filename: Tên file đầu ra.

        Returns:
            Đường dẫn đến file audio master.
        """
        audio_dir = self.workspace / "assets" / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        master = AudioSegment.empty()
        current_pos_ms = 0

        # Xác định provider
        provider_key = voice_style.get("provider", "local_piper")
        if provider_key not in self.providers:
            # Fallback về local nếu có
            if "local_piper" in self.providers:
                provider_key = "local_piper"
                logger.warning("Provider not found, fallback to local_piper", requested=voice_style.get("provider"))
            else:
                raise RuntimeError("No voice provider available")

        provider = self.providers[provider_key]
        voice_id = voice_style.get("voice_profile_id", "default")

        for i, seg in enumerate(script_segments):
            text = seg.get("text", "")
            if not text.strip():
                continue

            seg_start = seg.get("start_ms", current_pos_ms)
            seg_end = seg.get("end_ms")
            # Tạo file audio cho segment
            seg_file = audio_dir / f"seg_{i:03d}.wav"
            provider.synthesize(text, voice_id, seg_file,
                                speed=voice_style.get("speed", 1.0),
                                emotion=voice_style.get("emotion"))

            # Load audio segment
            audio_seg = AudioSegment.from_file(seg_file)
            # Chèn silence để đúng timing
            if seg_start > current_pos_ms:
                silence = AudioSegment.silent(duration=seg_start - current_pos_ms)
                master += silence
                current_pos_ms = seg_start

            master += audio_seg
            current_pos_ms += len(audio_seg)

            # Nếu có end_ms và cần silence đến cuối segment
            if seg_end and seg_end > current_pos_ms:
                silence = AudioSegment.silent(duration=seg_end - current_pos_ms)
                master += silence
                current_pos_ms = seg_end

        # Xuất file master
        output_path = audio_dir / output_filename
        master.export(output_path, format="wav")
        logger.info("Master audio rendered", path=str(output_path), duration_ms=len(master))
        return output_path
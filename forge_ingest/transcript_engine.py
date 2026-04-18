"""
Transcript Engine - Tạo transcript từ audio sử dụng Whisper (local).
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class TranscriptError(Exception):
    """Lỗi khi tạo transcript."""
    pass


class TranscriptEngine:
    """
    Sử dụng OpenAI Whisper (local) để chuyển lời nói thành văn bản.
    Yêu cầu: pip install openai-whisper
    """

    def __init__(self, model_name: str = "base", device: str = "cpu"):
        """
        Args:
            model_name: Whisper model (tiny, base, small, medium, large).
            device: "cpu" hoặc "cuda".
        """
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        """Lazy load Whisper model."""
        if self._model is None:
            try:
                import whisper
                logger.info("Loading Whisper model", model=self.model_name, device=self.device)
                self._model = whisper.load_model(self.model_name, device=self.device)
            except ImportError:
                raise TranscriptError("openai-whisper not installed. Run: pip install openai-whisper")
        return self._model

    def transcribe(self, audio_path: Path, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Chạy nhận dạng giọng nói trên file audio.

        Args:
            audio_path: File audio (WAV, MP3,...).
            language: Mã ngôn ngữ (vd: "vi", "en"). None để tự động phát hiện.

        Returns:
            Dict chứa full text và danh sách segments với timestamp.
        """
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        model = self._load_model()
        logger.info("Transcribing audio", path=str(audio_path), language=language)

        options = {}
        if language:
            options["language"] = language
        options["task"] = "transcribe"
        options["verbose"] = False

        try:
            result = model.transcribe(str(audio_path), **options)
        except Exception as e:
            logger.exception("Whisper transcription failed")
            raise TranscriptError(f"Whisper error: {e}") from e

        # Chuẩn hóa đầu ra
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "segment_id": f"seg_{seg.get('id', 0):03d}",
                "start_ms": int(seg.get("start", 0) * 1000),
                "end_ms": int(seg.get("end", 0) * 1000),
                "text": seg.get("text", "").strip(),
            })

        output = {
            "full_text": result.get("text", "").strip(),
            "language": result.get("language", language or "unknown"),
            "segments": segments,
        }
        logger.info("Transcription completed", segments_count=len(segments))
        return output

    def save_transcript_json(self, data: Dict[str, Any], output_path: Path) -> Path:
        """Lưu transcript dạng JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path

    def generate_srt(self, segments: List[Dict[str, Any]], output_path: Path) -> Path:
        """
        Tạo file SRT từ segments.
        Định dạng:
        1
        00:00:00,000 --> 00:00:03,500
        Text...
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def ms_to_srt_time(ms: int) -> str:
            hours = ms // 3600000
            ms %= 3600000
            minutes = ms // 60000
            ms %= 60000
            seconds = ms // 1000
            milliseconds = ms % 1000
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start = ms_to_srt_time(seg["start_ms"])
                end = ms_to_srt_time(seg["end_ms"])
                f.write(f"{i}\n{start} --> {end}\n{seg['text']}\n\n")
        return output_path
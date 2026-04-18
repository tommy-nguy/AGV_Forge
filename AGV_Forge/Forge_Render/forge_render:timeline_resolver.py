"""
Phân giải edit_timeline từ planner, kiểm tra asset tồn tại,
chuẩn bị dữ liệu cho render engine.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import structlog

from forge_image import AssetManager

logger = structlog.get_logger(__name__)


class TimelineResolver:
    """
    Phân giải timeline: kiểm tra asset reference, chuẩn bị cấu trúc
    để MoviePy engine có thể thực thi.
    """

    def __init__(self, job_path: Path, asset_manager: AssetManager):
        self.job_path = job_path
        self.asset_manager = asset_manager

    def resolve(self, planner_output: Dict[str, Any], master_audio_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Phân giải timeline từ planner output.

        Args:
            planner_output: JSON từ planner (đã validated).
            master_audio_path: Đường dẫn file audio master (nếu có).

        Returns:
            Dict chứa timeline đã resolve và metadata.
        """
        timeline = planner_output.get("edit_timeline", [])
        if not timeline:
            raise ValueError("edit_timeline is empty")

        resolved_steps = []
        missing_assets = []

        for step in timeline:
            step_type = step.get("type")
            resolved_step = step.copy()

            # Xử lý từng loại step
            if step_type in ("video_cut", "video_trim", "video_reorder"):
                source_asset = step.get("source_asset")
                if source_asset:
                    # Kiểm tra file nguồn (video gốc đã chuẩn hóa)
                    source_path = self.job_path / "working" / "normalized_video.mp4"
                    if source_path.exists():
                        resolved_step["resolved_source"] = str(source_path)
                    else:
                        missing_assets.append(source_asset)

            elif step_type in ("insert_ai_image", "replace_with_ai_image"):
                asset_id = step.get("asset_id")
                if asset_id:
                    img_path = self.asset_manager.resolve_image_path(asset_id)
                    if img_path:
                        resolved_step["resolved_asset"] = str(img_path)
                    else:
                        missing_assets.append(asset_id)

            elif step_type == "place_voice_track":
                if master_audio_path and master_audio_path.exists():
                    resolved_step["resolved_audio"] = str(master_audio_path)
                elif master_audio_path:
                    missing_assets.append(str(master_audio_path))

            resolved_steps.append(resolved_step)

        if missing_assets:
            logger.warning("Missing assets in timeline", assets=missing_assets)
            # Không fail ngay, render engine có thể dùng placeholder

        return {
            "steps": resolved_steps,
            "total_duration_ms": self._calculate_total_duration(timeline),
            "missing_assets": missing_assets,
            "master_audio": str(master_audio_path) if master_audio_path else None,
        }

    def _calculate_total_duration(self, timeline: List[Dict]) -> int:
        """Tính tổng thời lượng từ timeline_end_ms lớn nhất."""
        max_end = 0
        for step in timeline:
            end = step.get("timeline_end_ms", 0)
            if end > max_end:
                max_end = end
        return max_end
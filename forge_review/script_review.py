"""
Script Review Gate - cho phép người dùng xem và sửa script trước khi tiếp tục.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import structlog

from forge_core import WorkspaceManager, JobState

logger = structlog.get_logger(__name__)


class ScriptReviewGate:
    """
    Gate dừng job ở trạng thái AWAITING_SCRIPT_REVIEW.
    Người dùng có thể: approve, edit trực tiếp, hoặc yêu cầu AI revise.
    """

    def __init__(self, workspace_manager: WorkspaceManager, job_path: Path):
        self.wm = workspace_manager
        self.job_path = job_path
        self.planner_output_path = job_path / "manifest" / "planner_output.json"

    def get_current_script(self) -> Dict[str, Any]:
        """Lấy script hiện tại từ planner output."""
        if not self.planner_output_path.exists():
            raise FileNotFoundError("Planner output not found")
        with open(self.planner_output_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_script(self, script: Dict[str, Any]) -> None:
        """Lưu script đã chỉnh sửa."""
        with open(self.planner_output_path, "w", encoding="utf-8") as f:
            json.dump(script, f, indent=2, ensure_ascii=False)
        logger.info("Script saved", job_id=self.job_path.name)

    def apply_direct_edit(self, edited_script: Dict[str, Any]) -> None:
        """
        Người dùng sửa trực tiếp script (qua UI/CLI).
        Sau khi sửa, phải regenerate timeline.
        """
        # Lưu script mới
        self.save_script(edited_script)

        # Đánh dấu cần regenerate timeline
        manifest = self.wm.load_manifest(self.job_path)
        manifest["timeline_needs_regeneration"] = True
        self.wm.update_manifest(self.job_path, manifest)

        # Chuyển trạng thái quay lại planning để regenerate
        self.wm.update_state(self.job_path, JobState.PLANNING.value,
                             metadata={"action": "script_edited", "regenerate": True})
        logger.info("Script edited, job routed back to planning", job_id=self.job_path.name)

    def request_ai_revise(self, revision_prompt: str, planner_repair_loop) -> Dict[str, Any]:
        """
        Yêu cầu AI sửa script dựa trên prompt bổ sung.
        Gọi planner repair loop với prompt mới.
        """
        current_script = self.get_current_script()
        # Tạo prompt yêu cầu sửa
        full_prompt = f"""
Revise the following video script based on this feedback:
{revision_prompt}

Current script:
{json.dumps(current_script, indent=2)}

Output the revised script in the same JSON format.
"""
        revised = planner_repair_loop.run_with_repair(full_prompt)
        self.save_script(revised)
        self.wm.update_state(self.job_path, JobState.PLANNING.value,
                             metadata={"action": "ai_revised"})
        logger.info("AI revision completed", job_id=self.job_path.name)
        return revised

    def approve(self) -> None:
        """Phê duyệt script, tiếp tục pipeline."""
        self.wm.update_state(self.job_path, JobState.VOICE_PREPARING.value,
                             metadata={"action": "script_approved"})
        logger.info("Script approved, moving to voice", job_id=self.job_path.name)

    def reject(self, reason: str) -> None:
        """Từ chối script (fail job hoặc quay lại tùy logic)."""
        self.wm.update_state(self.job_path, JobState.FAILED.value,
                             metadata={"action": "script_rejected", "reason": reason})
        logger.warning("Script rejected", job_id=self.job_path.name, reason=reason)
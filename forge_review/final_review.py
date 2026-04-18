"""
Final Review Gate - duyệt video cuối cùng trước khi publish.
"""

from pathlib import Path
from typing import Optional
import structlog

from forge_core import WorkspaceManager, JobState

logger = structlog.get_logger(__name__)


class FinalReviewGate:
    """
    Gate dừng job ở trạng thái AWAITING_FINAL_REVIEW.
    Người dùng có thể approve (publish) hoặc reject (quay lại chỉnh sửa).
    """

    def __init__(self, workspace_manager: WorkspaceManager, job_path: Path):
        self.wm = workspace_manager
        self.job_path = job_path

    def get_video_path(self) -> Optional[Path]:
        """Trả về đường dẫn video cuối cùng nếu có."""
        output_dir = self.job_path / "output"
        videos = list(output_dir.glob("*.mp4"))
        return videos[0] if videos else None

    def get_thumbnail_path(self) -> Optional[Path]:
        """Trả về đường dẫn thumbnail."""
        thumb_dir = self.job_path / "assets" / "thumbnails"
        thumbs = list(thumb_dir.glob("*.jpg")) + list(thumb_dir.glob("*.png"))
        return thumbs[0] if thumbs else None

    def approve(self) -> None:
        """Phê duyệt video, chuyển sang publish."""
        # Kiểm tra xem có cần schedule không
        manifest = self.wm.load_manifest(self.job_path)
        publish_meta = manifest.get("planner_output", {}).get("publish_metadata", {})
        if publish_meta.get("schedule_at"):
            self.wm.update_state(self.job_path, JobState.SCHEDULED.value,
                                 metadata={"action": "final_approved_scheduled"})
        else:
            self.wm.update_state(self.job_path, JobState.PUBLISHING.value,
                                 metadata={"action": "final_approved"})
        logger.info("Final video approved", job_id=self.job_path.name)

    def reject(self, reason: str, edit_issue: bool = True) -> None:
        """
        Từ chối video.
        - edit_issue=True: lỗi dựng, quay về TIMELINE_REFINING.
        - edit_issue=False: lỗi script, quay về PLANNING.
        """
        if edit_issue:
            target_state = JobState.TIMELINE_REFINING.value
        else:
            target_state = JobState.PLANNING.value

        self.wm.update_state(self.job_path, target_state,
                             metadata={"action": "final_rejected", "reason": reason})
        logger.warning("Final video rejected", job_id=self.job_path.name,
                       target_state=target_state, reason=reason)
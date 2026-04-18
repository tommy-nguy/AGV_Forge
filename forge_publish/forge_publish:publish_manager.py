"""
Quản lý publish: lấy cấu hình từ channel, gọi publisher tương ứng.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from datetime import datetime, timedelta

from forge_core import WorkspaceManager, JobState
from .youtube_publisher import YouTubePublisher
from .facebook_publisher import FacebookPublisher
from .base_publisher import BasePublisher, PublishError

logger = structlog.get_logger(__name__)


class PublishManager:
    """
    Điều phối publish cho job.
    Hỗ trợ schedule và batch interval.
    """

    def __init__(self, workspace_manager: WorkspaceManager, job_path: Path):
        self.wm = workspace_manager
        self.job_path = job_path
        self.manifest = self.wm.load_manifest(job_path)

    def get_publish_metadata(self) -> Dict[str, Any]:
        """Lấy publish_metadata từ planner output."""
        planner_path = self.job_path / "manifest" / "planner_output.json"
        if not planner_path.exists():
            return {}
        import json
        with open(planner_path, "r") as f:
            planner = json.load(f)
        return planner.get("publish_metadata", {})

    def get_channel_credentials(self, platform: str) -> Dict[str, Any]:
        """Lấy credentials từ channel snapshot."""
        channel_snapshot = self.manifest.get("channel_snapshot", {})
        if platform == "youtube":
            return {
                "client_id": channel_snapshot.get("youtube_client_id"),
                "client_secret": channel_snapshot.get("youtube_client_secret"),
                "token_path": self.job_path / "working" / "youtube_token.pickle",
            }
        elif platform == "facebook":
            return {
                "app_id": channel_snapshot.get("facebook_app_id"),
                "app_secret": channel_snapshot.get("facebook_app_secret"),
                "page_id": channel_snapshot.get("facebook_page_id"),
                "access_token": channel_snapshot.get("facebook_access_token"),
            }
        return {}

    def publish_to_platform(
        self,
        platform: str,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Publish lên một nền tảng cụ thể.
        Trả về dict chứa platform_id và status.
        """
        creds = self.get_channel_credentials(platform)
        if platform == "youtube":
            publisher = YouTubePublisher(creds)
        elif platform == "facebook":
            publisher = FacebookPublisher(creds)
        else:
            raise ValueError(f"Unsupported platform: {platform}")

        try:
            video_id = publisher.upload_video(
                video_path, title, description, thumbnail_path
            )
            return {"platform": platform, "video_id": video_id, "status": "success"}
        except Exception as e:
            logger.error("Publish failed", platform=platform, error=str(e))
            return {"platform": platform, "video_id": None, "status": "failed", "error": str(e)}

    def publish_all(self) -> List[Dict[str, Any]]:
        """Publish lên tất cả platforms trong publish_metadata."""
        meta = self.get_publish_metadata()
        platforms = meta.get("platforms", ["youtube"])
        video_path = self._get_final_video()
        if not video_path:
            raise PublishError("Final video not found")

        title = self.manifest.get("planner_output", {}).get("title", "AGV Forge Video")
        description = meta.get("caption", "")
        thumbnail = self._get_thumbnail()

        # Kiểm tra schedule
        schedule_at = meta.get("schedule_at")
        if schedule_at:
            schedule_time = datetime.fromisoformat(schedule_at)
            now = datetime.now()
            if schedule_time > now:
                # Chờ đến giờ schedule (trong thực tế sẽ dùng queue/scheduler)
                logger.info("Job scheduled for later", schedule_at=schedule_at)
                self.wm.update_state(self.job_path, JobState.SCHEDULED.value)
                return []  # Chưa publish

        self.wm.update_state(self.job_path, JobState.PUBLISHING.value)
        results = []
        for platform in platforms:
            result = self.publish_to_platform(platform, video_path, title, description, thumbnail)
            results.append(result)

        # Kiểm tra kết quả
        all_success = all(r["status"] == "success" for r in results)
        if all_success:
            self.wm.update_state(self.job_path, JobState.PUBLISHED.value,
                                 metadata={"publish_results": results})
        else:
            self.wm.update_state(self.job_path, JobState.PARTIAL_FAILED.value,
                                 metadata={"publish_results": results})

        return results

    def _get_final_video(self) -> Optional[Path]:
        output_dir = self.job_path / "output"
        videos = list(output_dir.glob("*.mp4"))
        return videos[0] if videos else None

    def _get_thumbnail(self) -> Optional[Path]:
        thumb_dir = self.job_path / "assets" / "thumbnails"
        thumbs = list(thumb_dir.glob("*.jpg")) + list(thumb_dir.glob("*.png"))
        return thumbs[0] if thumbs else None
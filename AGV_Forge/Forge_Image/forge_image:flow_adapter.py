"""
Google Flow Automation Adapter (System 2).
Sẽ được triển khai sau khi System 1 ổn định.
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

from .base_provider import BaseImageProvider

logger = structlog.get_logger(__name__)


class FlowImageProvider(BaseImageProvider):
    """
    Điều khiển Google Flow qua Playwright (browser automation).
    Hiện tại là skeleton, sẽ hoàn thiện sau.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.headless = self.config.get("headless", False)
        self.session_path = Path(self.config.get("session_path", Path.home() / ".agv_forge" / "flow_session"))
        logger.warning("FlowImageProvider is a skeleton, not fully implemented")

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        reference_images: Optional[List[Path]] = None,
        **kwargs
    ) -> Path:
        """Sẽ triển khai sau."""
        raise NotImplementedError("FlowImageProvider is not yet implemented")

    def is_available(self) -> bool:
        return False
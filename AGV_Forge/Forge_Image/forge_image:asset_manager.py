"""
Quản lý asset hình ảnh: đăng ký, theo dõi, resolve.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class AssetManager:
    """Quản lý danh sách asset trong job workspace."""

    def __init__(self, job_path: Path):
        self.job_path = job_path
        self.assets_dir = job_path / "assets"
        self.images_dir = self.assets_dir / "images"
        self.thumbnails_dir = self.assets_dir / "thumbnails"
        self.manifest_path = job_path / "manifest" / "asset_manifest.json"
        self.manifest: Dict[str, Any] = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"images": {}, "thumbnails": {}, "audio": {}}

    def _save_manifest(self):
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

    def register_image(self, asset_id: str, file_path: Path, metadata: Dict[str, Any] = None) -> Path:
        """
        Đăng ký một ảnh vào manifest và copy vào thư mục assets/images.
        Trả về đường dẫn chuẩn trong workspace.
        """
        target_path = self.images_dir / f"{asset_id}.png"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target_path)

        self.manifest["images"][asset_id] = {
            "asset_id": asset_id,
            "path": str(target_path.relative_to(self.job_path)),
            "metadata": metadata or {},
            "generated_at": None,  # có thể thêm timestamp
        }
        self._save_manifest()
        logger.info("Image registered", asset_id=asset_id, path=str(target_path))
        return target_path

    def register_thumbnail(self, asset_id: str, file_path: Path, metadata: Dict[str, Any] = None) -> Path:
        """Đăng ký thumbnail."""
        target_path = self.thumbnails_dir / f"{asset_id}.jpg"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target_path)

        self.manifest["thumbnails"][asset_id] = {
            "asset_id": asset_id,
            "path": str(target_path.relative_to(self.job_path)),
            "metadata": metadata or {},
        }
        self._save_manifest()
        return target_path

    def resolve_image_path(self, asset_id: str) -> Optional[Path]:
        """Trả về đường dẫn tuyệt đối của ảnh đã đăng ký."""
        if asset_id in self.manifest["images"]:
            rel_path = self.manifest["images"][asset_id]["path"]
            return self.job_path / rel_path
        return None

    def get_all_images(self) -> Dict[str, Dict[str, Any]]:
        return self.manifest.get("images", {})

    def get_all_thumbnails(self) -> Dict[str, Dict[str, Any]]:
        return self.manifest.get("thumbnails", {})
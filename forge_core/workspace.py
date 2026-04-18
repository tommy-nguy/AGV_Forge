import os, shutil, hashlib, json
"""
AGV Forge - Workspace Manager
Quản lý cấu trúc thư mục chuẩn cho mỗi job theo Mục 15 của đặc tả.
"""

import json
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Union

import structlog

from .config import ForgeConfig, get_config

logger = structlog.get_logger(__name__)


class WorkspaceError(Exception):
    """Lỗi liên quan đến workspace."""
    pass


class WorkspaceManager:
    """
    Quản lý không gian làm việc của job.
    Mỗi job có một thư mục riêng với cấu trúc con cố định.
    """

    def __init__(self, config: Optional[ForgeConfig] = None):
        self.config = config or get_config()
        self.root = self.config.storage_root / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job_workspace(self, job_id: Optional[str] = None) -> Path:
        """
        Tạo workspace mới cho một job.

        Args:
            job_id: ID của job (tự sinh nếu không cung cấp).

        Returns:
            Path: Đường dẫn đến thư mục gốc của job.

        Raises:
            WorkspaceError: Nếu job_id đã tồn tại hoặc không thể tạo thư mục.
        """
        if job_id is None:
            job_id = self._generate_job_id()

        job_path = self.root / job_id

        if job_path.exists():
            raise WorkspaceError(f"Job workspace đã tồn tại: {job_path}")

        try:
            job_path.mkdir(parents=True)
            logger.info("Creating job workspace", job_id=job_id, path=str(job_path))
        except OSError as e:
            raise WorkspaceError(f"Không thể tạo thư mục workspace: {e}") from e

        # Tạo cấu trúc thư mục con theo đặc tả (Mục 15)
        subdirs = [
            "manifest",
            "input",
            "working",
            "assets/images",
            "assets/thumbnails",
            "assets/audio",
            "output",
            "logs",
        ]
        for sub in subdirs:
            (job_path / sub).mkdir(parents=True, exist_ok=True)

        # Tạo file manifest rỗng
        manifest = self._create_initial_manifest(job_id)
        self._save_manifest(job_path, manifest)

        return job_path

    def _generate_job_id(self) -> str:
        """Tạo ID duy nhất cho job."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"job_{timestamp}_{short_uuid}"

    def _create_initial_manifest(self, job_id: str) -> Dict[str, Any]:
        """Tạo nội dung manifest ban đầu."""
        return {
            "job_id": job_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "state": "created",
            "state_history": [{"state": "created", "timestamp": datetime.now().isoformat()}],
            "channel_snapshot": None,
            "input_assets": [],
            "planner_output_path": None,
            "timeline_final_path": None,
            "output_files": [],
            "error_log": None,
        }

    def get_manifest_path(self, job_path: Path) -> Path:
        """Trả về đường dẫn đến file manifest.json."""
        return job_path / "manifest" / "job_manifest.json"

    def _save_manifest(self, job_path: Path, manifest: Dict[str, Any]) -> None:
        """Ghi manifest ra file."""
        manifest_path = self.get_manifest_path(job_path)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.debug("Manifest saved", job_id=manifest.get("job_id"))

    def load_manifest(self, job_path: Union[Path, str]) -> Dict[str, Any]:
        """
        Đọc manifest của job.

        Args:
            job_path: Đường dẫn đến thư mục job hoặc file manifest.

        Returns:
            Dict chứa dữ liệu manifest.
        """
        path = Path(job_path)
        if path.is_dir():
            manifest_path = self.get_manifest_path(path)
        else:
            manifest_path = path

        if not manifest_path.exists():
            raise WorkspaceError(f"Manifest không tồn tại: {manifest_path}")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise WorkspaceError(f"Manifest bị hỏng (invalid JSON): {e}") from e

    def update_manifest(self, job_path: Path, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Cập nhật manifest và ghi lại file.

        Args:
            job_path: Đường dẫn thư mục job.
            updates: Dictionary chứa các trường cần cập nhật.

        Returns:
            Manifest sau khi cập nhật.
        """
        manifest = self.load_manifest(job_path)
        manifest.update(updates)
        manifest["updated_at"] = datetime.now().isoformat()
        self._save_manifest(job_path, manifest)
        return manifest

    def update_state(self, job_path: Path, new_state: str, metadata: Optional[Dict] = None) -> None:
        """
        Cập nhật trạng thái job và ghi vào lịch sử.

        Args:
            job_path: Đường dẫn thư mục job.
            new_state: Trạng thái mới (theo JobState enum).
            metadata: Thông tin bổ sung cho lần chuyển trạng thái này.
        """
        manifest = self.load_manifest(job_path)
        manifest["state"] = new_state

        state_entry = {
            "state": new_state,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            state_entry["metadata"] = metadata

        if "state_history" not in manifest:
            manifest["state_history"] = []
        manifest["state_history"].append(state_entry)

        manifest["updated_at"] = datetime.now().isoformat()
        self._save_manifest(job_path, manifest)
        logger.info("Job state updated", job_id=manifest["job_id"], new_state=new_state)

    def save_planner_output(self, job_path: Path, planner_json: Dict[str, Any]) -> Path:
        """
        Lưu output của planner vào file planner_output.json trong thư mục manifest.

        Returns:
            Đường dẫn đến file đã lưu.
        """
        output_path = job_path / "manifest" / "planner_output.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(planner_json, f, indent=2, ensure_ascii=False)

        self.update_manifest(job_path, {"planner_output_path": str(output_path)})
        logger.info("Planner output saved", job_id=job_path.name)
        return output_path

    def save_timeline_final(self, job_path: Path, timeline: Dict[str, Any]) -> Path:
        """Lưu timeline cuối cùng trước khi render."""
        output_path = job_path / "manifest" / "timeline_final.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)

        self.update_manifest(job_path, {"timeline_final_path": str(output_path)})
        return output_path

    def get_log_file_path(self, job_path: Path, log_name: str = "job.log") -> Path:
        """Trả về đường dẫn file log trong thư mục logs của job."""
        return job_path / "logs" / log_name

    def archive_job(self, job_path: Path) -> None:
        """Đánh dấu job là archived (có thể xóa sau này)."""
        self.update_state(job_path, "archived")
        # Có thể thêm logic nén workspace lại

    def delete_workspace(self, job_path: Path) -> None:
        """
        Xóa vĩnh viễn workspace của job.
        Chỉ cho phép xóa nếu job nằm trong thư mục projects để tránh xóa nhầm.
        """
        try:
            # Kiểm tra an toàn: job_path phải nằm trong self.root
            if self.root not in job_path.parents and job_path != self.root:
                raise WorkspaceError(f"Không thể xóa thư mục ngoài projects root: {job_path}")

            shutil.rmtree(job_path)
            logger.info("Workspace deleted", path=str(job_path))
        except OSError as e:
            raise WorkspaceError(f"Không thể xóa workspace: {e}") from e

    def list_jobs(self) -> list[Path]:
        """Liệt kê tất cả job workspace hiện có."""
        return [p for p in self.root.iterdir() if p.is_dir()]

    def job_exists(self, job_id: str) -> bool:
        """Kiểm tra job_id đã tồn tại chưa."""
        return (self.root / job_id).exists()
# ========== Compatibility wrappers for job_manager.py ==========
def create_job_workspace(storage_root: str, project_id: str, job_id: str):
    """Tạo workspace và trả về đối tượng WorkspacePaths (tạm)."""
    from pathlib import Path
    wm = WorkspaceManager()
    # WorkspaceManager hiện chỉ nhận config, ta cần tạo config tạm hoặc truyền storage_root
    # Tạm thời tạo workspace thủ công và trả về cấu trúc paths
    root = Path(storage_root).expanduser().resolve() / "projects" / project_id / job_id
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        'root': root,
        'manifest': root / 'manifest',
        'input': root / 'input',
        'working': root / 'working',
        'assets': root / 'assets',
        'output': root / 'output',
        'logs': root / 'logs',
    }
    for p in paths.values():
        p.mkdir(exist_ok=True)
    # Trả về một namespace đơn giản
    from types import SimpleNamespace
    return SimpleNamespace(**paths, 
                           job_manifest_path=paths['manifest'] / 'job_manifest.json',
                           channel_snapshot_path=paths['manifest'] / 'channel_snapshot.json',
                           planner_output_path=paths['manifest'] / 'planner_output.json',
                           timeline_final_path=paths['manifest'] / 'timeline_final.json')

def copy_input_asset(source: Path, dest_dir: Path) -> dict:
    """Copy file nguồn vào thư mục đích, trả về thông tin asset."""
    import shutil
    import hashlib
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / source.name
    shutil.copy2(source, dest_path)
    # Tính hash
    sha256 = hashlib.sha256()
    with open(dest_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return {
        'original_path': str(source),
        'workspace_path': str(dest_path),
        'file_name': source.name,
        'size_bytes': dest_path.stat().st_size,
        'sha256': sha256.hexdigest()
    }

def load_json(path: Path) -> dict:
    import json
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json_atomic(path: Path, data: dict):
    import json
    import tempfile
    import shutil
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

class WorkspacePaths:
    """Lớp giả để tương thích."""
    def __init__(self, root):
        self.root = root
        self.job_manifest_path = root / 'manifest' / 'job_manifest.json'
        self.channel_snapshot_path = root / 'manifest' / 'channel_snapshot.json'
        self.planner_output_path = root / 'manifest' / 'planner_output.json'
        self.timeline_final_path = root / 'manifest' / 'timeline_final.json'
        self.input_dir = root / 'input'
        self.working_dir = root / 'working'
        self.assets_dir = root / 'assets'
        self.output_dir = root / 'output'
        self.logs_dir = root / 'logs'
    def to_dict(self):
        return {k: str(v) for k, v in self.__dict__.items() if not k.startswith('_')}

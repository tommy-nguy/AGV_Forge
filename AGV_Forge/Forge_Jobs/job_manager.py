"""SQLite-backed job manager for AGV Forge.

Responsibilities:
- create project/job records
- snapshot channel config into the workspace
- copy/hash input assets
- keep job manifests in sync with SQLite metadata
- validate state transitions through forge_core.state_machine
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from forge_core.state_machine import JobState, progress_for_state, validate_transition
from forge_core.workspace import WorkspacePaths, copy_input_asset, create_job_workspace, load_json, write_json_atomic
from forge_jobs.channel_manager import ChannelManager, ChannelProfile


class JobValidationError(ValueError):
    """Raised when a job request or update is invalid."""



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class JobRecord:
    job_id: str
    project_id: str
    channel_id: str
    current_state: str
    progress_percent: int
    workspace_root: str
    manifest_path: str
    channel_snapshot_path: str
    input_assets: list[dict[str, Any]] = field(default_factory=list)
    last_error: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobManager:
    """Create and track AGV Forge jobs."""

    def __init__(self, db_path: str | Path, channel_manager: ChannelManager):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.channel_manager = channel_manager
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    current_state TEXT NOT NULL,
                    progress_percent INTEGER NOT NULL,
                    workspace_root TEXT NOT NULL,
                    manifest_path TEXT NOT NULL,
                    channel_snapshot_path TEXT NOT NULL,
                    input_assets TEXT NOT NULL DEFAULT '[]',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_channel_id ON jobs(channel_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(current_state);")
            conn.commit()

    @staticmethod
    def _normalize_input_asset(asset: str | Path | Mapping[str, Any], asset_index: int) -> dict[str, Any]:
        if isinstance(asset, (str, Path)):
            path = str(Path(asset).expanduser())
            return {
                "asset_id": f"input_{asset_index:03d}",
                "asset_type": "raw_media",
                "path": path,
                "copy_to_workspace": True,
            }
        if isinstance(asset, Mapping):
            if not asset.get("path"):
                raise JobValidationError(f"Input asset #{asset_index} is missing required field: path")
            return {
                "asset_id": str(asset.get("asset_id") or f"input_{asset_index:03d}").strip(),
                "asset_type": str(asset.get("asset_type") or "raw_media").strip(),
                "path": str(Path(str(asset["path"])).expanduser()),
                "copy_to_workspace": bool(asset.get("copy_to_workspace", True)),
                "metadata": dict(asset.get("metadata", {})),
            }
        raise JobValidationError(f"Unsupported input asset format at index {asset_index}: {asset!r}")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            project_id=row["project_id"],
            channel_id=row["channel_id"],
            current_state=row["current_state"],
            progress_percent=int(row["progress_percent"]),
            workspace_root=row["workspace_root"],
            manifest_path=row["manifest_path"],
            channel_snapshot_path=row["channel_snapshot_path"],
            input_assets=json.loads(row["input_assets"]),
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _build_job_manifest(
        self,
        *,
        job_id: str,
        project_id: str,
        channel: ChannelProfile,
        workspace: WorkspacePaths,
        input_assets: list[dict[str, Any]],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        return {
            "job_id": job_id,
            "project_id": project_id,
            "channel_id": channel.channel_id,
            "channel_name": channel.channel_name,
            "current_state": JobState.CREATED.value,
            "progress_percent": progress_for_state(JobState.CREATED),
            "created_at": now,
            "updated_at": now,
            "input_assets": input_assets,
            "channel_snapshot_path": str(workspace.channel_snapshot_path),
            "workspace": workspace.to_dict(),
            "metadata": dict(metadata or {}),
            "state_history": [
                {
                    "from_state": None,
                    "to_state": JobState.CREATED.value,
                    "changed_at": now,
                    "reason": "job_created",
                }
            ],
            "artifacts": {
                "planner_output": str(workspace.planner_output_path),
                "timeline_final": str(workspace.timeline_final_path),
                "final_video": str(workspace.output_dir / "final_video.mp4"),
                "final_thumbnail": str(workspace.output_dir / "final_thumbnail.jpg"),
            },
        }

    def _persist_job(self, record: JobRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (
                    job_id, project_id, channel_id, current_state, progress_percent,
                    workspace_root, manifest_path, channel_snapshot_path,
                    input_assets, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.job_id,
                    record.project_id,
                    record.channel_id,
                    record.current_state,
                    record.progress_percent,
                    record.workspace_root,
                    record.manifest_path,
                    record.channel_snapshot_path,
                    json.dumps(record.input_assets),
                    record.last_error,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def create_job(
        self,
        channel_id: str,
        input_assets: Sequence[str | Path | Mapping[str, Any]],
        *,
        project_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JobRecord:
        if not input_assets:
            raise JobValidationError("input_assets must not be empty")

        channel = self.channel_manager.get_channel(channel_id)
        if not channel.is_active:
            raise JobValidationError(f"Channel is inactive and cannot create jobs: {channel_id}")

        job_id = f"job_{uuid.uuid4().hex[:16]}"
        resolved_project_id = project_id or f"prj_{uuid.uuid4().hex[:12]}"
        workspace = create_job_workspace(channel.storage_root, resolved_project_id, job_id)

        normalized_assets = [self._normalize_input_asset(asset, i + 1) for i, asset in enumerate(input_assets)]
        copied_assets: list[dict[str, Any]] = []
        for asset in normalized_assets:
            source_path = Path(asset["path"]).expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                raise JobValidationError(f"Input asset does not exist: {source_path}")

            copied = copy_input_asset(source_path, workspace.input_dir)
            copied_assets.append(
                {
                    "asset_id": asset["asset_id"],
                    "asset_type": asset["asset_type"],
                    "original_path": copied["original_path"],
                    "workspace_path": copied["workspace_path"],
                    "file_name": copied["file_name"],
                    "size_bytes": copied["size_bytes"],
                    "sha256": copied["sha256"],
                    "metadata": asset.get("metadata", {}),
                }
            )

        write_json_atomic(workspace.channel_snapshot_path, channel.to_dict())
        manifest = self._build_job_manifest(
            job_id=job_id,
            project_id=resolved_project_id,
            channel=channel,
            workspace=workspace,
            input_assets=copied_assets,
            metadata=metadata,
        )
        write_json_atomic(workspace.job_manifest_path, manifest)

        record = JobRecord(
            job_id=job_id,
            project_id=resolved_project_id,
            channel_id=channel.channel_id,
            current_state=JobState.CREATED.value,
            progress_percent=progress_for_state(JobState.CREATED),
            workspace_root=str(workspace.root),
            manifest_path=str(workspace.job_manifest_path),
            channel_snapshot_path=str(workspace.channel_snapshot_path),
            input_assets=copied_assets,
            created_at=manifest["created_at"],
            updated_at=manifest["updated_at"],
        )
        self._persist_job(record)
        return record

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return self._row_to_record(row)

    def list_jobs(self, channel_id: str | None = None) -> list[JobRecord]:
        sql = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if channel_id:
            sql += " WHERE channel_id = ?"
            params = (channel_id,)
        sql += " ORDER BY updated_at DESC, created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def update_job_state(self, job_id: str, next_state: str | JobState, *, reason: str = "", error_message: str = "") -> JobRecord:
        record = self.get_job(job_id)
        validate_transition(record.current_state, next_state)
        normalized_next_state = JobState(next_state) if not isinstance(next_state, JobState) else next_state
        now = utc_now_iso()

        manifest = load_json(record.manifest_path)
        state_history = list(manifest.get("state_history", []))
        state_history.append(
            {
                "from_state": record.current_state,
                "to_state": normalized_next_state.value,
                "changed_at": now,
                "reason": reason or "state_update",
                "error_message": error_message,
            }
        )
        manifest["current_state"] = normalized_next_state.value
        manifest["progress_percent"] = progress_for_state(normalized_next_state)
        manifest["updated_at"] = now
        manifest["state_history"] = state_history
        if error_message:
            manifest["last_error"] = error_message
        write_json_atomic(record.manifest_path, manifest)

        updated = JobRecord(
            job_id=record.job_id,
            project_id=record.project_id,
            channel_id=record.channel_id,
            current_state=normalized_next_state.value,
            progress_percent=progress_for_state(normalized_next_state),
            workspace_root=record.workspace_root,
            manifest_path=record.manifest_path,
            channel_snapshot_path=record.channel_snapshot_path,
            input_assets=record.input_assets,
            last_error=error_message,
            created_at=record.created_at,
            updated_at=now,
        )
        self._persist_job(updated)
        return updated

    def attach_error(self, job_id: str, error_message: str) -> JobRecord:
        record = self.get_job(job_id)
        now = utc_now_iso()
        manifest = load_json(record.manifest_path)
        manifest["last_error"] = error_message
        manifest["updated_at"] = now
        write_json_atomic(record.manifest_path, manifest)

        updated = JobRecord(
            job_id=record.job_id,
            project_id=record.project_id,
            channel_id=record.channel_id,
            current_state=record.current_state,
            progress_percent=record.progress_percent,
            workspace_root=record.workspace_root,
            manifest_path=record.manifest_path,
            channel_snapshot_path=record.channel_snapshot_path,
            input_assets=record.input_assets,
            last_error=error_message,
            created_at=record.created_at,
            updated_at=now,
        )
        self._persist_job(updated)
        return updated

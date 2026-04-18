"""SQLite-backed channel/profile manager for AGV Forge.

Implements CRUD for channel profiles based on the project spec's Section 8.
The database starts empty by design: no demo or sample records are inserted.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ALLOWED_VOICE_MODES = {"trained_brand_voice", "manual_audio_import", "skip_voice"}
ALLOWED_BRAND_VOICE_STATUSES = {"untrained", "training", "ready", "failed", "disabled"}
ALLOWED_TIMEZONES_EXAMPLE = "Asia/Bangkok"


class ChannelValidationError(ValueError):
    """Raised when channel data violates required business rules."""



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()



def _normalize_json_list(value: Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    result: list[str] = []
    for item in value:
        if item is None:
            continue
        normalized = str(item).strip()
        if normalized:
            result.append(normalized)
    return result


@dataclass(slots=True)
class ChannelProfile:
    channel_id: str
    channel_name: str
    channel_language: str
    channel_category: str = ""
    is_active: bool = True
    default_voice_mode: str = "trained_brand_voice"
    default_voice_provider: str = ""
    default_voice_profile_id: str = ""
    brand_voice_profile_id: str = ""
    brand_voice_provider: str = ""
    brand_voice_mode: str = ""
    brand_voice_status: str = "untrained"
    training_source_files: list[str] = field(default_factory=list)
    default_subject_identity: str = ""
    default_prompt_bank_id: str = ""
    default_background_sound_id: str = ""
    review_script_enabled: bool = True
    review_final_video_enabled: bool = True
    auto_publish_enabled: bool = False
    default_publish_timezone: str = ALLOWED_TIMEZONES_EXAMPLE
    default_batch_interval_hours: int = 0
    target_platforms: list[str] = field(default_factory=list)
    youtube_account_id: str = ""
    facebook_account_id: str = ""
    api_key_refs: list[str] = field(default_factory=list)
    storage_root: str = ""
    log_root: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChannelManager:
    """Manage channel profiles in a local SQLite database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT NOT NULL,
                    channel_language TEXT NOT NULL,
                    channel_category TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    default_voice_mode TEXT NOT NULL,
                    default_voice_provider TEXT NOT NULL DEFAULT '',
                    default_voice_profile_id TEXT NOT NULL DEFAULT '',
                    brand_voice_profile_id TEXT NOT NULL DEFAULT '',
                    brand_voice_provider TEXT NOT NULL DEFAULT '',
                    brand_voice_mode TEXT NOT NULL DEFAULT '',
                    brand_voice_status TEXT NOT NULL DEFAULT 'untrained',
                    training_source_files TEXT NOT NULL DEFAULT '[]',
                    default_subject_identity TEXT NOT NULL DEFAULT '',
                    default_prompt_bank_id TEXT NOT NULL DEFAULT '',
                    default_background_sound_id TEXT NOT NULL,
                    review_script_enabled INTEGER NOT NULL DEFAULT 1,
                    review_final_video_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_publish_enabled INTEGER NOT NULL DEFAULT 0,
                    default_publish_timezone TEXT NOT NULL,
                    default_batch_interval_hours INTEGER NOT NULL DEFAULT 0,
                    target_platforms TEXT NOT NULL DEFAULT '[]',
                    youtube_account_id TEXT NOT NULL DEFAULT '',
                    facebook_account_id TEXT NOT NULL DEFAULT '',
                    api_key_refs TEXT NOT NULL DEFAULT '[]',
                    storage_root TEXT NOT NULL,
                    log_root TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(is_active);")
            conn.commit()

    @staticmethod
    def _validate_payload(payload: Mapping[str, Any]) -> None:
        required_non_empty = {
            "channel_name": payload.get("channel_name"),
            "channel_language": payload.get("channel_language"),
            "default_voice_mode": payload.get("default_voice_mode"),
            "default_background_sound_id": payload.get("default_background_sound_id"),
            "default_publish_timezone": payload.get("default_publish_timezone"),
            "storage_root": payload.get("storage_root"),
            "log_root": payload.get("log_root"),
        }
        missing = [field for field, value in required_non_empty.items() if not str(value or "").strip()]
        if missing:
            raise ChannelValidationError(f"Missing required channel fields: {', '.join(missing)}")

        voice_mode = str(payload.get("default_voice_mode", "")).strip()
        if voice_mode not in ALLOWED_VOICE_MODES:
            raise ChannelValidationError(
                f"default_voice_mode must be one of {sorted(ALLOWED_VOICE_MODES)}, got {voice_mode!r}"
            )

        brand_status = str(payload.get("brand_voice_status", "untrained")).strip()
        if brand_status not in ALLOWED_BRAND_VOICE_STATUSES:
            raise ChannelValidationError(
                f"brand_voice_status must be one of {sorted(ALLOWED_BRAND_VOICE_STATUSES)}, got {brand_status!r}"
            )

        batch_interval = int(payload.get("default_batch_interval_hours", 0))
        if batch_interval < 0:
            raise ChannelValidationError("default_batch_interval_hours must be >= 0")

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> ChannelProfile:
        return ChannelProfile(
            channel_id=row["channel_id"],
            channel_name=row["channel_name"],
            channel_language=row["channel_language"],
            channel_category=row["channel_category"],
            is_active=bool(row["is_active"]),
            default_voice_mode=row["default_voice_mode"],
            default_voice_provider=row["default_voice_provider"],
            default_voice_profile_id=row["default_voice_profile_id"],
            brand_voice_profile_id=row["brand_voice_profile_id"],
            brand_voice_provider=row["brand_voice_provider"],
            brand_voice_mode=row["brand_voice_mode"],
            brand_voice_status=row["brand_voice_status"],
            training_source_files=json.loads(row["training_source_files"]),
            default_subject_identity=row["default_subject_identity"],
            default_prompt_bank_id=row["default_prompt_bank_id"],
            default_background_sound_id=row["default_background_sound_id"],
            review_script_enabled=bool(row["review_script_enabled"]),
            review_final_video_enabled=bool(row["review_final_video_enabled"]),
            auto_publish_enabled=bool(row["auto_publish_enabled"]),
            default_publish_timezone=row["default_publish_timezone"],
            default_batch_interval_hours=int(row["default_batch_interval_hours"]),
            target_platforms=json.loads(row["target_platforms"]),
            youtube_account_id=row["youtube_account_id"],
            facebook_account_id=row["facebook_account_id"],
            api_key_refs=json.loads(row["api_key_refs"]),
            storage_root=row["storage_root"],
            log_root=row["log_root"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _serialize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "channel_id": payload["channel_id"],
            "channel_name": payload["channel_name"],
            "channel_language": payload["channel_language"],
            "channel_category": payload.get("channel_category", ""),
            "is_active": 1 if bool(payload.get("is_active", True)) else 0,
            "default_voice_mode": payload["default_voice_mode"],
            "default_voice_provider": payload.get("default_voice_provider", ""),
            "default_voice_profile_id": payload.get("default_voice_profile_id", ""),
            "brand_voice_profile_id": payload.get("brand_voice_profile_id", ""),
            "brand_voice_provider": payload.get("brand_voice_provider", ""),
            "brand_voice_mode": payload.get("brand_voice_mode", ""),
            "brand_voice_status": payload.get("brand_voice_status", "untrained"),
            "training_source_files": json.dumps(_normalize_json_list(payload.get("training_source_files"))),
            "default_subject_identity": payload.get("default_subject_identity", ""),
            "default_prompt_bank_id": payload.get("default_prompt_bank_id", ""),
            "default_background_sound_id": payload["default_background_sound_id"],
            "review_script_enabled": 1 if bool(payload.get("review_script_enabled", True)) else 0,
            "review_final_video_enabled": 1 if bool(payload.get("review_final_video_enabled", True)) else 0,
            "auto_publish_enabled": 1 if bool(payload.get("auto_publish_enabled", False)) else 0,
            "default_publish_timezone": payload["default_publish_timezone"],
            "default_batch_interval_hours": int(payload.get("default_batch_interval_hours", 0)),
            "target_platforms": json.dumps(_normalize_json_list(payload.get("target_platforms"))),
            "youtube_account_id": payload.get("youtube_account_id", ""),
            "facebook_account_id": payload.get("facebook_account_id", ""),
            "api_key_refs": json.dumps(_normalize_json_list(payload.get("api_key_refs"))),
            "storage_root": str(Path(payload["storage_root"]).expanduser()),
            "log_root": str(Path(payload["log_root"]).expanduser()),
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
        }

    def create_channel(self, **channel_fields: Any) -> ChannelProfile:
        now = utc_now_iso()
        payload: dict[str, Any] = {
            "channel_id": channel_fields.get("channel_id") or f"chn_{uuid.uuid4().hex[:12]}",
            "channel_name": channel_fields.get("channel_name", "").strip(),
            "channel_language": channel_fields.get("channel_language", "").strip(),
            "channel_category": channel_fields.get("channel_category", "").strip(),
            "is_active": bool(channel_fields.get("is_active", True)),
            "default_voice_mode": channel_fields.get("default_voice_mode", "").strip(),
            "default_voice_provider": channel_fields.get("default_voice_provider", "").strip(),
            "default_voice_profile_id": channel_fields.get("default_voice_profile_id", "").strip(),
            "brand_voice_profile_id": channel_fields.get("brand_voice_profile_id", "").strip(),
            "brand_voice_provider": channel_fields.get("brand_voice_provider", "").strip(),
            "brand_voice_mode": channel_fields.get("brand_voice_mode", "").strip(),
            "brand_voice_status": channel_fields.get("brand_voice_status", "untrained").strip(),
            "training_source_files": channel_fields.get("training_source_files", []),
            "default_subject_identity": channel_fields.get("default_subject_identity", "").strip(),
            "default_prompt_bank_id": channel_fields.get("default_prompt_bank_id", "").strip(),
            "default_background_sound_id": channel_fields.get("default_background_sound_id", "").strip(),
            "review_script_enabled": bool(channel_fields.get("review_script_enabled", True)),
            "review_final_video_enabled": bool(channel_fields.get("review_final_video_enabled", True)),
            "auto_publish_enabled": bool(channel_fields.get("auto_publish_enabled", False)),
            "default_publish_timezone": channel_fields.get("default_publish_timezone", ALLOWED_TIMEZONES_EXAMPLE).strip(),
            "default_batch_interval_hours": int(channel_fields.get("default_batch_interval_hours", 0)),
            "target_platforms": channel_fields.get("target_platforms", []),
            "youtube_account_id": channel_fields.get("youtube_account_id", "").strip(),
            "facebook_account_id": channel_fields.get("facebook_account_id", "").strip(),
            "api_key_refs": channel_fields.get("api_key_refs", []),
            "storage_root": channel_fields.get("storage_root", "").strip(),
            "log_root": channel_fields.get("log_root", "").strip(),
            "created_at": now,
            "updated_at": now,
        }
        self._validate_payload(payload)
        serialized = self._serialize_payload(payload)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO channels (
                    channel_id, channel_name, channel_language, channel_category, is_active,
                    default_voice_mode, default_voice_provider, default_voice_profile_id,
                    brand_voice_profile_id, brand_voice_provider, brand_voice_mode,
                    brand_voice_status, training_source_files, default_subject_identity,
                    default_prompt_bank_id, default_background_sound_id,
                    review_script_enabled, review_final_video_enabled, auto_publish_enabled,
                    default_publish_timezone, default_batch_interval_hours, target_platforms,
                    youtube_account_id, facebook_account_id, api_key_refs,
                    storage_root, log_root, created_at, updated_at
                ) VALUES (
                    :channel_id, :channel_name, :channel_language, :channel_category, :is_active,
                    :default_voice_mode, :default_voice_provider, :default_voice_profile_id,
                    :brand_voice_profile_id, :brand_voice_provider, :brand_voice_mode,
                    :brand_voice_status, :training_source_files, :default_subject_identity,
                    :default_prompt_bank_id, :default_background_sound_id,
                    :review_script_enabled, :review_final_video_enabled, :auto_publish_enabled,
                    :default_publish_timezone, :default_batch_interval_hours, :target_platforms,
                    :youtube_account_id, :facebook_account_id, :api_key_refs,
                    :storage_root, :log_root, :created_at, :updated_at
                );
                """,
                serialized,
            )
            conn.commit()
        return self.get_channel(payload["channel_id"])

    def get_channel(self, channel_id: str) -> ChannelProfile:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        if row is None:
            raise KeyError(f"Channel not found: {channel_id}")
        return self._row_to_profile(row)

    def list_channels(self, include_inactive: bool = True) -> list[ChannelProfile]:
        sql = "SELECT * FROM channels"
        params: tuple[Any, ...] = ()
        if not include_inactive:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY updated_at DESC, channel_name ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_profile(row) for row in rows]

    def update_channel(self, channel_id: str, **changes: Any) -> ChannelProfile:
        current = self.get_channel(channel_id).to_dict()
        disallowed = {"channel_id", "created_at"}
        for key in disallowed:
            changes.pop(key, None)
        current.update(changes)
        current["updated_at"] = utc_now_iso()
        self._validate_payload(current)
        serialized = self._serialize_payload(current)

        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE channels SET
                    channel_name = :channel_name,
                    channel_language = :channel_language,
                    channel_category = :channel_category,
                    is_active = :is_active,
                    default_voice_mode = :default_voice_mode,
                    default_voice_provider = :default_voice_provider,
                    default_voice_profile_id = :default_voice_profile_id,
                    brand_voice_profile_id = :brand_voice_profile_id,
                    brand_voice_provider = :brand_voice_provider,
                    brand_voice_mode = :brand_voice_mode,
                    brand_voice_status = :brand_voice_status,
                    training_source_files = :training_source_files,
                    default_subject_identity = :default_subject_identity,
                    default_prompt_bank_id = :default_prompt_bank_id,
                    default_background_sound_id = :default_background_sound_id,
                    review_script_enabled = :review_script_enabled,
                    review_final_video_enabled = :review_final_video_enabled,
                    auto_publish_enabled = :auto_publish_enabled,
                    default_publish_timezone = :default_publish_timezone,
                    default_batch_interval_hours = :default_batch_interval_hours,
                    target_platforms = :target_platforms,
                    youtube_account_id = :youtube_account_id,
                    facebook_account_id = :facebook_account_id,
                    api_key_refs = :api_key_refs,
                    storage_root = :storage_root,
                    log_root = :log_root,
                    updated_at = :updated_at
                WHERE channel_id = :channel_id;
                """,
                serialized,
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Channel not found: {channel_id}")
            conn.commit()
        return self.get_channel(channel_id)

    def delete_channel(self, channel_id: str) -> None:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            if cursor.rowcount == 0:
                raise KeyError(f"Channel not found: {channel_id}")
            conn.commit()

    def deactivate_channel(self, channel_id: str) -> ChannelProfile:
        return self.update_channel(channel_id, is_active=False)

    def activate_channel(self, channel_id: str) -> ChannelProfile:
        return self.update_channel(channel_id, is_active=True)

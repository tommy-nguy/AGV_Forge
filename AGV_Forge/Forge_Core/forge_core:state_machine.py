"""
AGV Forge - State Machine Module
Định nghĩa đầy đủ các trạng thái job và quy tắc chuyển đổi.
Tuân thủ nghiêm ngặt Mục 7 của đặc tả.
"""

from enum import Enum
from typing import List, Optional, Set
from datetime import datetime


class JobState(str, Enum):
    """
    Trạng thái của một job trong pipeline.
    Thứ tự enum phản ánh luồng chính: created → ... → published.
    """

    # Giai đoạn khởi tạo
    CREATED = "created"
    INGESTING = "ingesting"
    NORMALIZING = "normalizing"

    # Giai đoạn xử lý nội dung
    TRANSCRIBING = "transcribing"
    PLANNING = "planning"
    AWAITING_SCRIPT_REVIEW = "awaiting_script_review"

    # Giai đoạn sản xuất assets
    VOICE_PREPARING = "voice_preparing"
    VOICE_TRAINING = "voice_training"
    VOICE_RENDERING = "voice_rendering"
    IMAGE_GENERATING = "image_generating"
    TIMELINE_REFINING = "timeline_refining"

    # Giai đoạn hoàn thiện
    RENDERING = "rendering"
    AWAITING_FINAL_REVIEW = "awaiting_final_review"

    # Giai đoạn publish
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"

    # Trạng thái lỗi / kết thúc
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    ARCHIVED = "archived"

    @classmethod
    def is_terminal(cls, state: 'JobState') -> bool:
        """Trạng thái kết thúc (không thể chuyển tiếp)."""
        return state in {cls.PUBLISHED, cls.FAILED, cls.ARCHIVED}

    @classmethod
    def is_review_gate(cls, state: 'JobState') -> bool:
        """Trạng thái yêu cầu người dùng can thiệp (review)."""
        return state in {cls.AWAITING_SCRIPT_REVIEW, cls.AWAITING_FINAL_REVIEW}

    @classmethod
    def is_error_state(cls, state: 'JobState') -> bool:
        """Trạng thái lỗi cần xử lý."""
        return state in {cls.PARTIAL_FAILED, cls.FAILED}


class StateTransitionError(Exception):
    """Lỗi khi cố gắng chuyển trạng thái không hợp lệ."""
    pass


class JobStateMachine:
    """
    Máy trạng thái cho một job.
    Đảm bảo chỉ chuyển trạng thái theo đúng luồng quy định.
    """

    # Định nghĩa các chuyển tiếp hợp lệ (từ trạng thái hiện tại -> danh sách trạng thái đích)
    _TRANSITIONS: dict[JobState, Set[JobState]] = {
        JobState.CREATED: {JobState.INGESTING},

        JobState.INGESTING: {JobState.NORMALIZING, JobState.FAILED},

        JobState.NORMALIZING: {JobState.TRANSCRIBING, JobState.FAILED},

        JobState.TRANSCRIBING: {JobState.PLANNING, JobState.FAILED},

        JobState.PLANNING: {JobState.AWAITING_SCRIPT_REVIEW, JobState.FAILED},

        JobState.AWAITING_SCRIPT_REVIEW: {
            JobState.VOICE_PREPARING,      # approve
            JobState.PLANNING,             # reject do script sai (regenerate)
            JobState.FAILED
        },

        JobState.VOICE_PREPARING: {JobState.VOICE_TRAINING, JobState.VOICE_RENDERING, JobState.FAILED},

        JobState.VOICE_TRAINING: {JobState.VOICE_RENDERING, JobState.FAILED},

        JobState.VOICE_RENDERING: {JobState.IMAGE_GENERATING, JobState.FAILED},

        JobState.IMAGE_GENERATING: {JobState.TIMELINE_REFINING, JobState.FAILED},

        JobState.TIMELINE_REFINING: {JobState.RENDERING, JobState.FAILED},

        JobState.RENDERING: {JobState.AWAITING_FINAL_REVIEW, JobState.FAILED},

        JobState.AWAITING_FINAL_REVIEW: {
            JobState.SCHEDULED,             # approve
            JobState.TIMELINE_REFINING,     # reject do edit lệch
            JobState.PLANNING,              # reject do script sai
            JobState.FAILED
        },

        JobState.SCHEDULED: {JobState.PUBLISHING, JobState.FAILED},

        JobState.PUBLISHING: {JobState.PUBLISHED, JobState.PARTIAL_FAILED, JobState.FAILED},

        JobState.PUBLISHED: set(),      # terminal
        JobState.PARTIAL_FAILED: {JobState.ARCHIVED, JobState.FAILED},
        JobState.FAILED: {JobState.ARCHIVED},
        JobState.ARCHIVED: set(),       # terminal
    }

    def __init__(self, initial_state: JobState = JobState.CREATED):
        self._state = initial_state
        self._history: List[tuple[JobState, datetime]] = [
            (initial_state, datetime.now())
        ]

    @property
    def state(self) -> JobState:
        return self._state

    @property
    def history(self) -> List[tuple[JobState, datetime]]:
        """Lịch sử chuyển trạng thái (state, timestamp)."""
        return self._history.copy()

    def can_transition_to(self, target: JobState) -> bool:
        """Kiểm tra xem có thể chuyển đến trạng thái target không."""
        if self._state not in self._TRANSITIONS:
            return False
        return target in self._TRANSITIONS[self._state]

    def transition_to(self, target: JobState) -> bool:
        """
        Thực hiện chuyển trạng thái.
        Trả về True nếu thành công, raise StateTransitionError nếu không hợp lệ.
        """
        if not self.can_transition_to(target):
            raise StateTransitionError(
                f"Không thể chuyển từ '{self._state.value}' sang '{target.value}'"
            )

        self._state = target
        self._history.append((target, datetime.now()))
        return True

    def force_transition(self, target: JobState) -> None:
        """
        Ép buộc chuyển trạng thái (chỉ dùng trong trường hợp khẩn cấp, debug).
        Bỏ qua kiểm tra tính hợp lệ.
        """
        import warnings
        warnings.warn(f"Force transition from {self._state} to {target}", stacklevel=2)
        self._state = target
        self._history.append((target, datetime.now()))

    def rollback_to_review(self) -> Optional[JobState]:
        """
        Khi reject ở final review, quay về đúng gate.
        - Nếu do edit lệch -> quay về TIMELINE_REFINING
        - Nếu do script sai -> quay về PLANNING
        Phương thức này chỉ gợi ý; logic cụ thể do caller quyết định dựa trên lý do reject.
        """
        # Mặc định trả về PLANNING nếu không rõ lý do
        return JobState.PLANNING

    def to_dict(self) -> dict:
        """Serialize trạng thái để lưu vào manifest."""
        return {
            "current_state": self._state.value,
            "history": [(s.value, dt.isoformat()) for s, dt in self._history]
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'JobStateMachine':
        """Khôi phục state machine từ dict."""
        current = JobState(data["current_state"])
        sm = cls(initial_state=current)
        # Khôi phục history (nếu cần)
        sm._history = [
            (JobState(s), datetime.fromisoformat(dt))
            for s, dt in data.get("history", [])
        ]
        return sm


# ========== State Groups cho Dashboard (Mục 13) ==========

STATE_GROUPS = {
    "queued_to_planning": {
        JobState.CREATED,
        JobState.INGESTING,
        JobState.NORMALIZING,
        JobState.TRANSCRIBING,
        JobState.PLANNING,
    },
    "review_to_render": {
        JobState.AWAITING_SCRIPT_REVIEW,
        JobState.VOICE_PREPARING,
        JobState.VOICE_TRAINING,
        JobState.VOICE_RENDERING,
        JobState.IMAGE_GENERATING,
        JobState.TIMELINE_REFINING,
        JobState.RENDERING,
        JobState.AWAITING_FINAL_REVIEW,
    },
    "publish": {
        JobState.SCHEDULED,
        JobState.PUBLISHING,
        JobState.PUBLISHED,
    },
    "error": {
        JobState.PARTIAL_FAILED,
        JobState.FAILED,
    },
}


def get_state_group(state: JobState) -> str:
    """Trả về tên nhóm trạng thái (dùng cho dashboard)."""
    for group_name, states in STATE_GROUPS.items():
        if state in states:
            return group_name
    return "unknown"
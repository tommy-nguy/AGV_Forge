"""
AGV Forge - Core Module
Cung cấp các thành phần nền tảng: config, state machine, workspace, logging.
"""

from .config import ForgeConfig, get_config, reload_config
from .state_machine import JobState, JobStateMachine, StateTransitionError, get_state_group, STATE_GROUPS
from .workspace import WorkspaceManager, WorkspaceError
from .logging_config import configure_logging, get_logger, JobLogger

__all__ = [
    # Config
    "ForgeConfig",
    "get_config",
    "reload_config",
    # State machine
    "JobState",
    "JobStateMachine",
    "StateTransitionError",
    "get_state_group",
    "STATE_GROUPS",
    # Workspace
    "WorkspaceManager",
    "WorkspaceError",
    # Logging
    "configure_logging",
    "get_logger",
    "JobLogger",
]
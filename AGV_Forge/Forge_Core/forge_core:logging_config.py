"""
AGV Forge - Logging Configuration
Thiết lập logging có cấu trúc sử dụng structlog.
Ghi log vào cả console và file (trong thư mục logs của từng job hoặc toàn cục).
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.processors import (
    JSONRenderer,
    TimeStamper,
    add_log_level,
    StackInfoRenderer,
    format_exc_info,
    UnicodeDecoder,
)


def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    json_format: bool = False,
) -> None:
    """
    Cấu hình logging cho toàn hệ thống.

    Args:
        log_level: Mức log (DEBUG, INFO, WARNING, ERROR).
        log_file: Nếu cung cấp, ghi log ra file này.
        json_format: Nếu True, log dưới dạng JSON (phù hợp cho machine parsing).
    """
    # Cấu hình logging tiêu chuẩn
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Danh sách processors cho structlog
    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        TimeStamper(fmt="iso"),
        StackInfoRenderer(),
        format_exc_info,
        UnicodeDecoder(),
    ]

    if json_format:
        # Render ra JSON
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            JSONRenderer(sort_keys=True),
        ]
    else:
        # Render ra console đẹp
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]

    # Cấu hình structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Nếu có log_file, thêm file handler vào root logger
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(getattr(logging, log_level.upper()))
        # Định dạng log file có thể khác console
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str = "agv_forge") -> structlog.BoundLogger:
    """
    Lấy logger đã được cấu hình.

    Args:
        name: Tên logger (thường là __name__ của module).

    Returns:
        structlog.BoundLogger đã sẵn sàng sử dụng.
    """
    return structlog.get_logger(name)


def bind_job_context(logger: structlog.BoundLogger, job_id: str, **kwargs) -> structlog.BoundLogger:
    """
    Gắn thông tin job vào logger để tất cả log sau đó đều có context này.

    Args:
        logger: Logger gốc.
        job_id: ID của job hiện tại.
        **kwargs: Các context bổ sung (channel_id, step, ...)

    Returns:
        Logger mới đã được bind context.
    """
    return logger.bind(job_id=job_id, **kwargs)


class JobLogger:
    """
    Helper để quản lý logging cho một job cụ thể.
    Tự động ghi log vào file trong workspace và console.
    """

    def __init__(self, job_path: Path, log_name: str = "job.log"):
        self.job_path = job_path
        self.log_file = job_path / "logs" / log_name
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Lấy job_id từ tên thư mục
        self.job_id = job_path.name

        # Tạo file handler riêng cho job này
        self.file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        self.file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        self.file_handler.setFormatter(formatter)

        # Thêm handler vào root logger (hoặc logger riêng)
        self.logger = structlog.get_logger().bind(job_id=self.job_id)
        logging.getLogger().addHandler(self.file_handler)

    def info(self, event: str, **kwargs):
        self.logger.info(event, **kwargs)

    def debug(self, event: str, **kwargs):
        self.logger.debug(event, **kwargs)

    def warning(self, event: str, **kwargs):
        self.logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs):
        self.logger.error(event, **kwargs)

    def exception(self, event: str, **kwargs):
        self.logger.exception(event, **kwargs)

    def close(self):
        """Gỡ bỏ file handler khi job kết thúc."""
        logging.getLogger().removeHandler(self.file_handler)
        self.file_handler.close()
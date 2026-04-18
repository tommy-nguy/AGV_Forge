"""
Repair loop: gửi lỗi có cấu trúc cho Gemini để sửa JSON, tối đa 5 lần.
"""

from typing import Dict, Any, List, Callable, Optional
import structlog

from .gemini_adapter import GeminiPlanner, GeminiPlannerError
from .schema_validator import PlannerValidator, ValidationError

logger = structlog.get_logger(__name__)


class PlannerRepairLoop:
    MAX_RETRY = 5

    def __init__(self, planner: GeminiPlanner, validator: PlannerValidator):
        self.planner = planner
        self.validator = validator

    def run_with_repair(self, prompt: str) -> Dict[str, Any]:
        """
        Gọi planner, nếu validation fail thì gửi lại lỗi để sửa.
        Trả về JSON đã validated hoặc raise exception nếu hết retry.
        """
        current_prompt = prompt
        attempt = 0
        last_output = None

        while attempt < self.MAX_RETRY:
            attempt += 1
            logger.info("Planner attempt", attempt=attempt)

            try:
                output = self.planner.generate_plan(current_prompt)
                passed, errors = self.validator.validate_all(output)

                if passed:
                    logger.info("Planner output validated successfully", attempt=attempt)
                    return output

                # Nếu không pass, tạo repair prompt
                logger.warning("Validation failed", attempt=attempt, error_count=len(errors))
                last_output = output
                current_prompt = self._build_repair_prompt(prompt, output, errors)

            except GeminiPlannerError as e:
                logger.error("Gemini API error during attempt", attempt=attempt, error=str(e))
                if attempt >= self.MAX_RETRY:
                    raise
            except Exception as e:
                logger.exception("Unexpected error during repair loop")
                raise

        # Hết retry
        raise ValidationError(
            f"Planner failed validation after {self.MAX_RETRY} attempts",
            errors=errors if 'errors' in locals() else []
        )

    def _build_repair_prompt(self, original_prompt: str, invalid_json: Dict[str, Any], errors: List[Dict]) -> str:
        """Tạo prompt yêu cầu sửa lỗi dựa trên danh sách lỗi có cấu trúc."""
        error_text = "\n".join(
            f"- {err['level']} error at {err['path']}: {err['message']}"
            for err in errors
        )
        return f"""
Your previous JSON output failed validation with the following errors:
{error_text}

Original prompt:
{original_prompt}

Please correct the JSON according to the schema and semantic rules. Output ONLY the corrected JSON.
"""
"""
Gemini Adapter for AI Planner.
Gọi Gemini Pro API và trả về JSON đã parse.
"""

import json
import google.generativeai as genai
from typing import Dict, Any, Optional
import structlog

from forge_core import ForgeConfig

logger = structlog.get_logger(__name__)


class GeminiPlannerError(Exception):
    """Lỗi khi gọi Gemini API."""
    pass


class GeminiPlanner:
    def __init__(self, config: ForgeConfig):
        self.config = config
        if not config.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiPlanner")
        genai.configure(api_key=config.gemini_api_key)
        self.model = genai.GenerativeModel(config.gemini_model)

    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        """
        Gửi prompt đến Gemini và trả về JSON đã parse.
        Prompt phải yêu cầu output JSON theo schema quy định.
        """
        try:
            logger.debug("Calling Gemini API", model=self.config.gemini_model)
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            # Parse JSON từ response
            raw_text = response.text
            if not raw_text:
                raise GeminiPlannerError("Gemini returned empty response")

            # Clean markdown code fences nếu có
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini JSON response", error=str(e), response=raw_text[:200])
            raise GeminiPlannerError(f"Invalid JSON from Gemini: {e}") from e
        except Exception as e:
            logger.exception("Gemini API call failed")
            raise GeminiPlannerError(f"Gemini API error: {e}") from e
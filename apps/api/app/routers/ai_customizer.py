"""NVIDIA AI API Integration for UI & Report Customization.

Connects to NVIDIA API:
  base_url: https://integrate.api.nvidia.com/v1
  model: z-ai/glm-5.2
  api_key: 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
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional
import urllib.request
import urllib.error

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import require_user
from ..db import UserRow

logger = logging.getLogger(__name__)
router = APIRouter()

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY = os.getenv(
    "NVIDIA_API_KEY",
    "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",
)
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "z-ai/glm-5.2")

SYSTEM_PROMPT = """
You are an expert UI & Report Customization Assistant embedded inside a business application.

Your ONLY job is to help the user customize the look, layout, labels, themes, and report/export formats of the application.

STRICT RULES (NEVER BREAK THESE):

1. You can ONLY modify presentation and configuration layers.
2. You must NEVER change, suggest, or generate:
   - Business logic
   - Calculations or formulas
   - Database schema or data models
   - API endpoints or data queries
   - Authentication, permissions, or security rules
   - Core workflows or validation rules

3. All changes must be expressed as configuration only (JSON, theme tokens, layout definitions, or report templates).
4. Always preserve existing data and functionality.
5. If the user asks for something that would require logic or data changes, politely refuse and explain that only visual/layout/report formatting changes are allowed.

WHAT YOU CAN DO:
- Change colors, fonts, spacing, borders, shadows (via design tokens / theme)
- Reorder, show/hide, resize UI components and widgets
- Change labels, titles, placeholders, and help text
- Modify dashboard layouts and widget arrangements
- Customize report columns (order, visibility, formatting, grouping)
- Change report headers, footers, logos, page size, orientation
- Adjust export styles (PDF, Excel, CSV presentation)
- Create or update themes (light/dark/custom)

RESPONSE FORMAT:
Always return your output as a JSON object with these keys:
{
  "explanation": "Short confirmation of what you understood and brief explanation of visual effect",
  "config": {
    "theme": "ocean|emerald|purple|amber|dark|light",
    "filters": {
      "gender": "Female|Male",
      "min_age": 18,
      "max_age": 25,
      "verified": true|false,
      "house_number": "..."
    },
    "columns": "all|basic|identity",
    "export": "excel|csv|json"
  }
}
"""


class AiCustomizeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    current_config: Optional[Dict[str, Any]] = None


class AiCustomizeResponse(BaseModel):
    explanation: str
    config: Dict[str, Any]
    raw_ai_response: Optional[str] = None


def _local_fallback_customize(prompt: str) -> Dict[str, Any]:
    """Deterministic local rule engine fallback if NVIDIA API is offline."""
    p = prompt.lower()
    config: Dict[str, Any] = {}
    explanation_parts = []

    if "emerald" in p or "green" in p:
      config["theme"] = "emerald"
      explanation_parts.append("Applied Emerald Green color theme.")
    elif "purple" in p or "cyber" in p:
      config["theme"] = "purple"
      explanation_parts.append("Applied Cyberpunk Purple theme.")
    elif "amber" in p or "sunset" in p or "gold" in p:
      config["theme"] = "amber"
      explanation_parts.append("Applied Sunset Amber theme.")
    elif "blue" in p or "ocean" in p:
      config["theme"] = "ocean"
      explanation_parts.append("Applied Ocean Blue modern theme.")
    elif "dark" in p or "night" in p:
      config["theme"] = "dark"
      explanation_parts.append("Enabled Dark Mode.")
    elif "light" in p or "day" in p:
      config["theme"] = "light"
      explanation_parts.append("Enabled Light Mode.")

    filters: Dict[str, Any] = {}
    if "female" in p or "women" in p:
      filters["gender"] = "Female"
      explanation_parts.append("Filtered for Female voters.")
    elif "male" in p or "men" in p:
      filters["gender"] = "Male"
      explanation_parts.append("Filtered for Male voters.")

    if "18-25" in p or "young" in p:
      filters["min_age"] = 18
      filters["max_age"] = 25
      explanation_parts.append("Filtered for age group 18-25.")
    elif "unverified" in p or "pending" in p:
      filters["verified"] = False
      explanation_parts.append("Filtered for Unverified records.")

    if filters:
      config["filters"] = filters

    if "all columns" in p or "23 columns" in p:
      config["columns"] = "all"
      explanation_parts.append("Expanded view to show all 23 database columns.")
    elif "basic" in p or "identity" in p:
      config["columns"] = "basic"
      explanation_parts.append("Applied basic identity column preset.")

    if "excel" in p or "xlsx" in p:
      config["export"] = "excel"
      explanation_parts.append("Triggered Excel report export.")
    elif "csv" in p:
      config["export"] = "csv"
      explanation_parts.append("Triggered CSV report export.")

    explanation = " ".join(explanation_parts) if explanation_parts else f"Customized workspace UI based on prompt: '{prompt}'"

    return {
        "explanation": explanation,
        "config": config,
    }


@router.post("/customize", response_model=AiCustomizeResponse)
def customize_ui_with_ai(
    req: AiCustomizeRequest,
    _user: UserRow = Depends(require_user),
) -> AiCustomizeResponse:
    """Call NVIDIA LLM API to process user UI customization prompt."""
    url = f"{NVIDIA_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.prompt},
        ],
        "temperature": 0.7,
        "top_p": 1,
        "max_tokens": 2048,
    }

    try:
        req_data = json.dumps(payload).encode("utf-8")
        httpx_req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
        with urllib.request.urlopen(httpx_req, timeout=12) as resp:
            resp_bytes = resp.read()
            resp_json = json.loads(resp_bytes.decode("utf-8"))

        choices = resp_json.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            # Extract JSON block from markdown ```json if present
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            json_str = match.group(1) if match else content

            try:
                parsed_data = json.loads(json_str)
                return AiCustomizeResponse(
                    explanation=parsed_data.get("explanation", content[:200]),
                    config=parsed_data.get("config", {}),
                    raw_ai_response=content,
                )
            except Exception:
                return AiCustomizeResponse(
                    explanation=content[:300],
                    config=_local_fallback_customize(req.prompt)["config"],
                    raw_ai_response=content,
                )

    except Exception as err:
        logger.warning("NVIDIA AI API call failed or timed out: %s. Using fallback.", err)

    # Fallback to local rule engine
    fallback = _local_fallback_customize(req.prompt)
    return AiCustomizeResponse(
        explanation=fallback["explanation"],
        config=fallback["config"],
        raw_ai_response=None,
    )

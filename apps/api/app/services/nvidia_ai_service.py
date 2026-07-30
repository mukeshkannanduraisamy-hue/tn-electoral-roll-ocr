"""NVIDIA AI LLM Integration Service (z-ai/glm-5.2).

Provides natural language intelligence for application guidance, voter analytics,
export assistance, and UI customization.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
NVIDIA_API_KEY = os.getenv(
    "NVIDIA_API_KEY",
    "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",
)
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "z-ai/glm-5.2")

SYSTEM_PROMPT = """You are a highly intelligent and helpful AI Copilot embedded inside the Tamil Nadu Electoral Roll OCR & Voter Analytics application.

Your role is to:
- Answer user questions clearly, accurately, and concisely.
- Help users understand application features, OCR text extraction, family tree building, and PDF provenance.
- Guide users on generating reports, filters, column visibility chooser, and data exports (Excel, CSV, JSON).
- Provide smart insights, summary statistics, and practical troubleshooting.
- Automatically detect if the user wants to customize the UI (e.g. themes: Emerald, Purple, Amber, Ocean, Dark; filters: age, gender, house no, unverified; column visibility; or export downloads).

Guidelines:
- Be professional, friendly, and concise.
- If you don't know something specific, say so honestly without inventing data.
- Never alter core system files or invent non-existent database schema.

Output Format:
Always reply in JSON format with two top-level keys:
1. "reply": String containing your helpful, formatted natural language response for the user.
2. "ui_changes": Object containing optional UI customization commands:
   - "theme": "emerald" | "purple" | "amber" | "ocean" | "dark" | "light" | null
   - "filters": {"gender": str, "minAge": str, "maxAge": str, "verified": "true"|"false", "houseNumber": str, "relationType": str} | null
   - "columns": "all" | "basic" | "identity" | null
   - "export": "excel" | "csv" | "json" | null
   - "reset": true | false
"""


def query_nvidia_copilot(user_message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Query NVIDIA z-ai/glm-5.2 LLM endpoint and return AI reply + structured UI action commands."""
    if not user_message or not user_message.strip():
        return {
            "reply": "Please enter a message or command for the AI assistant.",
            "ui_changes": {},
        }

    full_user_content = user_message.strip()
    if context:
        ctx_str = json.dumps(context, default=str)
        full_user_content += f"\n\n[Current App Context: {ctx_str}]"

    url = f"{NVIDIA_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
    }

    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_user_content},
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 2048,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        choices = body.get("choices", [])
        if choices and "message" in choices[0]:
            content = choices[0]["message"].get("content", "")

            # Attempt to parse JSON output from model
            try:
                # Strip markdown code fencing if present
                clean_content = content.strip()
                if clean_content.startswith("```"):
                    clean_content = clean_content.split("```")[1]
                    if clean_content.startswith("json"):
                        clean_content = clean_content[4:]
                    clean_content = clean_content.strip()

                parsed = json.loads(clean_content)
                if isinstance(parsed, dict) and "reply" in parsed:
                    return {
                        "reply": str(parsed.get("reply", "")),
                        "ui_changes": parsed.get("ui_changes", {}),
                    }
            except Exception:
                pass

            # Fallback to plain text content if not JSON
            return {
                "reply": content.strip(),
                "ui_changes": {},
            }

    except Exception as e:
        logger.warning("NVIDIA AI API call failed: %s. Using local fallback engine.", e)

    # Local Fallback Rule Engine if network API is unreachable
    return _local_rule_fallback(user_message)


def _local_rule_fallback(user_message: str) -> Dict[str, Any]:
    """Deterministic fallback if NVIDIA API is unreachable."""
    msg = user_message.lower()
    ui_changes: Dict[str, Any] = {}
    reply_lines = []

    if "emerald" in msg or "green" in msg:
        ui_changes["theme"] = "emerald"
        reply_lines.append("Applied Emerald Green theme to your workspace.")
    elif "purple" in msg or "cyber" in msg:
        ui_changes["theme"] = "purple"
        reply_lines.append("Applied Cyberpunk Purple theme to your workspace.")
    elif "amber" in msg or "sunset" in msg:
        ui_changes["theme"] = "amber"
        reply_lines.append("Applied Sunset Amber theme to your workspace.")
    elif "dark" in msg:
        ui_changes["theme"] = "dark"
        reply_lines.append("Switched workspace to Dark Mode.")
    elif "light" in msg:
        ui_changes["theme"] = "light"
        reply_lines.append("Switched workspace to Light Mode.")

    filters: Dict[str, Any] = {}
    if "female" in msg or "women" in msg:
        filters["gender"] = "Female"
    elif "male" in msg or "men" in msg:
        filters["gender"] = "Male"

    if "18-25" in msg or "young" in msg:
        filters["minAge"] = "18"
        filters["maxAge"] = "25"
    elif "unverified" in msg:
        filters["verified"] = "false"

    if filters:
        ui_changes["filters"] = filters
        reply_lines.append(f"Applied voter filters: {filters}")

    if "23 columns" in msg or "all columns" in msg:
        ui_changes["columns"] = "all"
        reply_lines.append("Enabled visibility for all 23 database columns.")

    if "excel" in msg or "export" in msg:
        ui_changes["export"] = "excel"
        reply_lines.append("Triggered Excel report download.")

    if "reset" in msg or "default" in msg:
        ui_changes["reset"] = True
        reply_lines.append("Reset UI theme and active filters to system defaults.")

    if not reply_lines:
        reply_lines.append(f"I processed your query: '{user_message}'. You can ask me to change themes, filter voters, manage columns, or export reports.")

    return {
        "reply": "\n".join(reply_lines),
        "ui_changes": ui_changes,
    }

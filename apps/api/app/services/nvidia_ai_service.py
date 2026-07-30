"""NVIDIA AI LLM Integration Service (z-ai/glm-5.2).

Provides natural language intelligence for application guidance, voter analytics,
export assistance, and UI customization.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
#: Read from the environment only. A literal default here is a credential in the
#: repository: the previous one reached a public GitHub remote and had to be
#: rotated. With no key set the service degrades to the local rule engine below
#: rather than failing the request.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
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


#: Phrases that mean "show me figures" rather than "explain a feature".
_STATISTICAL_CUES = (
    "infographic", "info graph", "infograph", "visual summary", "visualise",
    "visualize", "chart", "graph", "statistic", "stats", "summary", "overview",
    "breakdown", "distribution", "how many", "count of", "average", "percentage",
    "percent", "share of", "compare", "total",
    # Tamil
    "எத்தனை", "சராசரி", "விளக்கப்படம்", "சுருக்கம்", "புள்ளிவிவரம்", "மொத்தம்",
)


def wants_infographic(user_message: str) -> bool:
    """Whether the question is asking for figures rather than guidance."""
    msg = (user_message or "").lower()
    return any(cue in msg for cue in _STATISTICAL_CUES)


_SPEC_PROMPT = """You translate a question about an electoral roll into a chart specification.

You MUST NOT answer the question and MUST NOT produce any numbers. The database
is queried separately; your only job is to say *what to measure*.

Reply with JSON only:
{{"metric": "<metric key>", "dimension": "<dimension key or null>",
  "filters": {{}}, "chart_type": null, "title": "<short human title>"}}

Choose strictly from this vocabulary — anything else is rejected:
{catalogue}

Rules:
- "metric" is required and must be one of the metric keys.
- "dimension" is the breakdown, or null for a single headline figure.
- "filters" uses only the listed filter keys. Omit it when the question is about
  the whole roll.
- Leave "chart_type" null unless the user explicitly names a form.
- "title" is a short label, six words or fewer, with no figures in it.
"""

_NARRATIVE_PROMPT = """You write the commentary beside a chart of electoral-roll data.

The figures below were computed from the database and are the only true values.

CRITICAL: do not write any numbers in your insights. The chart and its highlight
figures already show them; a number you type cannot be verified and will be
discarded. Refer to categories by name and describe direction, comparison and
what a reviewer should look at.

Reply with JSON only: {{"insights": ["...", "..."]}}
Two insights, one sentence each, plain professional language. Use the same
language as the user's question (English or Tamil).

Chart: {title}
Measure: {metric}
Computed data: {data}
User asked: {question}
"""

#: Any digit run in a generated insight must appear here, else the sentence goes.
_DIGITS = re.compile(r"\d+(?:\.\d+)?")


def _permitted_numbers(payload: Dict[str, Any]) -> set[str]:
    """Every numeric string the model is allowed to echo back."""
    allowed: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            # Labels such as "289", "18-25" or "60+" legitimately contain digits.
            for run in _DIGITS.findall(str(value)):
                allowed.add(run)
            return
        allowed.add(f"{number:g}")
        allowed.add(str(int(number)))
        # A rate may be quoted rounded either way.
        allowed.add(str(int(number) + 1))

    add(payload.get("total"))
    add(payload.get("population"))
    for point in payload.get("series") or []:
        add(point.get("value"))
        add(point.get("share"))
        add(point.get("label"))
    for highlight in payload.get("highlights") or []:
        add(highlight.get("value"))
        add(highlight.get("label"))
    for applied in payload.get("filters_applied") or []:
        add(applied.get("value"))
    return allowed


def strip_invented_numbers(
    insights: List[str], payload: Dict[str, Any]
) -> Tuple[List[str], int]:
    """Drop any insight quoting a figure the database did not produce.

    This is what makes "never invent numbers" a property of the system rather
    than a request in a prompt. The model is told not to write figures at all, so
    this should rarely fire — when it does, the sentence is discarded whole
    rather than served with a wrong number in it.
    """
    allowed = _permitted_numbers(payload)
    kept: List[str] = []
    dropped = 0
    for insight in insights:
        text = str(insight or "").strip()
        if not text:
            continue
        runs = _DIGITS.findall(text.replace(",", ""))
        invented = [r for r in runs if r not in allowed]
        if invented:
            dropped += 1
            logger.warning(
                "Discarded an AI insight quoting unverified figures %s: %r",
                invented, text,
            )
            continue
        kept.append(text)
    return kept, dropped


def _chat(messages: List[Dict[str, str]], *, temperature: float, max_tokens: int) -> Optional[str]:
    """One call to the hosted model. Returns raw content, or None on failure."""
    if not NVIDIA_API_KEY:
        return None
    payload = {
        "model": NVIDIA_MODEL,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    try:
        req = urllib.request.Request(
            f"{NVIDIA_BASE_URL}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {NVIDIA_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") or []
        if choices and "message" in choices[0]:
            return choices[0]["message"].get("content", "")
    except Exception as exc:
        logger.warning("NVIDIA AI call failed: %s", exc)
    return None


def _parse_json_object(content: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse a model reply that may be wrapped in a markdown fence."""
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def propose_infographic_spec(user_message: str, catalogue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ask the model which measure to chart. It never sees or writes values."""
    content = _chat(
        [
            {
                "role": "system",
                "content": _SPEC_PROMPT.format(catalogue=json.dumps(catalogue)),
            },
            {"role": "user", "content": (user_message or "").strip()},
        ],
        temperature=0.1,
        max_tokens=400,
    )
    return _parse_json_object(content)


def narrate_infographic(user_message: str, payload: Dict[str, Any]) -> List[str]:
    """Commentary for a chart whose values are already computed and fixed."""
    compact = {
        "series": payload.get("series"),
        "total": payload.get("total"),
        "population": payload.get("population"),
        "filters": payload.get("filters_applied"),
    }
    content = _chat(
        [
            {
                "role": "system",
                "content": _NARRATIVE_PROMPT.format(
                    title=payload.get("title", ""),
                    metric=(payload.get("metric") or {}).get("label", ""),
                    data=json.dumps(compact, default=str, ensure_ascii=False),
                    question=(user_message or "").strip(),
                ),
            },
            {"role": "user", "content": "Write the two insights."},
        ],
        temperature=0.3,
        max_tokens=400,
    )
    parsed = _parse_json_object(content) or {}
    raw = parsed.get("insights")
    if not isinstance(raw, list):
        return []
    kept, _ = strip_invented_numbers([str(i) for i in raw][:2], payload)
    return kept


def query_nvidia_copilot(user_message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Query NVIDIA z-ai/glm-5.2 LLM endpoint and return AI reply + structured UI action commands."""
    if not user_message or not user_message.strip():
        return {
            "reply": "Please enter a message or command for the AI assistant.",
            "ui_changes": {},
        }

    if not NVIDIA_API_KEY:
        logger.info("NVIDIA_API_KEY is not set; using the local rule engine.")
        return _local_rule_fallback(user_message)

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


def local_infographic_spec(user_message: str) -> Dict[str, Any]:
    """Keyword-matched spec, used when the hosted model is unavailable.

    Keeps the feature working offline and gives the LLM path something to fall
    back to. Deliberately conservative: an unrecognised question becomes the
    whole-roll headcount rather than a guess at what was meant.
    """
    msg = (user_message or "").lower()

    if "verif" in msg or "சரிபார" in msg:
        metric = "verified_rate" if ("rate" in msg or "percent" in msg or "%" in msg) else "verified_count"
    elif "average age" in msg or "mean age" in msg or "சராசரி" in msg:
        metric = "average_age"
    elif "supplement" in msg:
        metric = "supplement_count"
    else:
        metric = "voter_count"

    # Cue -> dimension. Order only breaks ties within a single scan, so an
    # explicit "by <x>" is matched first: "average age by part" names age as the
    # *measure* and part as the breakdown, and a plain scan would read the
    # earlier word "age" as the breakdown instead.
    dimension_cues = (
        ("gender", "gender"), ("male", "gender"), ("female", "gender"), ("பாலின", "gender"),
        ("age band", "age_band"), ("age group", "age_band"), ("age", "age_band"),
        ("வயது", "age_band"),
        ("part", "part_number"), ("பகுதி", "part_number"),
        ("constituency", "constituency"),
        ("relation", "relation_type"),
        ("roll type", "is_supplement"), ("supplement", "is_supplement"),
        ("verification", "verified"), ("verified", "verified"),
    )

    dimension = None
    grouped_by = re.search(r"\b(?:by|per|across|grouped by)\s+(.{0,24})", msg)
    if grouped_by:
        tail = grouped_by.group(1)
        for cue, key in dimension_cues:
            if cue in tail:
                dimension = key
                break
    if dimension is None:
        for cue, key in dimension_cues:
            if cue in msg:
                dimension = key
                break
    # "verified by ..." only makes sense as a breakdown of something else.
    if dimension is None and metric == "voter_count" and ("verif" in msg):
        dimension = "verified"

    filters: Dict[str, Any] = {}
    if "female" in msg or "women" in msg:
        filters["gender"] = "Female"
    elif "male" in msg or "men" in msg:
        filters["gender"] = "Male"
    if "unverified" in msg:
        filters["verified"] = False

    # "in part 289" names one part, so filter to it rather than charting all of
    # them. Naming a part and asking to break down *by* part is contradictory —
    # the filter wins, since it is the more specific request.
    named_part = re.search(r"part\s*(?:no\.?|number)?\s*([0-9]{1,4})", msg)
    if named_part:
        filters["part_number"] = named_part.group(1)
        if dimension == "part_number":
            dimension = None

    return {"metric": metric, "dimension": dimension, "filters": filters}


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

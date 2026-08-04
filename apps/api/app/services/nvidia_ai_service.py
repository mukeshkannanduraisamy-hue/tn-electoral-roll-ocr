"""Chat assistant for the electoral roll workspace.

Two responsibilities, deliberately separated:

* **Conversation.** Plain answers about the roll and how the application works.
* **Figures.** When a question is statistical, the model picks *what to measure*
  from a closed vocabulary and `infographic.py` runs the SQL. The model never
  writes a number, and :func:`strip_invented_numbers` discards any sentence that
  quotes a figure the database did not produce.

The assistant does not drive the interface. It answers; the operator decides.

Credentials are passed in rather than read from module-level environment
variables, because they can be set from the Settings page at runtime. See
`app_settings.resolve_ai_credentials`.
"""

from __future__ import annotations

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .app_settings import AiCredentials

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the assistant embedded in a Tamil Nadu electoral roll OCR and voter analytics workspace.

Answer questions about the roll and about using the application: OCR text
extraction, household and family resolution, PDF provenance, verification
workflow, filters, column visibility, and exports to Excel, CSV or JSON.

Guidelines:
- Be professional, concise and concrete.
- Reply in the language the user wrote in (English or Tamil).
- Never state a figure about the data. Counts, averages and percentages are
  computed separately and shown to the user as a chart; a number you type cannot
  be verified. Describe what a figure means, not what it is.
- If you do not know something, say so plainly rather than guessing.
- Reply with prose only. No JSON, no markdown code fences.
"""


#: Phrases that mean "show me figures" rather than "explain something".
_STATISTICAL_CUES = (
    "infographic", "info graph", "infograph", "visual summary", "visualise",
    "visualize", "chart", "graph", "statistic", "stats", "summary", "overview",
    "breakdown", "distribution", "how many", "count of", "average", "percentage",
    "percent", "share of", "compare", "total",
    # Tamil. The last three are postfix breakdown markers — Tamil puts the
    # "by/-wise" after the dimension ("பாலினம் வாரியாக"), so the "by <x>" pattern
    # below cannot catch them and they count as cues in their own right.
    "எத்தனை", "சராசரி", "விளக்கப்படம்", "சுருக்கம்", "புள்ளிவிவரம்", "மொத்தம்",
    "வாரியாக", "வாரியான", "அடிப்படையில்",
)


#: Words naming something the roll can be broken down by. "voters by gender" is
#: a request for figures even though it contains none of the cues above, and that
#: phrasing is the one people reach for first.
_BREAKDOWN_WORDS = (
    "gender", "age", "part", "constituency", "relation", "house", "roll type",
    "supplement", "verification", "verified", "male", "female",
    "பாலின", "வயது", "பகுதி",
)

_BREAKDOWN_PHRASE = re.compile(
    r"\b(?:by|per|across|grouped by|wise)\s+(?:the\s+)?(\w[\w\s-]{0,20})"
)


def wants_infographic(user_message: str) -> bool:
    """Whether the question is asking for figures rather than guidance."""
    msg = (user_message or "").lower()
    if any(cue in msg for cue in _STATISTICAL_CUES):
        return True
    match = _BREAKDOWN_PHRASE.search(msg)
    return bool(match) and any(word in match.group(1) for word in _BREAKDOWN_WORDS)


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


def _permitted_numbers(payload: Dict[str, Any]) -> set:
    """Every numeric string the model is allowed to echo back."""
    allowed: set = set()

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


@dataclass(frozen=True)
class ChatOutcome:
    """The result of one call, with enough detail to act on a failure.

    Collapsing every failure into "no response" was a mistake: a rejected key, a
    missing model, an exhausted quota and a firewall all need different fixes,
    and an operator staring at one generic sentence cannot tell which they have.
    """

    content: Optional[str] = None
    #: Operator-facing explanation. Set whenever `content` is None.
    error: Optional[str] = None
    status: Optional[int] = None

    @property
    def ok(self) -> bool:
        return bool(self.content)


def _explain_http_error(status: int, body: str, model: str) -> str:
    """Turn a status code into the action it implies."""
    detail = body.strip()[:300]
    if status in (401, 403):
        return (
            "The API key was rejected. It may be mistyped, revoked, or lack "
            f"access to {model!r}. Generate a fresh key at build.nvidia.com and "
            f"paste it again. (HTTP {status})"
        )
    if status == 404:
        return (
            f"The model {model!r} was not found at this endpoint. Check the model "
            f"name and base URL. (HTTP 404) {detail}"
        )
    if status == 429:
        return (
            "Rate limited or out of credits — the key is valid but the account "
            f"cannot serve this request right now. (HTTP 429) {detail}"
        )
    if status == 400:
        return f"The endpoint rejected the request as malformed. (HTTP 400) {detail}"
    if status >= 500:
        return f"The provider returned a server error; try again shortly. (HTTP {status})"
    return f"HTTP {status}. {detail}"


def _chat(
    messages: List[Dict[str, str]],
    creds: AiCredentials,
    *,
    temperature: float,
    max_tokens: int,
) -> ChatOutcome:
    """One call to the hosted model.

    Never logs or returns the key itself, but does surface the provider's own
    status and message so a misconfiguration is diagnosable.
    """
    if not creds.configured:
        return ChatOutcome(error="No API key is configured.")

    payload = {
        "model": creds.model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }

    try:
        req = urllib.request.Request(
            f"{creds.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {creds.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        message = _explain_http_error(exc.code, detail, creds.model)
        logger.warning("AI call failed: %s", message)
        return ChatOutcome(error=message, status=exc.code)
    except urllib.error.URLError as exc:
        message = (
            f"Could not reach {creds.base_url} ({exc.reason}). Check the base URL "
            "and whether this server has outbound internet access."
        )
        logger.warning("AI call failed: %s", message)
        return ChatOutcome(error=message)
    except (socket.timeout, TimeoutError):
        message = "The NVIDIA AI provider response timed out (30s). Please try your request again."
        logger.warning("AI call failed: %s", message)
        return ChatOutcome(error=message)
    except Exception as exc:
        message = f"Unexpected failure calling the model: {type(exc).__name__}."
        logger.warning("AI call failed: %s", message)
        return ChatOutcome(error=message)

    choices = body.get("choices") or []
    if not choices:
        return ChatOutcome(error="The provider returned no choices.", status=200)

    message_obj = choices[0].get("message") or {}
    content = (message_obj.get("content") or "").strip()
    if content:
        return ChatOutcome(content=content, status=200)

    reasoning = (message_obj.get("reasoning_content") or "").strip()
    finish = choices[0].get("finish_reason")
    if reasoning and finish == "length":
        return ChatOutcome(
            error=(
                f"{creds.model} used its entire {max_tokens}-token budget on "
                "internal reasoning and never produced an answer."
            ),
            status=200,
        )
    if reasoning:
        return ChatOutcome(
            error=f"{creds.model} returned reasoning but no answer.", status=200
        )
    return ChatOutcome(
        error=f"{creds.model} returned an empty response (finish_reason={finish}).",
        status=200,
    )


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


def check_credentials(creds: AiCredentials) -> Dict[str, Any]:
    """A minimal live call, so the Settings page can verify a pasted key.

    The budget is deliberately generous: a reasoning model spends tokens thinking
    before it answers, and a stingy limit would fail a perfectly good key.
    """
    if not creds.configured:
        return {"ok": False, "detail": "No API key is configured."}

    outcome = _chat(
        [{"role": "user", "content": "Reply with the single word: ready"}],
        creds,
        temperature=0.0,
        max_tokens=512,
    )
    if not outcome.ok:
        return {
            "ok": False,
            "detail": outcome.error or "The model did not respond.",
            "status": outcome.status,
        }
    return {"ok": True, "detail": f"{creds.model} responded.", "model": creds.model}


def propose_infographic_spec(
    user_message: str, catalogue: Dict[str, Any], creds: AiCredentials
) -> Optional[Dict[str, Any]]:
    """Ask the model which measure to chart. It never sees or writes values."""
    outcome = _chat(
        [
            {
                "role": "system",
                "content": _SPEC_PROMPT.format(catalogue=json.dumps(catalogue)),
            },
            {"role": "user", "content": (user_message or "").strip()},
        ],
        creds,
        # Room for a reasoning model to think before emitting the small JSON.
        temperature=0.1,
        max_tokens=1024,
    )
    return _parse_json_object(outcome.content)


def narrate_infographic(
    user_message: str, payload: Dict[str, Any], creds: AiCredentials
) -> List[str]:
    """Commentary for a chart whose values are already computed and fixed."""
    compact = {
        "series": payload.get("series"),
        "total": payload.get("total"),
        "population": payload.get("population"),
        "filters": payload.get("filters_applied"),
    }
    outcome = _chat(
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
        creds,
        temperature=0.3,
        max_tokens=1024,
    )
    parsed = _parse_json_object(outcome.content) or {}
    raw = parsed.get("insights")
    if not isinstance(raw, list):
        return []
    kept, _ = strip_invented_numbers([str(i) for i in raw][:2], payload)
    return kept


def _sanitize_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Keep context lightweight and compact to prevent prompt inflation and LLM timeouts."""
    clean = {}
    for k, v in ctx.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            clean[k] = v
        elif isinstance(v, list):
            clean[k] = f"List of {len(v)} item(s)"
        elif isinstance(v, dict):
            clean[k] = {dk: dv for dk, dv in list(v.items())[:5] if isinstance(dv, (str, int, float, bool))}
    return clean


def query_nvidia_copilot(
    user_message: str,
    creds: Optional[AiCredentials] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Answer a question in prose. Figures are attached separately as a chart."""
    if not user_message or not user_message.strip():
        return {"reply": "Ask me anything about the roll, or about using the app."}

    creds = creds or AiCredentials(api_key="", base_url="", model="")
    if not creds.configured:
        logger.info("No AI key configured; answering from the offline guide.")
        return _local_rule_fallback(user_message)

    content = (user_message or "").strip()
    if context:
        clean_ctx = _sanitize_context(context)
        content += f"\n\n[App View Context: {json.dumps(clean_ctx, default=str)}]"

    outcome = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        creds,
        temperature=0.6,
        max_tokens=512,
    )
    if not outcome.ok:
        fallback = _local_rule_fallback(user_message)
        if fallback.get("reply", "").startswith("The AI assistant is not configured"):
            fallback["reply"] = f"NVIDIA AI Status: {outcome.error}\n\nI can still answer offline topics or generate database charts."
        else:
            fallback["reply"] = f"{fallback['reply']}\n\n({outcome.error})"
        return fallback
    return {"reply": outcome.content.strip()}


def local_infographic_spec(user_message: str) -> Dict[str, Any]:
    """Keyword-matched spec, used when the hosted model is unavailable.

    Keeps figures working offline and gives the LLM path something to fall back
    to. Deliberately conservative: an unrecognised question becomes the
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


#: What the assistant can help with when no model is reachable. Kept short and
#: honest rather than pretending to have answered.
_OFFLINE_TOPICS = (
    ("export", "Use the Excel, CSV or JSON buttons above the voters table — the file matches the filters currently applied."),
    ("filter", "Filter voters from the toolbar above the table: age band, gender, part, house number and verification state."),
    ("column", "The DB Columns chooser above the table controls which of the 23 database columns are shown."),
    ("famil", "Open a voter and use the Family tab to see the resolved household graph, with the evidence behind each link."),
    ("household", "Open a voter and use the Family tab to see the resolved household graph, with the evidence behind each link."),
    ("ocr", "A voter's OCR Details tab shows each extracted field, its confidence, and the box it came from on the source page."),
    ("verif", "Mark a record verified from its profile once you have checked it against the Source Document tab."),
    ("photo", "The Photos tab shows the elector's crop and the polling station imagery extracted from the roll."),
)


def _local_rule_fallback(user_message: str) -> Dict[str, Any]:
    """Answer from a short offline guide when no model is configured.

    Says plainly that the assistant is offline, so an operator does not mistake
    a canned answer for a considered one.
    """
    msg = (user_message or "").lower()
    for cue, answer in _OFFLINE_TOPICS:
        if cue in msg:
            return {"reply": answer}

    if wants_infographic(msg):
        # A chart is still attached by the caller, so point at it rather than
        # apologising.
        return {"reply": "Here is what the database returned."}

    return {
        "reply": (
            "The AI assistant is not configured, so I can only answer from a short "
            "built-in guide. Add an API key under Settings to enable full answers. "
            "I can still chart figures from the database — try “voters by gender” "
            "or “average age by part”."
        )
    }


# ---------------------------------------------------------------------------
# Transports for the agent
#
# Two additions, both additive: a streaming call so a long answer appears as it
# is written rather than after twenty seconds of silence, and a tool-calling
# call so the model can ask for data instead of guessing at it.
#
# Everything above this line keeps its existing behaviour; the legacy
# `/api/voters/ai-copilot` path does not go through here.
# ---------------------------------------------------------------------------

#: Whether a given model accepted a `tools` array. Learned on first refusal
#: rather than hard-coded, because the provider's catalogue changes and an
#: operator can type any model name into the Settings page.
_TOOL_SUPPORT: Dict[str, bool] = {}


def supports_native_tools(model: str) -> Optional[bool]:
    """True, False, or None when it has not been tried yet."""
    return _TOOL_SUPPORT.get(model)


def remember_tool_support(model: str, supported: bool) -> None:
    _TOOL_SUPPORT[model] = supported


def _request(payload: Dict[str, Any], creds: AiCredentials, *, stream: bool):
    return urllib.request.Request(
        f"{creds.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": f"Bearer {creds.api_key}",
        },
        method="POST",
    )


def stream_chat(
    messages: List[Dict[str, Any]],
    creds: AiCredentials,
    *,
    temperature: float,
    max_tokens: int,
):
    """Yield content deltas as the model writes them.

    A generator rather than a return value: the caller forwards each fragment to
    the browser, so the operator watches the answer form instead of watching a
    spinner. Errors are yielded as text — an exception mid-stream would leave a
    half-written bubble with no explanation in it.
    """
    payload = {
        "model": creds.model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        with urllib.request.urlopen(_request(payload, creds, stream=True), timeout=60) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    frame = json.loads(data)
                except ValueError:
                    continue
                for choice in frame.get("choices") or []:
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield delta
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        yield f"\n\n[{_explain_http_error(exc.code, detail, creds.model)}]"
    except (socket.timeout, TimeoutError):
        yield "\n\n[The provider stopped responding while writing the answer.]"
    except Exception as exc:
        logger.warning("Streaming call failed: %s", type(exc).__name__)
        yield f"\n\n[The answer could not be completed: {type(exc).__name__}.]"


@dataclass(frozen=True)
class ToolCallOutcome:
    """One turn of a tool-calling conversation."""

    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    status: Optional[int] = None
    #: True when the provider rejected the request because of the tools array,
    #: which is how a model without function calling announces itself.
    unsupported: bool = False


def chat_with_tools(
    messages: List[Dict[str, Any]],
    creds: AiCredentials,
    tools: List[Dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
) -> ToolCallOutcome:
    """One call that may come back asking for data instead of answering."""
    if not creds.configured:
        return ToolCallOutcome(error="No API key is configured.")

    payload: Dict[str, Any] = {
        "model": creds.model,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        with urllib.request.urlopen(_request(payload, creds, stream=False), timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        # A 400 mentioning tools or functions means this model cannot do it.
        # Only meaningful when a `tools` array was actually sent — otherwise an
        # unrelated 400 (bad max_tokens, malformed message, ...) that happens to
        # contain the word "function" in its prose gets misread as a refusal.
        unsupported = bool(tools) and exc.code == 400 and bool(
            re.search(r"tool|function", detail, re.IGNORECASE)
        )
        if unsupported:
            logger.info("%s does not support native tool calling", creds.model)
        return ToolCallOutcome(
            error=_explain_http_error(exc.code, detail, creds.model),
            status=exc.code,
            unsupported=unsupported,
        )
    except (socket.timeout, TimeoutError):
        return ToolCallOutcome(error="The provider timed out.")
    except Exception as exc:
        logger.warning("Tool call failed: %s", type(exc).__name__)
        return ToolCallOutcome(error=f"Unexpected failure: {type(exc).__name__}.")

    choices = body.get("choices") or []
    if not choices:
        return ToolCallOutcome(error="The provider returned no choices.", status=200)

    message = choices[0].get("message") or {}
    calls: List[Dict[str, Any]] = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw_args = function.get("arguments")
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except ValueError:
            logger.info("Model emitted unparseable tool arguments: %r", raw_args)
            parsed = {}
        calls.append(
            {
                "id": call.get("id") or f"call_{len(calls)}",
                "name": function.get("name") or "",
                "arguments": parsed if isinstance(parsed, dict) else {},
            }
        )

    return ToolCallOutcome(
        content=(message.get("content") or "").strip() or None,
        tool_calls=calls,
        status=200,
    )

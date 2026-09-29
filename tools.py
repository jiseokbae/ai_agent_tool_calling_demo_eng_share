# tools.py

import hashlib
import json
from typing import Any

from datetime_normalizer import normalize_calendar_datetime
from calendar_client import check_google_calendar
from place_client import search_place_google

import config

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_calendar_availability",
            "description": (
                "Use this when the caller asks about the user's availability, proposes a meeting time, or asks whether a certain date and time works. "
                "Put the caller's date/time expression in datetime_text. "
                "If date and time information appears in different parts of the caller's utterance, combine them in datetime_text. "
                "Do not guess or invent missing date/time information. "
                "Normalization and missing-information checks are handled inside the tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "datetime_text": {
                        "type": "string",
                        "description": (
                            "The caller's original date/time expression. "
                            "Examples: tomorrow at 3 PM, next Tuesday at 10 AM, this week, 5 PM, in one hour"
                        ),
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Expected meeting duration in minutes. Omit it if the caller did not mention a duration.",
                    },
                },
                "required": ["datetime_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_place",
            "description": (
                "Use this when the caller mentions a meeting place, location, building, station, cafe, restaurant, or other place."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place": {
                        "type": "string",
                        "description": "The place mentioned by the caller. Examples: The Grove, Starbucks in Santa Monica, LAX",
                    }
                },
                "required": ["place"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_user",
            "description": (
                "Use this when information from the call should be delivered to the user. "
                "Use it for scheduling requests, callback requests, place information, urgent messages, or call summaries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The call summary, request, or message to deliver to the user",
                    }
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": (
                "Use this when the call should be ended. "
                "Use it not only for spam or promotional calls, but also when the caller's purpose has been sufficiently identified and "
                "the information that should be delivered to the user has been collected. "
                "This tool does not hang up immediately. Say closing_message to the caller first, then end the call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason_type": {
                        "type": "string",
                        "enum": [
                            "completed",
                            "spam",
                            "callback_request",
                            "wrong_number",
                            "no_response",
                            "other",
                        ],
                        "description": "Reason category for ending the call",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Specific reason for ending the call",
                    },
                    "closing_message": {
                        "type": "string",
                        "description": "Final message to say to the caller before ending the call",
                    },
                },
                "required": ["reason_type", "reason", "closing_message"],
                "additionalProperties": False,
            },
        },
    }
]


def execute_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "check_calendar_availability":
        return _check_calendar_availability(args)

    if tool_name == "resolve_place":
        return _resolve_place(args)

    if tool_name == "notify_user":
        return _notify_user(args)

    if tool_name == "end_call":
        return _end_call(args)

    raise ValueError(f"Unknown tool: {tool_name}")


def dumps_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)



def _check_calendar_availability(args: dict[str, Any]) -> dict[str, Any]:
    datetime_text = _require_str(args, "datetime_text")

    duration_minutes = args.get("duration_minutes") or 60
    try:
        duration_minutes = int(duration_minutes)
    except Exception:
        duration_minutes = 60

    if duration_minutes <= 0:
        duration_minutes = 60

    normalized = normalize_calendar_datetime(
        datetime_text=datetime_text,
        default_duration_minutes=duration_minutes,
        require_explicit_date=True,
    )

    base = {
        "ok": True,
        "tool": "check_calendar_availability",
        "result_id": _result_id("calendar", args),
        "requested_time_text": datetime_text,
        "duration_minutes": duration_minutes,
        "normalized_time": normalized,
    }

    # 1. 날짜/시간 부족
    if normalized["status"] == "needs_more_info":
        return {
            **base,
            "status": "needs_more_info",
            "available": None,
            "busy_blocks": [],
            "suggested_slots": [],
            "missing_fields": normalized.get("missing_fields", []),
            "message_for_assistant": normalized.get(
                "ask_user_message",
                "There is not enough date or time information to check the calendar. Ask the caller to provide a more specific date and time.",
            ),
        }

    # 2. 날짜/시간 정규화 성공 → 실제 캘린더 조회
    calendar_result = check_google_calendar(
        start_datetime=normalized["start_datetime"],
        end_datetime=normalized["end_datetime"],
    )

    # 3. 캘린더 API 실패
    if not calendar_result.get("ok", False):
        return {
            **base,
            "ok": False,
            "status": calendar_result.get("status", "error"),
            "available": None,
            "busy_blocks": [],
            "suggested_slots": [],
            "error_code": calendar_result.get("error_code"),
            "error_type": calendar_result.get("error_type"),
            "error": calendar_result.get("error"),
            "raw_calendar_result": calendar_result,
            "message_for_assistant": (
                "An error occurred while checking the calendar. "
                "Tell the caller that the information will be noted and passed along."
            ),
        }

    # 4. 일정 가능
    if calendar_result.get("available") is True:
        return {
            **base,
            "status": "available",
            "available": True,
            "busy_blocks": [],
            "suggested_slots": [],
            "calendar_query": {
                "start_datetime": normalized["start_datetime"],
                "end_datetime": normalized["end_datetime"],
            },
            "raw_calendar_result": calendar_result,
            "message_for_assistant": (
                "There are no calendar conflicts during the requested time. "
                "Do not confirm the appointment without the user's approval; only say that the time may be available."
            ),
        }

    # 5. 일정 있음
    return {
        **base,
        "status": "busy",
        "available": False,
        "busy_blocks": calendar_result.get("busy_blocks", []),
        "suggested_slots": [],
        "calendar_query": {
            "start_datetime": normalized["start_datetime"],
            "end_datetime": normalized["end_datetime"],
        },
        "raw_calendar_result": calendar_result,
        "message_for_assistant": (
            "There is a calendar conflict during the requested time. "
            "Do not reveal event titles or private calendar details. Tell the caller that the requested time may not work. "
            "If needed, ask the caller to suggest another time."
        ),
    }

def _resolve_place(args: dict[str, Any]) -> dict[str, Any]:
    place = _require_str(args, "place")

    place_result = search_place_google(place)
    status = place_result.get("status")

    if status == "exact_match":
        message_for_assistant = (
            "The place was resolved to a single result. "
            "Do not treat the meeting location as confirmed. Tell the caller that the place information will be passed along to the user."
        )
    elif status == "multiple_candidates":
        message_for_assistant = (
            "Multiple place candidates were found. "
            "Briefly ask the caller which location they mean. "
            "When helpful, mention two or three options from top_candidates as examples. "
            "Do not ask about the date or time unless the caller asked to check or discuss scheduling. "
            "Clarify the place first before saying that the information will be passed along."
        )
    elif status == "not_found":
        message_for_assistant = (
            "The place could not be found. "
            "Ask the caller for an address or a more specific place name."
        )
    elif status == "config_missing":
        message_for_assistant = (
            "The place search API is not configured. "
            "Tell the caller that the place name will be noted."
        )
    else:
        message_for_assistant = (
            "An error occurred while searching for the place. "
            "Tell the caller that the place name will be noted."
        )

    return {
        "ok": place_result.get("ok", False),
        "tool": "resolve_place",
        "result_id": _result_id("place", args),
        "query": place,
        "status": status,
        "resolved": place_result.get("resolved"),
        "candidates": place_result.get("candidates", []),
        "top_candidates": place_result.get("top_candidates", []),
        "selected_candidate": place_result.get("selected_candidate"),
        "raw_place_result": place_result,
        "message_for_assistant": message_for_assistant,
    }

def _notify_user(args: dict[str, Any]) -> dict[str, Any]:
    message = _require_str(args, "message")

    # include_failures = os.getenv("MOCK_INCLUDE_FAILURES", "false").lower() == "true"
    include_failures = getattr(config, "MOCK_INCLUDE_FAILURES", False)
    candidates = ["sent", "queued"]
    if include_failures:
        candidates.append("failed")

    scenario = _pick_scenario("notify_user", args, candidates)

    print("\n[MOCK_NOTIFY_USER]")
    print(message)

    base = {
        "ok": True,
        "tool": "notify_user",
        "result_id": _result_id("notify", args),
        "message": message,
    }

    if scenario == "sent":
        return {
            **base,
            "status": "sent",
            "delivered": True,
            "message_for_assistant": "The notification was delivered to the user. You may tell the caller that the message has been passed along.",
        }

    if scenario == "queued":
        return {
            **base,
            "status": "queued",
            "delivered": False,
            "message_for_assistant": "The notification is queued for delivery. You may tell the caller that the message will be passed along.",
        }

    return {
        **base,
        "ok": False,
        "status": "failed",
        "delivered": False,
        "error_code": "MOCK_PUSH_FAILED",
        "message_for_assistant": "The notification could not be delivered. Tell the caller that the message has been noted.",
    }


def _end_call(args: dict[str, Any]) -> dict[str, Any]:
    reason_type = _optional_str(args, "reason_type", default="other")
    reason = _optional_str(args, "reason", default="The conditions for ending the call have been met")
    closing_message = _optional_str(
        args,
        "closing_message",
        default="Thank you. I'll pass along what you've told me.",
    )

    allowed_reason_types = {
        "completed",
        "spam",
        "callback_request",
        "wrong_number",
        "no_response",
        "other",
    }

    if reason_type not in allowed_reason_types:
        reason_type = "other"

    print("\n[MOCK_END_CALL]")
    print(f"reason_type={reason_type}")
    print(f"reason={reason}")
    # print(f"closing_message={closing_message}")

    return {
        "ok": True,
        "tool": "end_call",
        "result_id": _result_id("end_call", args),

        # 실제 hangup이 아니라, 마지막 멘트 후 종료하라는 신호
        "should_end_call": True,

        "reason_type": reason_type,
        "reason": reason,
        "closing_message": closing_message,
        "message_for_assistant": (
            "Say closing_message to the caller, then end the call."
        ),
    }


def _optional_str(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key)

    if isinstance(value, str) and value.strip():
        return value.strip()

    return default

def _pick_scenario(tool_name: str, args: dict[str, Any], candidates: list[str]) -> str:
    seed = _stable_json({"tool_name": tool_name, "args": args})
    idx = _stable_int(seed) % len(candidates)
    return candidates[idx]


def _stable_int(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _result_id(prefix: str, args: dict[str, Any]) -> str:
    digest = hashlib.sha256(_stable_json(args).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool argument '{key}' must be a non-empty string")

    return value.strip()
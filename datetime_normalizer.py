# datetime_normalizer.py

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from english_date_converter import DateConverter
from english_time_converter import absolute_time, delta_time

import config


TIMEZONE_NAME = getattr(config, "LOCAL_TIMEZONE", "America/Los_Angeles")
LOCAL_TZ = ZoneInfo(TIMEZONE_NAME)


def get_reference_now() -> datetime:
    """
    Return the current reference time in the configured local timezone.

    For reproducible tests, config.REFERENCE_NOW may be set to an ISO timestamp.
    Example: REFERENCE_NOW = "2026-08-14T10:00:00-07:00"
    """
    raw = getattr(config, "REFERENCE_NOW", None)

    if raw:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
        return dt.astimezone(LOCAL_TZ)

    return datetime.now(LOCAL_TZ)


def normalize_calendar_datetime(
    datetime_text: str,
    default_duration_minutes: int = 60,
    require_explicit_date: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Convert US-English natural-language date/time expressions into an ISO time range.

    Policy:
    - specific date + specific time -> resolved_exact
    - relative time such as "in 30 minutes" -> resolved_exact
    - date only -> needs_more_info(time)
    - time only -> needs_more_info(date), unless require_explicit_date=False
    - broad expressions such as "next week" -> needs_more_info(specific_date)
    - ambiguous values are not silently guessed
    """
    original = (datetime_text or "").strip()

    if not original:
        return _needs_more_info(
            original_text=original,
            missing_fields=["date", "time"],
            reason="Both the date and time are missing.",
        )

    now_local = _ensure_local(now or get_reference_now())
    now_naive = _to_naive(now_local)
    normalized_text = _normalize_text(original)

    # 1. Relative clock time first: "in 30 minutes", "2 hours from now".
    delta_dt, delta_match = delta_time(now_naive, normalized_text)
    if delta_match is not None:
        start_dt = _attach_local(delta_dt)
        end_dt = start_dt + timedelta(minutes=default_duration_minutes)
        return {
            "ok": True,
            "status": "resolved_exact",
            "resolution_type": "relative_time",
            "original_text": original,
            "matched_text": delta_match.group(0),
            "timezone": TIMEZONE_NAME,
            "reference_now": now_local.isoformat(),
            "start_datetime": start_dt.isoformat(),
            "end_datetime": end_dt.isoformat(),
            "duration_minutes": default_duration_minutes,
            "missing_fields": [],
            "normalizer_message": "The relative time expression was normalized successfully.",
        }

    # 2. Immediate/current-time expressions.
    if re.search(r"\b(?:now|right now|immediately|asap|as soon as possible)\b", normalized_text):
        start_dt = now_local.replace(microsecond=0)
        end_dt = start_dt + timedelta(minutes=default_duration_minutes)
        return {
            "ok": True,
            "status": "resolved_exact",
            "resolution_type": "now",
            "original_text": original,
            "matched_text": "now/immediately",
            "timezone": TIMEZONE_NAME,
            "reference_now": now_local.isoformat(),
            "start_datetime": start_dt.isoformat(),
            "end_datetime": end_dt.isoformat(),
            "duration_minutes": default_duration_minutes,
            "missing_fields": [],
            "normalizer_message": "The expression was normalized to the current time.",
        }

    # 3. Date.
    date_is_broad = _is_broad_date_expression(normalized_text)
    date_dt = None
    if not date_is_broad:
        date_dt = DateConverter().do_convert(now_naive, normalized_text)

    # 4. Clock time.
    if date_dt is not None:
        time_base = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        time_base = now_naive

    time_dt, time_match = absolute_time(time_base, normalized_text)

    has_date = date_dt is not None
    has_time = time_match is not None

    # 5. Missing-information cases.
    if not has_date and not has_time:
        missing_fields = ["specific_date" if date_is_broad else "date", "time"]
        return _needs_more_info(
            original_text=original,
            missing_fields=missing_fields,
            reason="The date and time are not specific enough.",
            reference_now=now_local,
        )

    if has_date and not has_time:
        return _needs_more_info(
            original_text=original,
            missing_fields=["time"],
            reason="The date is clear, but the time is missing or ambiguous.",
            reference_now=now_local,
            parsed_date=_attach_local(date_dt).date().isoformat(),
        )

    if not has_date and has_time:
        missing_field = "specific_date" if date_is_broad else "date"
        candidate_time = _attach_local(time_dt)

        if require_explicit_date:
            return _needs_more_info(
                original_text=original,
                missing_fields=[missing_field],
                reason="The time is clear, but a specific date is missing.",
                reference_now=now_local,
                candidate_time=candidate_time.isoformat(),
                matched_time_text=time_match.group(0),
            )

        start_dt = candidate_time
        end_dt = start_dt + timedelta(minutes=default_duration_minutes)
        return {
            "ok": True,
            "status": "resolved_exact",
            "resolution_type": "time_only_closest_future",
            "original_text": original,
            "matched_time_text": time_match.group(0),
            "timezone": TIMEZONE_NAME,
            "reference_now": now_local.isoformat(),
            "start_datetime": start_dt.isoformat(),
            "end_datetime": end_dt.isoformat(),
            "duration_minutes": default_duration_minutes,
            "missing_fields": [],
            "normalizer_message": "The time was normalized to the closest future occurrence.",
        }

    # 6. Specific date + specific time.
    start_dt = _attach_local(time_dt)
    end_dt = start_dt + timedelta(minutes=default_duration_minutes)
    return {
        "ok": True,
        "status": "resolved_exact",
        "resolution_type": "date_and_time",
        "original_text": original,
        "matched_time_text": time_match.group(0),
        "timezone": TIMEZONE_NAME,
        "reference_now": now_local.isoformat(),
        "start_datetime": start_dt.isoformat(),
        "end_datetime": end_dt.isoformat(),
        "duration_minutes": default_duration_minutes,
        "missing_fields": [],
        "normalizer_message": "The date and time were normalized successfully.",
    }


def _needs_more_info(
    original_text: str,
    missing_fields: list[str],
    reason: str,
    reference_now: datetime | None = None,
    **extra,
) -> dict[str, Any]:
    result = {
        "ok": True,
        "status": "needs_more_info",
        "original_text": original_text,
        "missing_fields": missing_fields,
        "reason": reason,
        "ask_user_message": _build_missing_info_message(missing_fields),
    }

    if reference_now is not None:
        result["reference_now"] = reference_now.isoformat()

    result.update(extra)
    return result


def _build_missing_info_message(missing_fields: list[str]) -> str:
    missing = set(missing_fields)

    if "specific_date" in missing and "time" in missing:
        return "Ask the caller for a specific date and time."
    if "date" in missing and "time" in missing:
        return "Ask the caller for the date and time."
    if "specific_date" in missing:
        return "Ask the caller for a specific date."
    if "date" in missing:
        return "Ask the caller for the date."
    if "time" in missing:
        return "Ask the caller for a specific time, including AM or PM if needed."
    return "Ask the caller for the missing scheduling information."


def _is_broad_date_expression(text: str) -> bool:
    """Return True when the date phrase is too broad for a calendar lookup."""
    text = _normalize_text(text)

    weekday = (
        r"(?:monday|mon|tuesday|tue|tues|wednesday|wed|thursday|thu|thur|thurs|"
        r"friday|fri|saturday|sat|sunday|sun)"
    )

    # These are specific despite containing "this/next week".
    if re.search(rf"\b(?:this|next)\s+week(?:\s+on)?\s+{weekday}\b", text):
        return False

    if re.search(r"\b(?:this|next|last)\s+week\b", text):
        return True
    if re.search(r"\b(?:later|sometime)\s+(?:this|next)\s+week\b", text):
        return True
    if re.search(r"\b(?:this|next|last)\s+weekend\b", text):
        return True
    if re.search(r"\b(?:this|next|last)\s+month\b", text):
        return True
    if re.search(r"\b(?:early|mid|late)\s+(?:this|next)\s+(?:week|month)\b", text):
        return True

    return False


def _ensure_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def _attach_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)


def _to_naive(dt: datetime) -> datetime:
    return _ensure_local(dt).replace(tzinfo=None)


def _normalize_text(text: str) -> str:
    text = (text or "").strip().lower().replace("’", "'")
    return re.sub(r"\s+", " ", text)
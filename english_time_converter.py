# english_time_converter.py

import re
from datetime import datetime, timedelta


_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
}
_NUM = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"


def _to_int(token: str) -> int:
    token = token.lower()
    return int(token) if token.isdigit() else _NUMBER_WORDS[token]


def delta_time(date: datetime, time_text: str):
    """Resolve relative times such as 'in 30 minutes' or '2 hours from now'."""
    text = _normalize(time_text)

    m = re.search(r"\b(?:in\s+)?(?:an|one|1)\s+hour\s+and\s+(?:a\s+)?half(?:\s+from\s+now)?\b", text)
    if m:
        return date + timedelta(hours=1, minutes=30), m

    m = re.search(r"\b(?:in\s+)?half\s+an?\s+hour(?:\s+from\s+now)?\b", text)
    if m:
        return date + timedelta(minutes=30), m

    m = re.search(
        rf"\b(?:in\s+)?({_NUM})\s+hours?\s+(?:and\s+)?({_NUM})\s+minutes?"
        r"(?:\s+from\s+now|\s+later|\s+after\s+now)?\b",
        text,
    )
    if m:
        return date + timedelta(hours=_to_int(m.group(1)), minutes=_to_int(m.group(2))), m

    m = re.search(rf"\b({_NUM})\s+(seconds?|minutes?|hours?)\s+ago\b", text)
    if m:
        return date - _unit_delta(_to_int(m.group(1)), m.group(2)), m

    m = re.search(
        rf"\b(?:in\s+)?({_NUM})\s+(seconds?|minutes?|hours?)"
        r"(?:\s+from\s+now|\s+later|\s+after\s+now)\b",
        text,
    )
    if m:
        return date + _unit_delta(_to_int(m.group(1)), m.group(2)), m

    m = re.search(rf"\bin\s+({_NUM})\s+(seconds?|minutes?|hours?)\b", text)
    if m:
        return date + _unit_delta(_to_int(m.group(1)), m.group(2)), m

    return date, None


def absolute_time(date: datetime, time_text: str):
    """
    Resolve explicit clock times.

    Bare-hour policy:
      7-11 -> AM, 12 -> noon, 13-23 -> 24-hour time.
      1-6 without AM/PM stays unresolved so the caller can be asked to clarify.
    """
    text = _normalize(time_text)

    m = re.search(r"\bnoon\b", text)
    if m:
        return _closest_future_time(date, 12, 0, 0), m

    m = re.search(r"\bmidnight\b", text)
    if m:
        return _closest_future_time(date, 0, 0, 0), m

    m = re.search(
        r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s+in\s+the\s+(morning|afternoon|evening)\b",
        text,
    )
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = m.group(3)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return date, None
        if period == "morning":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return _closest_future_time(date, hour, minute, 0), m

    m = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        marker = m.group(3).replace(".", "")
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return date, None
        if marker == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return _closest_future_time(date, hour, minute, 0), m

    m = re.search(r"\b(?:at\s+)?(\d{1,2}):(\d{2})\b", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return date, None
        if 1 <= hour <= 6:
            return date, None
        return _closest_future_time(date, hour, minute, 0), m

    # Requiring "at" avoids mistaking date numbers for times.
    m = re.search(r"\bat\s+(\d{1,2})\b", text)
    if m:
        hour = int(m.group(1))
        if 7 <= hour <= 11:
            return _closest_future_time(date, hour, 0, 0), m
        if hour == 12:
            return _closest_future_time(date, 12, 0, 0), m
        if 13 <= hour <= 23:
            return _closest_future_time(date, hour, 0, 0), m
        return date, None

    return date, None


def convert_time(date: datetime, time_text: str):
    date_res, match = delta_time(date, time_text)
    if match is not None:
        return date_res, match
    return absolute_time(date, time_text)


def _unit_delta(value: int, unit: str) -> timedelta:
    unit = unit.lower()
    if unit.startswith("hour"):
        return timedelta(hours=value)
    if unit.startswith("minute"):
        return timedelta(minutes=value)
    return timedelta(seconds=value)


def _closest_future_time(current_time: datetime, target_hour: int, target_minute: int, target_second: int = 0) -> datetime:
    target = current_time.replace(
        hour=target_hour,
        minute=target_minute,
        second=target_second,
        microsecond=0,
    )
    if target < current_time:
        target += timedelta(days=1)
    return target


def _normalize(text: str) -> str:
    text = (text or "").strip().lower().replace("’", "'")
    return re.sub(r"\s+", " ", text)
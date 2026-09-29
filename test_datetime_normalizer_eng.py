from datetime import datetime
from zoneinfo import ZoneInfo

from datetime_normalizer import normalize_calendar_datetime


REFERENCE_NOW = datetime(
    2026, 8, 14, 10, 0, 0,
    tzinfo=ZoneInfo("America/Los_Angeles"),
)

CASES = [
    "tomorrow at 3 PM",
    "next Tuesday at 10",
    "August 20th at 4:30 PM",
    "in 30 minutes",
    "next week at 3 PM",
    "tomorrow afternoon",
    "tomorrow at 4",
    "8/20/2026 at 15:00",
]


for text in CASES:
    result = normalize_calendar_datetime(text, now=REFERENCE_NOW)

    print("=" * 80)
    print("INPUT:", text)
    print("status:", result.get("status"))
    print("missing_fields:", result.get("missing_fields"))
    print("start_datetime:", result.get("start_datetime"))
    print("end_datetime:", result.get("end_datetime"))
    print("ask_user_message:", result.get("ask_user_message"))
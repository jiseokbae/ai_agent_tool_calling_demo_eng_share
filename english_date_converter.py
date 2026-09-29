# english_date_converter.py

import re
from calendar import monthrange
from datetime import datetime, timedelta


class DateConverter:
    """Convert common US-English date expressions into a specific datetime date."""

    MONTHS = {
        "january": 1, "jan": 1,
        "february": 2, "feb": 2,
        "march": 3, "mar": 3,
        "april": 4, "apr": 4,
        "may": 5,
        "june": 6, "jun": 6,
        "july": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }

    WEEKDAYS = {
        "monday": 0, "mon": 0,
        "tuesday": 1, "tue": 1, "tues": 1,
        "wednesday": 2, "wed": 2,
        "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
        "friday": 4, "fri": 4,
        "saturday": 5, "sat": 5,
        "sunday": 6, "sun": 6,
    }

    NUMBER_WORDS = {
        "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12,
    }

    def do_convert(self, today: datetime, date_text: str) -> datetime | None:
        text = self._normalize(date_text)
        if not text:
            return None

        if re.search(r"\b(?:none|n/?a|tbd|unknown|not sure|undecided)\b", text):
            return None

        # Relative named dates.
        if re.search(r"\bday after tomorrow\b", text):
            return today + timedelta(days=2)
        if re.search(r"\btomorrow\b", text):
            return today + timedelta(days=1)
        if re.search(r"\b(?:today|tonight)\b", text):
            return today
        if re.search(r"\byesterday\b", text):
            return today - timedelta(days=1)

        # "in 2 days", "3 days from now", "in two weeks".
        m = re.search(
            r"\b(?:in\s+)?(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
            r"\s+(day|days|week|weeks)\s*(?:from now)?\b",
            text,
        )
        if m:
            qty = self._quantity(m.group(1))
            days = qty * (7 if m.group(2).startswith("week") else 1)
            return today + timedelta(days=days)

        # ISO date: 2026-08-20.
        m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
        if m:
            return self._build(today, int(m.group(1)), int(m.group(2)), int(m.group(3)))

        # US numeric dates: 8/20/2026, 08/20/26, 8/20.
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            year = self._normalize_year(m.group(3)) if m.group(3) else None
            return self._month_day(today, month, day, year)

        month_pattern = "|".join(sorted(self.MONTHS, key=len, reverse=True))

        # August 20th, August 20th 2026, August 20, 2026.
        m = re.search(
            rf"\b({month_pattern})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d{{2}}|\d{{2}}))?\b",
            text,
        )
        if m:
            month = self.MONTHS[m.group(1)]
            day = int(m.group(2))
            year = self._normalize_year(m.group(3)) if m.group(3) else None
            return self._month_day(today, month, day, year)

        # 20th of August, 20 August 2026.
        m = re.search(
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+({month_pattern})\.?(?:,?\s+(20\d{{2}}|\d{{2}}))?\b",
            text,
        )
        if m:
            day = int(m.group(1))
            month = self.MONTHS[m.group(2)]
            year = self._normalize_year(m.group(3)) if m.group(3) else None
            return self._month_day(today, month, day, year)

        special = self._special_date(today, text)
        if special is not None:
            return special

        weekday_pattern = "|".join(sorted(self.WEEKDAYS, key=len, reverse=True))

        # "next week Tuesday" / "this week Tuesday".
        m = re.search(rf"\b(this|next)\s+week(?:\s+on)?\s+({weekday_pattern})\b", text)
        if m:
            monday = today - timedelta(days=today.weekday())
            if m.group(1) == "next":
                monday += timedelta(days=7)
            return monday + timedelta(days=self.WEEKDAYS[m.group(2)])

        # "this Tuesday", "next Tuesday", "this coming Tuesday".
        m = re.search(rf"\b(this\s+coming|coming|this|next)\s+({weekday_pattern})\b", text)
        if m:
            qualifier = m.group(1)
            target = self.WEEKDAYS[m.group(2)]
            if qualifier == "this":
                monday = today - timedelta(days=today.weekday())
                return monday + timedelta(days=target)
            days_ahead = (target - today.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

        # Bare weekday -> closest occurrence, including today.
        m = re.search(rf"\b({weekday_pattern})\b", text)
        if m:
            target = self.WEEKDAYS[m.group(1)]
            days_ahead = (target - today.weekday() + 7) % 7
            return today + timedelta(days=days_ahead)

        return None

    def _special_date(self, today: datetime, text: str) -> datetime | None:
        fixed = {
            "new year's day": (1, 1),
            "new years day": (1, 1),
            "valentine's day": (2, 14),
            "valentines day": (2, 14),
            "independence day": (7, 4),
            "fourth of july": (7, 4),
            "4th of july": (7, 4),
            "halloween": (10, 31),
            "christmas": (12, 25),
            "christmas day": (12, 25),
        }
        for name, (month, day) in fixed.items():
            if name in text:
                return self._month_day(today, month, day, None)

        if "thanksgiving" in text:
            year = today.year
            candidate = self._nth_weekday_of_month(year, 11, 3, 4)
            if candidate.date() < today.date():
                candidate = self._nth_weekday_of_month(year + 1, 11, 3, 4)
            return self._copy_clock(today, candidate)

        return None

    @staticmethod
    def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
        first = datetime(year, month, 1)
        shift = (weekday - first.weekday() + 7) % 7
        day = 1 + shift + (n - 1) * 7
        return datetime(year, month, day)

    def _month_day(self, today: datetime, month: int, day: int, year: int | None) -> datetime | None:
        if year is not None:
            return self._build(today, year, month, day)

        candidate = self._build(today, today.year, month, day)
        if candidate is None:
            return None
        if candidate.date() < today.date():
            candidate = self._build(today, today.year + 1, month, day)
        return candidate

    @staticmethod
    def _build(today: datetime, year: int, month: int, day: int) -> datetime | None:
        try:
            max_day = monthrange(year, month)[1]
            if not 1 <= day <= max_day:
                return None
            return today.replace(year=year, month=month, day=day)
        except ValueError:
            return None

    @staticmethod
    def _copy_clock(source: datetime, target: datetime) -> datetime:
        return target.replace(
            hour=source.hour,
            minute=source.minute,
            second=source.second,
            microsecond=source.microsecond,
            tzinfo=source.tzinfo,
        )

    @classmethod
    def _quantity(cls, token: str) -> int:
        return int(token) if token.isdigit() else cls.NUMBER_WORDS[token]

    @staticmethod
    def _normalize_year(raw: str | None) -> int | None:
        if raw is None:
            return None
        year = int(raw)
        return 2000 + year if year < 100 else year

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())
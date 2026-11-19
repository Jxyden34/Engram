import pytest

from app.documents import is_supported
from app.jobs import extract_text


def test_calendar_export_retains_dates_people_and_recurrence():
    raw = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Engram//Test//EN
BEGIN:VEVENT
UID:one
DTSTAMP:20261114T100000Z
DTSTART;TZID=Europe/London:20261116T100000
DTEND;TZID=Europe/London:20261116T103000
SUMMARY:Project meeting
LOCATION:Room 4
ATTENDEE:mailto:guest@example.invalid
RRULE:FREQ=WEEKLY;COUNT=3
EXDATE;TZID=Europe/London:20261123T100000
DESCRIPTION:Discuss handover\n
 and review
END:VEVENT
BEGIN:VEVENT
UID:two
DTSTAMP:20261114T100000Z
DTSTART;VALUE=DATE:20261120
SUMMARY:All-day review
END:VEVENT
BEGIN:VEVENT
UID:three
DTSTAMP:20261114T100000Z
DTSTART;VALUE=DATE:20261120
SUMMARY:Cancelled meeting
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""
    assert is_supported("Calendar.ics")
    text = extract_text("Calendar.ics", raw)
    assert "2026-11-16T10:00:00+00:00" in text
    assert "guest@example.invalid" in text
    assert "Room 4" in text
    assert "FREQ=WEEKLY" in text
    assert "Excluded dates: 20261123T100000" in text
    assert "2026-11-20" in text
    assert "Cancelled meeting" not in text
    with pytest.raises(ValueError, match="5 MiB"):
        extract_text("Calendar.ics", b"x" * (5 * 1024 * 1024 + 1))

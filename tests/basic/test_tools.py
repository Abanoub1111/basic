import unittest

from email_assistant.tools.default.calendar_tools import schedule_meeting


class CalendarToolTests(unittest.TestCase):
    def test_schedule_meeting_accepts_an_iso_date(self) -> None:
        result = schedule_meeting.invoke(
            {
                "attendees": ["manager@example.com"],
                "subject": "Project meeting",
                "duration_minutes": 30,
                "preferred_day": "2026-09-06",
                "start_time": 14,
            }
        )

        self.assertIn("September 06, 2026", result)


if __name__ == "__main__":
    unittest.main()

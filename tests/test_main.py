import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main


class LeadApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.db"
        self.database_path_patch = patch.object(
            main, "database_path", self.database_path
        )
        self.database_path_patch.start()
        main.initialize_database()
        self.client = TestClient(main.app)

    def tearDown(self):
        self.database_path_patch.stop()
        self.temporary_directory.cleanup()

    @staticmethod
    def make_lead(**changes):
        lead = {
            "name": "Тестовый клиент",
            "phone": "+79001234567",
            "email": "test@mail.ru",
            "message": "Хочу автоматизировать бизнес",
        }
        lead.update(changes)
        return lead

    def get_saved_leads(self):
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM leads ORDER BY id"
                ).fetchall()
            ]

    @patch.object(main, "send_to_google_sheets", return_value=True)
    @patch.object(main, "send_to_telegram", return_value=True)
    def test_first_lead_is_saved_and_sent(self, telegram_mock, google_mock):
        response = self.client.post("/api/leads", json=self.make_lead())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["duplicate"], False)
        self.assertEqual(len(self.get_saved_leads()), 1)
        telegram_mock.assert_called_once()
        google_mock.assert_called_once()

    @patch.object(main, "send_to_google_sheets", return_value=True)
    @patch.object(main, "send_to_telegram", return_value=True)
    def test_duplicate_within_five_minutes_is_skipped(
        self, telegram_mock, google_mock
    ):
        first_response = self.client.post("/api/leads", json=self.make_lead())
        duplicate_response = self.client.post("/api/leads", json=self.make_lead())

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(duplicate_response.status_code, 200)
        self.assertEqual(duplicate_response.json()["duplicate"], True)
        self.assertEqual(
            duplicate_response.json()["message"],
            "Заявка уже была принята",
        )
        self.assertEqual(len(self.get_saved_leads()), 1)
        telegram_mock.assert_called_once()
        google_mock.assert_called_once()

    @patch.object(main, "send_to_google_sheets", return_value=True)
    @patch.object(main, "send_to_telegram", return_value=True)
    def test_normalized_values_are_treated_as_duplicate(
        self, telegram_mock, google_mock
    ):
        first_lead = self.make_lead(
            name="  Тестовый   клиент  ",
            phone="+7 900 123-45-67",
            email="TEST@MAIL.RU",
            message="  Хочу автоматизировать бизнес  ",
        )

        self.client.post("/api/leads", json=first_lead)
        response = self.client.post("/api/leads", json=self.make_lead())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["duplicate"], True)
        saved_leads = self.get_saved_leads()
        self.assertEqual(len(saved_leads), 1)
        self.assertEqual(saved_leads[0]["name"], "Тестовый клиент")
        self.assertEqual(saved_leads[0]["phone"], "+79001234567")
        self.assertEqual(saved_leads[0]["email"], "test@mail.ru")
        telegram_mock.assert_called_once()
        google_mock.assert_called_once()

    @patch.object(main, "send_to_google_sheets", return_value=True)
    @patch.object(main, "send_to_telegram", return_value=True)
    def test_matching_lead_older_than_five_minutes_is_created(
        self, telegram_mock, google_mock
    ):
        self.client.post("/api/leads", json=self.make_lead())
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE leads SET created_at = datetime('now', '-6 minutes')"
            )

        response = self.client.post("/api/leads", json=self.make_lead())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["duplicate"], False)
        self.assertEqual(len(self.get_saved_leads()), 2)
        self.assertEqual(telegram_mock.call_count, 2)
        self.assertEqual(google_mock.call_count, 2)

    @patch.object(main, "send_to_google_sheets", return_value=False)
    @patch.object(main, "send_to_telegram", return_value=True)
    def test_google_failure_does_not_lose_lead(
        self, telegram_mock, google_mock
    ):
        response = self.client.post(
            "/api/leads",
            json=self.make_lead(
                name="Тест ошибки",
                phone="+71111111111",
                email="failure@example.com",
                message="Google Sheets временно недоступен",
            ),
        )

        saved_lead = self.get_saved_leads()[0]
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(saved_lead["telegram_sent"], 1)
        self.assertEqual(saved_lead["google_sheets_sent"], 0)
        telegram_mock.assert_called_once()
        google_mock.assert_called_once()

    def assert_invalid_lead_is_rejected(self, **changes):
        with patch.object(main, "send_to_telegram") as telegram_mock, patch.object(
            main, "send_to_google_sheets"
        ) as google_mock:
            response = self.client.post(
                "/api/leads",
                json=self.make_lead(**changes),
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.get_saved_leads()), 0)
        telegram_mock.assert_not_called()
        google_mock.assert_not_called()

    def test_empty_name_is_rejected(self):
        self.assert_invalid_lead_is_rejected(name="   ")

    def test_invalid_email_is_rejected(self):
        self.assert_invalid_lead_is_rejected(email="not-an-email")

    def test_invalid_phone_is_rejected(self):
        self.assert_invalid_lead_is_rejected(phone="123")

    def test_empty_message_is_rejected(self):
        self.assert_invalid_lead_is_rejected(message="   ")

    def test_message_longer_than_2000_characters_is_rejected(self):
        self.assert_invalid_lead_is_rejected(message="А" * 2001)

    def test_health_reports_working_database(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_health_hides_database_error_details(self):
        with patch.object(
            main.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError("secret/path/test.db"),
        ):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"status": "error", "database": "unavailable"},
        )
        self.assertNotIn("secret", response.text)
        self.assertNotIn("path", response.text)

    def test_public_leads_list_is_disabled(self):
        response = self.client.get("/api/leads")

        self.assertEqual(response.status_code, 405)
        self.assertNotIn("test@mail.ru", response.text)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import maintenance_db as db
from ai_services import answer_knowledge_question, groq_configured, triage_issue


TECHNICIANS = [
    {
        "id": 1,
        "name": "Alex Morgan",
        "skills": "Mechanical, CNC, vibration",
        "availability": "Available",
        "active_work_orders": 1,
    },
    {
        "id": 2,
        "name": "Samira Patel",
        "skills": "Electrical, controls, sensors",
        "availability": "Available",
        "active_work_orders": 0,
    },
    {
        "id": 3,
        "name": "Jordan Lee",
        "skills": "Hydraulic, pumps, cooling",
        "availability": "Available",
        "active_work_orders": 0,
    },
]


class MaintenanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = db.DB_PATH
        db.DB_PATH = Path(cls.temp_dir.name) / "test.db"

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls.original_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        db.DB_PATH.unlink(missing_ok=True)
        db.initialize()
        secrets_patcher = patch("ai_services._load_secrets", return_value={})
        secrets_patcher.start()
        self.addCleanup(secrets_patcher.stop)

    def test_issue_triage_creates_and_closes_work_order(self):
        equipment = db.rows("SELECT * FROM equipment ORDER BY id LIMIT 1")[0]
        technicians = db.rows("SELECT * FROM technicians ORDER BY id")
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            triage, provider_error = triage_issue(
                "Machine is overheating and making unusual noise",
                equipment["name"],
                technicians,
                equipment["equipment_type"],
            )

        self.assertEqual(triage["priority"], "High")
        self.assertEqual(triage["category"], "Cooling")
        self.assertIsNone(provider_error)
        technician = next(
            tech for tech in technicians if tech["id"] == triage["assigned_technician_id"]
        )
        self.assertEqual(technician["name"], "Jordan Lee")
        issue_id = db.create_issue(
            equipment["id"], "Machine is overheating and making unusual noise", triage,
            triage["assigned_technician_id"],
        )
        saved_issue = db.row("SELECT * FROM issues WHERE id = ?", (issue_id,))
        task = db.row("SELECT * FROM maintenance_tasks WHERE issue_id = ?", (issue_id,))
        self.assertEqual(task["assigned_technician_id"], technician["id"])
        self.assertEqual(saved_issue["routing_provider"], "Local skill matching")
        self.assertIn("cooling", saved_issue["technician_match_reason"].lower())

        db.update_issue(issue_id, "In Progress", technician["id"])
        db.add_maintenance_record(equipment["id"], issue_id, technician["id"], "Cleaned fan and checked airflow", "Filter", 1.5)

        issue = db.row("SELECT status FROM issues WHERE id = ?", (issue_id,))
        task = db.row("SELECT status FROM maintenance_tasks WHERE issue_id = ?", (issue_id,))
        record_count = db.row("SELECT COUNT(*) AS total FROM maintenance_records")["total"]
        self.assertEqual(issue["status"], "Closed")
        self.assertEqual(task["status"], "Closed")
        self.assertEqual(record_count, 1)

    def test_document_assistant_returns_matching_grounded_passage(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            with patch(
                "ai_services.retrieve",
                return_value=[
                    {
                        "filename": "manual.txt",
                        "content": "For overheating, stop the machine and inspect the cooling fan and airflow.",
                        "score": 0.91,
                        "chunk_index": 0,
                    }
                ],
            ) as retrieve:
                answer, sources, provider_error = answer_knowledge_question(
                    "What does the manual say about overheating?",
                )
                retrieve.assert_called_once_with(
                    question="What does the manual say about overheating?",
                    top_k=5,
                )
        self.assertIn("cooling fan", answer.lower())
        self.assertEqual(sources[0]["filename"], "manual.txt")
        self.assertIsNone(provider_error)

    def test_local_fallback_uses_report_specific_causes_and_skill_match(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            with patch("ai_services._completion") as completion:
                cooling, _ = triage_issue(
                    "Cooling pump is overheating and airflow is blocked",
                    "PUMP-002",
                    TECHNICIANS,
                    "Cooling pump",
                )
                electrical, _ = triage_issue(
                    "Electrical control panel is sparking and sensor has alarm",
                    "PANEL-004",
                    TECHNICIANS,
                    "Control panel",
                )
                completion.assert_not_called()

        self.assertEqual(cooling["provider"], "Local rules-based triage")
        self.assertEqual(cooling["assigned_technician_id"], 3)
        self.assertEqual(electrical["assigned_technician_id"], 2)
        self.assertNotEqual(cooling["possible_causes"], electrical["possible_causes"])
        self.assertNotEqual(cooling["recommendation"], electrical["recommendation"])

    def test_groq_receives_roster_and_selects_a_valid_specialist(self):
        response = (
            '{"issue":"Pump vibration","category":"Hydraulic","priority":"High",'
            '"possible_causes":["Cavitation from restricted inlet flow"],'
            '"recommendation":"Check inlet pressure and inspect the impeller after isolation.",'
            '"assigned_technician_id":3,'
            '"technician_match_reason":"Jordan has pump and hydraulic skills with no active work orders."}'
        )
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}),
            patch("ai_services._completion", return_value=response) as completion,
        ):
            triage, provider_error = triage_issue(
                "PUMP-002 is vibrating and flow is low",
                "PUMP-002",
                TECHNICIANS,
                "Cooling pump",
            )

        self.assertIsNone(provider_error)
        self.assertEqual(triage["provider"], "Groq")
        self.assertEqual(triage["routing_provider"], "Groq")
        self.assertEqual(triage["assigned_technician_id"], 3)
        self.assertEqual(triage["possible_causes"], ["Cavitation from restricted inlet flow"])
        sent_prompt = completion.call_args.args[1]
        self.assertIn("PUMP-002 is vibrating and flow is low", sent_prompt)
        self.assertIn("Samira Patel", sent_prompt)
        self.assertIn("active_work_orders", sent_prompt)

    def test_groq_key_is_loaded_from_secrets_file(self):
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": ""}),
            patch(
                "ai_services._load_secrets",
                return_value={"GROQ_API_KEY": "test-secrets-file-key"},
            ),
            patch("groq.Groq") as groq_client,
        ):
            self.assertTrue(groq_configured())
            from ai_services import _groq_client

            _groq_client()

        groq_client.assert_called_once_with(api_key="test-secrets-file-key")

    def test_malformed_secrets_file_error_is_actionable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secrets_path = Path(temp_dir) / "secrets.toml"
            secrets_path.write_text(
                'GROQ_API_KEY = "unterminated', encoding="utf-8"
            )
            with (
                patch.dict("os.environ", {"GROQ_API_KEY": ""}),
                patch("ai_services.SECRETS_PATH", secrets_path),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"Could not parse \.streamlit/secrets\.toml",
                ):
                    groq_configured()

    def test_groq_key_and_model_support_groq_secret_section(self):
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "", "GROQ_MODEL": ""}),
            patch(
                "ai_services._load_secrets",
                return_value={
                    "groq": {"api_key": "section-secret", "model": "section-model"}
                },
            ),
        ):
            from ai_services import _setting

            self.assertTrue(groq_configured())
            self.assertEqual(
                _setting("GROQ_MODEL", "groq", "model", "default-model"),
                "section-model",
            )

    def test_environment_groq_key_overrides_secrets_file(self):
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "environment-key"}),
            patch(
                "ai_services._load_secrets",
                return_value={"GROQ_API_KEY": "secrets-file-key"},
            ),
            patch("groq.Groq") as groq_client,
        ):
            from ai_services import _groq_client

            _groq_client()

        groq_client.assert_called_once_with(api_key="environment-key")

    def test_groq_request_failure_is_reported_and_uses_skill_fallback(self):
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}),
            patch("ai_services._completion", side_effect=RuntimeError("provider unavailable")),
        ):
            triage, provider_error = triage_issue(
                "Electrical panel has lost power", "PANEL-004", TECHNICIANS, "Control panel"
            )

        self.assertIn("provider unavailable", provider_error)
        self.assertEqual(triage["provider"], "Local rules-based triage")
        self.assertEqual(triage["assigned_technician_id"], 2)
        self.assertEqual(triage["routing_provider"], "Local skill matching")

    def test_groq_cannot_assign_unknown_or_unavailable_technician(self):
        response = (
            '{"issue":"Electrical fault","category":"Electrical","priority":"High",'
            '"possible_causes":["Power supply fault"],"recommendation":"Isolate power and inspect.",'
            '"assigned_technician_id":99,"technician_match_reason":"Best technician."}'
        )
        roster = [dict(tech) for tech in TECHNICIANS]
        roster[1]["availability"] = "Unavailable"
        with (
            patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}),
            patch("ai_services._completion", return_value=response),
        ):
            triage, provider_error = triage_issue(
                "Electrical panel has lost power", "PANEL-004", roster, "Control panel"
            )

        self.assertIsNone(triage["assigned_technician_id"])
        self.assertEqual(triage["routing_provider"], "Local skill matching")
        self.assertIn("invalid or unavailable", provider_error)

    def test_existing_database_receives_ai_routing_columns(self):
        original_path = db.DB_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            db.DB_PATH = Path(temp_dir) / "legacy.db"
            try:
                with db.connect() as legacy_db:
                    legacy_db.executescript(
                        """
                        CREATE TABLE equipment (
                            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                            equipment_type TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'Operational', installed_on TEXT,
                            created_at TEXT NOT NULL
                        );
                        CREATE TABLE technicians (
                            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                            skills TEXT NOT NULL DEFAULT '', availability TEXT NOT NULL DEFAULT 'Available',
                            contact TEXT NOT NULL DEFAULT ''
                        );
                        CREATE TABLE issues (
                            id INTEGER PRIMARY KEY, equipment_id INTEGER NOT NULL,
                            title TEXT NOT NULL, description TEXT NOT NULL,
                            category TEXT NOT NULL DEFAULT 'General',
                            priority TEXT NOT NULL DEFAULT 'Medium',
                            status TEXT NOT NULL DEFAULT 'Open', assigned_technician_id INTEGER,
                            ai_summary TEXT NOT NULL DEFAULT '',
                            possible_causes TEXT NOT NULL DEFAULT '',
                            recommendation TEXT NOT NULL DEFAULT '',
                            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                        );
                        """
                    )
                db.initialize()
                columns = {column["name"] for column in db.rows("PRAGMA table_info(issues)")}
                self.assertTrue(
                    {"triage_provider", "routing_provider", "technician_match_reason"} <= columns
                )
            finally:
                db.DB_PATH = original_path


if __name__ == "__main__":
    unittest.main()

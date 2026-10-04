import importlib
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

import maintenance_db as db


class EquipmentAndTechnicianApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = db.DB_PATH
        db.DB_PATH = Path(cls.temp_dir.name) / "test.db"
        cls.api = importlib.import_module("api")

    @classmethod
    def tearDownClass(cls):
        db.DB_PATH = cls.original_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        db.DB_PATH.unlink(missing_ok=True)
        db.initialize()

    def test_equipment_can_be_partially_updated_and_deleted(self):
        equipment_id = db.rows("SELECT id FROM equipment ORDER BY id LIMIT 1")[0]["id"]

        result = self.api.update_equipment(
            equipment_id,
            self.api.EquipmentUpdatePayload(location="  Line 4  "),
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            db.row("SELECT location FROM equipment WHERE id = ?", (equipment_id,))[
                "location"
            ],
            "Line 4",
        )
        response = self.api.delete_equipment(equipment_id)
        self.assertEqual(response.status_code, 204)

    def test_technician_can_be_partially_updated_and_deleted(self):
        technician_id = db.rows("SELECT id FROM technicians ORDER BY id LIMIT 1")[0]["id"]

        result = self.api.update_technician(
            technician_id,
            self.api.TechnicianUpdatePayload(skills="  Electrical  "),
        )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            db.row("SELECT skills FROM technicians WHERE id = ?", (technician_id,))[
                "skills"
            ],
            "Electrical",
        )
        response = self.api.delete_technician(technician_id)
        self.assertEqual(response.status_code, 204)

    def test_delete_returns_conflict_for_referenced_equipment_and_technician(self):
        equipment = db.rows("SELECT id FROM equipment ORDER BY id LIMIT 1")[0]
        technician = db.rows("SELECT id FROM technicians ORDER BY id LIMIT 1")[0]
        db.execute(
            """INSERT INTO maintenance_records
               (equipment_id, technician_id, work_performed, completed_at)
               VALUES (?, ?, ?, ?)""",
            (equipment["id"], technician["id"], "Inspection", "2026-01-01"),
        )

        with self.assertRaises(HTTPException) as equipment_error:
            self.api.delete_equipment(equipment["id"])
        with self.assertRaises(HTTPException) as technician_error:
            self.api.delete_technician(technician["id"])

        self.assertEqual(equipment_error.exception.status_code, 409)
        self.assertEqual(technician_error.exception.status_code, 409)

    def test_update_returns_not_found_for_missing_items(self):
        with self.assertRaises(HTTPException) as equipment_error:
            self.api.update_equipment(
                9999, self.api.EquipmentUpdatePayload(location="Line 4")
            )
        with self.assertRaises(HTTPException) as technician_error:
            self.api.update_technician(
                9999, self.api.TechnicianUpdatePayload(skills="Electrical")
            )

        self.assertEqual(equipment_error.exception.status_code, 404)
        self.assertEqual(technician_error.exception.status_code, 404)

    def test_update_rejects_empty_and_duplicate_names(self):
        equipment = db.rows("SELECT id, name FROM equipment ORDER BY id")
        technician = db.rows("SELECT id, name FROM technicians ORDER BY id")

        with self.assertRaises(HTTPException) as empty_equipment_name:
            self.api.update_equipment(
                equipment[0]["id"], self.api.EquipmentUpdatePayload(name=" ")
            )
        with self.assertRaises(HTTPException) as duplicate_equipment_name:
            self.api.update_equipment(
                equipment[0]["id"],
                self.api.EquipmentUpdatePayload(name=equipment[1]["name"]),
            )
        with self.assertRaises(HTTPException) as empty_technician_name:
            self.api.update_technician(
                technician[0]["id"], self.api.TechnicianUpdatePayload(name=" ")
            )
        with self.assertRaises(HTTPException) as duplicate_technician_name:
            self.api.update_technician(
                technician[0]["id"],
                self.api.TechnicianUpdatePayload(name=technician[1]["name"]),
            )

        self.assertEqual(empty_equipment_name.exception.status_code, 422)
        self.assertEqual(duplicate_equipment_name.exception.status_code, 409)
        self.assertEqual(empty_technician_name.exception.status_code, 422)
        self.assertEqual(duplicate_technician_name.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()

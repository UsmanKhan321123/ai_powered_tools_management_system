"""SQLite persistence and data-access helpers for MaintainIQ."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


DB_PATH = Path(os.getenv("MAINTAINIQ_DB", str(Path(__file__).with_name("maintainiq.db"))))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def initialize() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                equipment_type TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Operational',
                installed_on TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS technicians (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                skills TEXT NOT NULL DEFAULT '',
                availability TEXT NOT NULL DEFAULT 'Available',
                contact TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'General',
                priority TEXT NOT NULL DEFAULT 'Medium',
                status TEXT NOT NULL DEFAULT 'Open',
                assigned_technician_id INTEGER REFERENCES technicians(id),
                ai_summary TEXT NOT NULL DEFAULT '',
                possible_causes TEXT NOT NULL DEFAULT '',
                recommendation TEXT NOT NULL DEFAULT '',
                triage_provider TEXT NOT NULL DEFAULT '',
                routing_provider TEXT NOT NULL DEFAULT '',
                technician_match_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS maintenance_tasks (
                id INTEGER PRIMARY KEY,
                issue_id INTEGER NOT NULL UNIQUE REFERENCES issues(id) ON DELETE CASCADE,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id),
                assigned_technician_id INTEGER REFERENCES technicians(id),
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                due_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS maintenance_records (
                id INTEGER PRIMARY KEY,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id),
                issue_id INTEGER REFERENCES issues(id),
                technician_id INTEGER REFERENCES technicians(id),
                work_performed TEXT NOT NULL,
                parts_used TEXT NOT NULL DEFAULT '',
                duration_hours REAL NOT NULL DEFAULT 0,
                completed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY,
                issue_id INTEGER REFERENCES issues(id) ON DELETE SET NULL,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id),
                recommendation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                source_hash TEXT NOT NULL UNIQUE,
                uploaded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
            CREATE INDEX IF NOT EXISTS idx_issues_equipment ON issues(equipment_id);
            CREATE INDEX IF NOT EXISTS idx_records_equipment ON maintenance_records(equipment_id);
            """
        )
        _ensure_issue_ai_columns(db)
        _seed(db)


def _ensure_issue_ai_columns(db: sqlite3.Connection) -> None:
    columns = {
        column["name"] for column in db.execute("PRAGMA table_info(issues)").fetchall()
    }
    for name in ("triage_provider", "routing_provider", "technician_match_reason"):
        if name not in columns:
            db.execute(f"ALTER TABLE issues ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def _seed(db: sqlite3.Connection) -> None:
    if db.execute("SELECT COUNT(*) FROM equipment").fetchone()[0] == 0:
        equipment = [
            ("CNC-001", "CNC Milling Machine", "Production floor A", "Operational"),
            ("PUMP-002", "Cooling Pump", "Utilities room", "Operational"),
            ("COMP-003", "Air Compressor", "Production floor B", "Operational"),
        ]
        db.executemany(
            "INSERT INTO equipment (name, equipment_type, location, status, installed_on, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(name, kind, location, status, None, _timestamp()) for name, kind, location, status in equipment],
        )
    if db.execute("SELECT COUNT(*) FROM technicians").fetchone()[0] == 0:
        technicians = [
            ("Alex Morgan", "Mechanical, CNC, vibration", "Available", ""),
            ("Samira Patel", "Electrical, controls, sensors", "Available", ""),
            ("Jordan Lee", "Hydraulic, pumps, cooling", "Available", ""),
        ]
        db.executemany(
            "INSERT INTO technicians (name, skills, availability, contact) VALUES (?, ?, ?, ?)",
            technicians,
        )


def rows(query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as db:
        return [dict(row) for row in db.execute(query, parameters).fetchall()]


def row(query: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as db:
        result = db.execute(query, parameters).fetchone()
        return dict(result) if result else None


def execute(query: str, parameters: tuple[Any, ...] = ()) -> int:
    with connect() as db:
        cursor = db.execute(query, parameters)
        return int(cursor.lastrowid or 0)


def add_equipment(name: str, equipment_type: str, location: str, installed_on: str | None) -> int:
    return execute(
        "INSERT INTO equipment (name, equipment_type, location, installed_on, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (name.strip(), equipment_type.strip(), location.strip(), installed_on, _timestamp()),
    )


def add_technician(name: str, skills: str, contact: str) -> int:
    return execute(
        "INSERT INTO technicians (name, skills, contact) VALUES (?, ?, ?)",
        (name.strip(), skills.strip(), contact.strip()),
    )


def create_issue(
    equipment_id: int,
    description: str,
    triage: dict[str, Any],
    technician_id: int | None,
) -> int:
    now = _timestamp()
    title = str(triage.get("issue") or description).splitlines()[0][:160]
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO issues
               (equipment_id, title, description, category, priority, assigned_technician_id,
                ai_summary, possible_causes, recommendation, triage_provider, routing_provider,
                technician_match_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                equipment_id,
                title,
                description.strip(),
                str(triage.get("category", "General")),
                str(triage.get("priority", "Medium")),
                technician_id,
                str(triage.get("issue", "")),
                "\n".join(str(cause) for cause in triage.get("possible_causes", [])),
                str(triage.get("recommendation", "")),
                str(triage.get("provider", "")),
                str(triage.get("routing_provider", "")),
                str(triage.get("technician_match_reason", "")),
                now,
                now,
            ),
        )
        issue_id = int(cursor.lastrowid)
        due_date = (date.today() + timedelta(days=1 if triage.get("priority") in {"Critical", "High"} else 3)).isoformat()
        db.execute(
            """INSERT INTO maintenance_tasks
               (issue_id, equipment_id, assigned_technician_id, description, status, due_date, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'Open', ?, ?, ?)""",
            (issue_id, equipment_id, technician_id, description.strip(), due_date, now, now),
        )
        db.execute(
            "INSERT INTO recommendations (issue_id, equipment_id, recommendation, created_at) VALUES (?, ?, ?, ?)",
            (issue_id, equipment_id, str(triage.get("recommendation", "")), now),
        )
        if triage.get("priority") in {"Critical", "High"}:
            db.execute("UPDATE equipment SET status = 'Needs Attention' WHERE id = ?", (equipment_id,))
        return issue_id


def update_issue(issue_id: int, status: str, technician_id: int | None) -> None:
    now = _timestamp()
    with connect() as db:
        issue = db.execute("SELECT equipment_id FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if not issue:
            raise ValueError("Issue no longer exists.")
        db.execute(
            "UPDATE issues SET status = ?, assigned_technician_id = ?, updated_at = ? WHERE id = ?",
            (status, technician_id, now, issue_id),
        )
        db.execute(
            "UPDATE maintenance_tasks SET status = ?, assigned_technician_id = ?, updated_at = ? WHERE issue_id = ?",
            (status, technician_id, now, issue_id),
        )
        if status == "Closed":
            open_count = db.execute(
                "SELECT COUNT(*) FROM issues WHERE equipment_id = ? AND status != 'Closed' AND id != ?",
                (issue["equipment_id"], issue_id),
            ).fetchone()[0]
            if open_count == 0:
                db.execute(
                    "UPDATE equipment SET status = 'Operational' WHERE id = ?",
                    (issue["equipment_id"],),
                )


def add_maintenance_record(
    equipment_id: int,
    issue_id: int | None,
    technician_id: int | None,
    work_performed: str,
    parts_used: str,
    duration_hours: float,
) -> int:
    with connect() as db:
        cursor = db.execute(
            """INSERT INTO maintenance_records
               (equipment_id, issue_id, technician_id, work_performed, parts_used, duration_hours, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                equipment_id,
                issue_id,
                technician_id,
                work_performed.strip(),
                parts_used.strip(),
                duration_hours,
                _timestamp(),
            ),
        )
        record_id = int(cursor.lastrowid)
        if issue_id is not None:
            issue = db.execute("SELECT status, assigned_technician_id FROM issues WHERE id = ?", (issue_id,)).fetchone()
            if issue and issue["status"] != "Closed":
                now = _timestamp()
                assigned = technician_id if technician_id is not None else issue["assigned_technician_id"]
                db.execute(
                    "UPDATE issues SET status = 'Closed', assigned_technician_id = ?, updated_at = ? WHERE id = ?",
                    (assigned, now, issue_id),
                )
                db.execute(
                    "UPDATE maintenance_tasks SET status = 'Closed', assigned_technician_id = ?, updated_at = ? WHERE issue_id = ?",
                    (assigned, now, issue_id),
                )
            open_count = db.execute(
                "SELECT COUNT(*) FROM issues WHERE equipment_id = ? AND status != 'Closed'",
                (equipment_id,),
            ).fetchone()[0]
            if open_count == 0:
                db.execute("UPDATE equipment SET status = 'Operational' WHERE id = ?", (equipment_id,))
        return record_id


def save_document(filename: str, content: str, source_hash: str) -> bool:
    with connect() as db:
        existing = db.execute(
            "SELECT id FROM knowledge_documents WHERE source_hash = ?", (source_hash,)
        ).fetchone()
        if existing:
            return False
        db.execute(
            "INSERT INTO knowledge_documents (filename, content, source_hash, uploaded_at) VALUES (?, ?, ?, ?)",
            (filename, content, source_hash, _timestamp()),
        )
        return True

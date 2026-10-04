"""MaintainIQ: JSON API backend for the maintenance operations workspace.

This replaces the former Streamlit front end. The HTML/CSS/JS client in
``static/`` talks to the endpoints defined here; all persistence, triage, and
retrieval work is delegated to the existing ``maintenance_db``,
``ai_services``, and ``rag_service`` modules.
"""

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import maintenance_db as db
from ai_services import (
    answer_knowledge_question,
    groq_configured,
    summarize_maintenance_history,
    triage_issue,
)
from rag_service import (
    DOCUMENTS_DIR,
    SUPPORTED_EXTENSIONS,
    index_document,
    index_text_document,
    list_indexed_documents,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

STATUS_OPTIONS = ["Open", "In Progress", "On Hold", "Closed"]

app = FastAPI(title="MaintainIQ", version="2.0.0")

db.initialize()


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class EquipmentPayload(BaseModel):
    name: str
    equipment_type: str
    location: str = ""
    installed_on: str | None = None


class TechnicianPayload(BaseModel):
    name: str
    skills: str = ""
    contact: str = ""


class EquipmentUpdatePayload(BaseModel):
    name: str | None = None
    equipment_type: str | None = None
    location: str | None = None
    installed_on: str | None = None
    status: str | None = None


class TechnicianUpdatePayload(BaseModel):
    name: str | None = None
    skills: str | None = None
    contact: str | None = None


class IssuePayload(BaseModel):
    equipment_id: int
    description: str


class IssueUpdatePayload(BaseModel):
    status: str
    technician_id: int | None = None


class RecordPayload(BaseModel):
    equipment_id: int
    issue_id: int | None = None
    technician_id: int | None = None
    work_performed: str
    parts_used: str = ""
    duration_hours: float = 0.0


class IssueRecordPayload(BaseModel):
    """Completion record for an existing work order; the asset comes from the issue."""

    technician_id: int | None = None
    work_performed: str
    parts_used: str = ""
    duration_hours: float = 0.0


class QuestionPayload(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


def _require(condition: Any, message: str, status_code: int = 422) -> None:
    if not condition:
        raise HTTPException(status_code=status_code, detail=message)


def equipment_options() -> list[dict[str, Any]]:
    return db.rows(
        "SELECT id, name, equipment_type, location, status, installed_on FROM equipment ORDER BY name"
    )


def technician_options() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT t.id, t.name, t.skills, t.availability, t.contact,
                  (SELECT COUNT(*) FROM issues i
                   WHERE i.assigned_technician_id = t.id AND i.status != 'Closed') AS active_work_orders
           FROM technicians t ORDER BY t.name"""
    )


def _equipment(equipment_id: int) -> dict[str, Any]:
    item = db.row(
        "SELECT id, name, equipment_type, location, status FROM equipment WHERE id = ?",
        (equipment_id,),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Equipment not found.")
    return item


def _technician_name(technicians: list[dict[str, Any]], technician_id: int | None) -> str | None:
    if technician_id is None:
        return None
    return next(
        (tech["name"] for tech in technicians if tech["id"] == technician_id),
        None,
    )


def _csv_response(
    records: list[dict[str, Any]],
    columns: dict[str, str],
    filename: str,
) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns))
    writer.writerow(columns)
    for record in records:
        writer.writerow({key: record.get(key, "") for key in columns})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Status and dashboard
# ---------------------------------------------------------------------------


@app.get("/api/status")
def read_status() -> dict[str, Any]:
    return {
        "groq_configured": groq_configured(),
        "indexed_documents": len(list_indexed_documents()),
    }


@app.get("/api/dashboard")
def read_dashboard() -> dict[str, Any]:
    equipment = equipment_options()
    issues = db.rows(
        """SELECT i.id, e.name AS equipment, i.title, i.category, i.priority, i.status,
                  COALESCE(t.name, 'Unassigned') AS technician, i.created_at
           FROM issues i JOIN equipment e ON e.id = i.equipment_id
           LEFT JOIN technicians t ON t.id = i.assigned_technician_id
           WHERE i.status != 'Closed' ORDER BY
             CASE i.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,
             i.created_at DESC"""
    )
    records_count = db.row("SELECT COUNT(*) AS total FROM maintenance_records")["total"]
    total_issues = db.row("SELECT COUNT(*) AS total FROM issues")["total"]
    open_issues = sum(issue["status"] != "Closed" for issue in db.rows("SELECT status FROM issues"))
    critical_issues = sum(issue["priority"] == "Critical" for issue in issues)

    health_counts: dict[str, int] = {}
    for item in equipment:
        health_counts[item["status"]] = health_counts.get(item["status"], 0) + 1

    recommendations = db.rows(
        """SELECT r.created_at, e.name AS equipment, r.recommendation
           FROM recommendations r JOIN equipment e ON e.id = r.equipment_id
           ORDER BY r.created_at DESC LIMIT 4"""
    )
    inventory = db.rows(
        """SELECT e.name AS equipment, e.equipment_type, e.location, e.status,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id AND i.status != 'Closed') AS open_requests,
                  (SELECT COUNT(*) FROM maintenance_records r WHERE r.equipment_id = e.id) AS service_records
           FROM equipment e ORDER BY open_requests DESC, e.name"""
    )

    return {
        "metrics": {
            "equipment": len(equipment),
            "open_issues": open_issues,
            "critical_issues": critical_issues,
            "records": records_count,
            "total_issues": total_issues,
        },
        "issues": issues[:8],
        "equipment_health": [
            {"status": status, "count": count} for status, count in health_counts.items()
        ],
        "recommendations": recommendations,
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# Equipment and technicians
# ---------------------------------------------------------------------------


@app.get("/api/equipment")
def list_equipment() -> list[dict[str, Any]]:
    return equipment_options()


@app.post("/api/equipment", status_code=201)
def create_equipment(payload: EquipmentPayload) -> dict[str, Any]:
    name = payload.name.strip()
    equipment_type = payload.equipment_type.strip()
    _require(name and equipment_type, "Asset ID/name and equipment type are required.")
    try:
        equipment_id = db.add_equipment(
            name, equipment_type, payload.location, payload.installed_on
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="An equipment item with that asset ID/name already exists.",
        ) from None
    return {"id": equipment_id}


@app.patch("/api/equipment/{equipment_id}")
def update_equipment(
    equipment_id: int, payload: EquipmentUpdatePayload
) -> dict[str, str]:
    updates = payload.model_dump(exclude_unset=True)
    _require(bool(updates), "Provide at least one equipment field to update.")
    _require(
        updates.get("name") is None or bool(updates["name"].strip()),
        "Asset ID/name cannot be empty.",
    )
    _require(
        updates.get("equipment_type") is None
        or bool(updates["equipment_type"].strip()),
        "Equipment type cannot be empty.",
    )
    _require(
        updates.get("status") is None
        or updates["status"] in {"Operational", "Needs Attention", "Offline"},
        "Unknown equipment status.",
    )
    _require(
        all(value is not None for key, value in updates.items()),
        "Equipment fields cannot be null.",
    )
    updates = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in updates.items()
    }
    try:
        updated = db.update_equipment(equipment_id, updates)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="An equipment item with that asset ID/name already exists.",
        ) from None
    if not updated:
        raise HTTPException(status_code=404, detail="Equipment not found.")
    return {"status": "ok"}


@app.delete("/api/equipment/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: int) -> Response:
    try:
        deleted = db.delete_equipment(equipment_id)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete equipment that has linked issues, work orders, records, or recommendations.",
        ) from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Equipment not found.")
    return Response(status_code=204)


@app.get("/api/technicians")
def list_technicians() -> list[dict[str, Any]]:
    return technician_options()


@app.post("/api/technicians", status_code=201)
def create_technician(payload: TechnicianPayload) -> dict[str, Any]:
    name = payload.name.strip()
    _require(name, "Technician name is required.")
    try:
        technician_id = db.add_technician(name, payload.skills, payload.contact)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A technician with that name already exists.",
        ) from None
    return {"id": technician_id}


@app.patch("/api/technicians/{technician_id}")
def update_technician(
    technician_id: int, payload: TechnicianUpdatePayload
) -> dict[str, str]:
    updates = payload.model_dump(exclude_unset=True)
    _require(bool(updates), "Provide at least one technician field to update.")
    _require(
        all(value is not None for value in updates.values()),
        "Technician fields cannot be null.",
    )
    _require(
        updates.get("name") is None or bool(updates["name"].strip()),
        "Technician name cannot be empty.",
    )
    updates = {key: value.strip() for key, value in updates.items()}
    try:
        updated = db.update_technician(technician_id, updates)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A technician with that name already exists.",
        ) from None
    if not updated:
        raise HTTPException(status_code=404, detail="Technician not found.")
    return {"status": "ok"}


@app.delete("/api/technicians/{technician_id}", status_code=204)
def delete_technician(technician_id: int) -> Response:
    try:
        deleted = db.delete_technician(technician_id)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a technician assigned to work orders or referenced by maintenance records.",
        ) from None
    if not deleted:
        raise HTTPException(status_code=404, detail="Technician not found.")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Issue triage and work orders
# ---------------------------------------------------------------------------


def _run_triage(payload: IssuePayload) -> dict[str, Any]:
    description = payload.description.strip()
    _require(
        len(description) >= 8,
        "Please describe the problem in a little more detail (at least 8 characters).",
    )
    equipment = _equipment(payload.equipment_id)
    technicians = technician_options()
    triage, provider_error = triage_issue(
        description,
        equipment["name"],
        technicians,
        equipment["equipment_type"],
    )
    return {
        "triage": triage,
        "provider_error": provider_error,
        "equipment": equipment,
        "suggested_technician": _technician_name(
            technicians, triage["assigned_technician_id"]
        ),
    }


@app.post("/api/issues/triage")
def preview_triage(payload: IssuePayload) -> dict[str, Any]:
    """Analyze an issue without persisting it, so the user can confirm first."""
    return _run_triage(payload)


@app.post("/api/issues", status_code=201)
def create_issue(payload: IssuePayload) -> dict[str, Any]:
    result = _run_triage(payload)
    triage = result["triage"]
    issue_id = db.create_issue(
        result["equipment"]["id"],
        payload.description.strip(),
        triage,
        triage["assigned_technician_id"],
    )
    return {**result, "issue_id": issue_id}


@app.get("/api/issues")
def list_issues() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT i.*, e.name AS equipment, COALESCE(t.name, 'Unassigned') AS technician,
                  mt.due_date
           FROM issues i JOIN equipment e ON e.id = i.equipment_id
           LEFT JOIN technicians t ON t.id = i.assigned_technician_id
           LEFT JOIN maintenance_tasks mt ON mt.issue_id = i.id
           ORDER BY CASE i.status WHEN 'Open' THEN 1 WHEN 'In Progress' THEN 2 WHEN 'On Hold' THEN 3 ELSE 4 END,
             CASE i.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,
             i.created_at DESC"""
    )


@app.patch("/api/issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueUpdatePayload) -> dict[str, str]:
    _require(payload.status in STATUS_OPTIONS, "Unknown work order status.")
    if db.row("SELECT id FROM issues WHERE id = ?", (issue_id,)) is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    if payload.technician_id is not None and db.row(
        "SELECT id FROM technicians WHERE id = ?", (payload.technician_id,)
    ) is None:
        raise HTTPException(status_code=422, detail="Unknown technician.")
    db.update_issue(issue_id, payload.status, payload.technician_id)
    return {"status": "ok"}


@app.post("/api/issues/{issue_id}/records", status_code=201)
def close_issue_with_record(issue_id: int, payload: IssueRecordPayload) -> dict[str, Any]:
    _require(payload.work_performed.strip(), "Describe the work performed before saving.")
    issue = db.row("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if issue is None:
        raise HTTPException(status_code=404, detail="Work order not found.")
    technician_id = (
        payload.technician_id
        if payload.technician_id is not None
        else issue["assigned_technician_id"]
    )
    record_id = db.add_maintenance_record(
        issue["equipment_id"],
        issue_id,
        technician_id,
        payload.work_performed,
        payload.parts_used,
        payload.duration_hours,
    )
    return {"record_id": record_id}


# ---------------------------------------------------------------------------
# Maintenance records
# ---------------------------------------------------------------------------


@app.get("/api/records")
def list_records() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT r.id, e.name AS equipment, COALESCE(t.name, 'Not specified') AS technician,
                  r.work_performed, r.parts_used, r.duration_hours, r.completed_at,
                  COALESCE(i.title, 'Planned / unlinked') AS issue
           FROM maintenance_records r JOIN equipment e ON e.id = r.equipment_id
           LEFT JOIN technicians t ON t.id = r.technician_id
           LEFT JOIN issues i ON i.id = r.issue_id
           ORDER BY r.completed_at DESC"""
    )


@app.post("/api/records", status_code=201)
def create_record(payload: RecordPayload) -> dict[str, Any]:
    _require(payload.work_performed.strip(), "Describe the completed maintenance work.")
    _equipment(payload.equipment_id)
    record_id = db.add_maintenance_record(
        payload.equipment_id,
        payload.issue_id,
        payload.technician_id,
        payload.work_performed,
        payload.parts_used,
        payload.duration_hours,
    )
    return {"record_id": record_id}


# ---------------------------------------------------------------------------
# Knowledge assistant
# ---------------------------------------------------------------------------


def _migrate_legacy_documents() -> list[str]:
    """Index knowledge documents that only exist in the SQLite table."""

    indexed = {document["filename"] for document in list_indexed_documents()}
    warnings: list[str] = []
    for document in db.rows(
        "SELECT filename, content FROM knowledge_documents ORDER BY uploaded_at DESC"
    ):
        if document["filename"] in indexed:
            continue
        try:
            result = index_text_document(document["filename"], document["content"])
        except (OSError, UnicodeError, ValueError, ImportError, RuntimeError) as exc:
            warnings.append(f"Could not index {document['filename']}: {exc}")
            continue
        if result["status"] in {"indexed", "already_indexed"}:
            indexed.add(document["filename"])
    return warnings


@app.get("/api/knowledge/documents")
def list_documents() -> dict[str, Any]:
    warnings = _migrate_legacy_documents()
    return {"documents": list_indexed_documents(), "warnings": warnings}


@app.post("/api/knowledge/documents", status_code=201)
def upload_documents(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for item in files:
        filename = Path(item.filename or "").name
        if not filename:
            results.append(
                {"filename": "", "status": "error", "message": "Empty filename."}
            )
            continue
        if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            results.append(
                {
                    "filename": filename,
                    "status": "error",
                    "message": f"Unsupported document type: {Path(filename).suffix}",
                }
            )
            continue
        try:
            target = DOCUMENTS_DIR / filename
            target.write_bytes(item.file.read())
            results.append(index_document(target))
        except (OSError, UnicodeError, ValueError, ImportError, RuntimeError) as exc:
            results.append(
                {"filename": filename, "status": "error", "message": str(exc)}
            )
    return {"results": results, "documents": list_indexed_documents()}


@app.post("/api/knowledge/ask")
def ask_question(payload: QuestionPayload) -> dict[str, Any]:
    question = payload.question.strip()
    _require(question, "Enter a question to search the knowledge base.")
    answer, sources, provider_error = answer_knowledge_question(question)
    return {"answer": answer, "sources": sources, "provider_error": provider_error}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _equipment_health() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT e.id, e.name, e.equipment_type, e.location, e.status,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id) AS total_issues,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id AND i.status != 'Closed') AS open_issues,
                  (SELECT COUNT(*) FROM maintenance_records r WHERE r.equipment_id = e.id) AS maintenance_records
           FROM equipment e ORDER BY open_issues DESC, total_issues DESC, e.name"""
    )


def _recurring_issues() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT e.name AS equipment, i.category, COUNT(*) AS issue_count,
                  SUM(CASE WHEN i.status != 'Closed' THEN 1 ELSE 0 END) AS open_count
           FROM issues i JOIN equipment e ON e.id = i.equipment_id
           GROUP BY e.id, i.category ORDER BY issue_count DESC"""
    )


def _recommendations() -> list[dict[str, Any]]:
    return db.rows(
        """SELECT r.created_at, e.name AS equipment, r.recommendation,
                  COALESCE(i.priority, '—') AS priority, COALESCE(i.status, '—') AS status
           FROM recommendations r JOIN equipment e ON e.id = r.equipment_id
           LEFT JOIN issues i ON i.id = r.issue_id ORDER BY r.created_at DESC"""
    )


@app.get("/api/reports")
def read_reports() -> dict[str, Any]:
    records = db.rows(
        """SELECT e.name AS equipment_name, r.work_performed, r.completed_at
           FROM maintenance_records r JOIN equipment e ON e.id = r.equipment_id
           ORDER BY r.completed_at DESC"""
    )
    return {
        "equipment_health": _equipment_health(),
        "recurring": _recurring_issues(),
        "history_summary": summarize_maintenance_history(records),
        "recommendations": _recommendations(),
    }


@app.get("/api/reports/equipment.csv")
def download_equipment_csv() -> Response:
    return _csv_response(
        _equipment_health(),
        {
            "id": "ID",
            "name": "Equipment",
            "equipment_type": "Type",
            "location": "Location",
            "status": "Health status",
            "total_issues": "Issues",
            "open_issues": "Open issues",
            "maintenance_records": "Maintenance records",
        },
        "maintainiq_equipment_health.csv",
    )


@app.get("/api/reports/recommendations.csv")
def download_recommendations_csv() -> Response:
    return _csv_response(
        _recommendations(),
        {
            "created_at": "Created",
            "equipment": "Equipment",
            "recommendation": "Recommendation",
            "priority": "Priority",
            "status": "Issue status",
        },
        "maintainiq_recommendations.csv",
    )


# ---------------------------------------------------------------------------
# Static front end
# ---------------------------------------------------------------------------

# Mounted last so the /api routes above take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

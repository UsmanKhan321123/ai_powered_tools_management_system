"""Optional AI integrations and local, no-key-required maintenance workflows."""

import json
import os
import re
from collections import Counter
from typing import Any

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def _setting(name: str, secret_section: str, secret_name: str, default: str = "") -> str:
    environment_value = os.getenv(name, "").strip()
    if environment_value:
        return environment_value
    try:
        secrets = st.secrets
        value = secrets.get(name)
        if value is None:
            section = secrets.get(secret_section, {})
            if hasattr(section, "get"):
                value = section.get(secret_name)
    except StreamlitSecretNotFoundError as exc:
        if exc.__cause__ is not None:
            raise RuntimeError(
                "Streamlit could not parse .streamlit/secrets.toml. "
                "Check that the API key is valid TOML, for example GROQ_API_KEY = \"your-key\"."
            ) from None
        return default
    return str(value).strip() if value is not None and str(value).strip() else default


def groq_api_key() -> str:
    return _setting("GROQ_API_KEY", "groq", "api_key")


def groq_configured() -> bool:
    return bool(groq_api_key())


def _groq_client():
    api_key = groq_api_key()
    if not api_key:
        return None
    from groq import Groq

    return Groq(api_key=api_key)


def _completion(system_prompt: str, user_prompt: str) -> str:
    client = _groq_client()
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    response = client.chat.completions.create(
        model=_setting("GROQ_MODEL", "groq", "model", "openai/gpt-oss-120b"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The AI provider returned an empty response.")
    return content.strip()


def _parse_json_response(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The AI provider returned invalid JSON.")
    result = json.loads(cleaned[start : end + 1])
    if not isinstance(result, dict):
        raise ValueError("The AI provider returned an unexpected response.")
    return result


def _local_technician_match(
    description: str,
    equipment_name: str,
    equipment_type: str,
    category: str,
    possible_causes: list[str],
    technicians: list[dict[str, Any]],
) -> tuple[int | None, str]:
    """Choose an available technician by documented skill and current workload."""
    available = [
        tech for tech in technicians
        if str(tech.get("availability", "")).strip().lower() == "available"
    ]
    if not available:
        return None, "No technician is currently marked available."

    evidence = " ".join([description, category, *possible_causes]).lower()
    asset_context = f"{equipment_name} {equipment_type}".lower()
    aliases = {
        "cooling": ("cooling", "coolant", "thermal", "overheat", "fan", "airflow"),
        "hydraulic": ("hydraulic", "fluid", "pressure", "hose", "seal", "leak"),
        "electrical": ("electrical", "electric", "voltage", "wiring", "power", "circuit"),
        "controls": ("controls", "control", "sensor", "software", "alarm", "error code"),
        "mechanical": ("mechanical", "bearing", "vibration", "alignment", "cnc", "shaft"),
        "pump": ("pump", "flow", "coolant", "pressure"),
    }
    scored: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for tech in available:
        skills = str(tech.get("skills", "")).lower()
        matched = [
            skill for skill in re.findall(r"[a-z][a-z0-9+#-]{2,}", skills)
            if skill in evidence
        ]
        asset_matches = [
            skill for skill in re.findall(r"[a-z][a-z0-9+#-]{2,}", skills)
            if skill in asset_context and skill not in matched
        ]
        for skill, related_terms in aliases.items():
            if skill in skills and any(term in evidence for term in related_terms):
                matched.append(skill)
            elif skill in skills and any(term in asset_context for term in related_terms):
                asset_matches.append(skill)
        unique_matches = list(dict.fromkeys(matched))
        unique_asset_matches = list(dict.fromkeys(asset_matches))
        workload = int(tech.get("active_work_orders", 0) or 0)
        relevance_score = len(unique_matches) * 10 + len(unique_asset_matches)
        scored.append(
            (
                relevance_score,
                -workload,
                tech,
                unique_matches + [f"{skill} (asset match)" for skill in unique_asset_matches],
            )
        )
    scored.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
    score, _, technician, matched_skills = scored[0]
    if score == 0:
        return None, "No available technician has a documented skill matching this issue; assign manually."
    skill_details = ", ".join(matched_skills)
    workload = int(technician.get("active_work_orders", 0) or 0)
    return (
        int(technician["id"]),
        f"Best available skill match ({skill_details}); {workload} active work order(s). "
        "Selected by local skill matching because Groq AI is unavailable.",
    )


def _local_triage(
    description: str,
    equipment_name: str,
    equipment_type: str,
    technicians: list[dict[str, Any]],
) -> dict[str, Any]:
    text = description.lower()
    category = "Mechanical"
    category_terms = {
        "Electrical": ("electrical", "power", "voltage", "wiring", "breaker", "motor"),
        "Cooling": ("overheat", "overheating", "temperature", "coolant", "cooling", "fan"),
        "Hydraulic": ("hydraulic", "pressure", "leak", "fluid", "hose"),
        "Controls": ("sensor", "control", "software", "alarm", "error code", "display"),
    }
    for candidate, terms in category_terms.items():
        if any(term in text for term in terms):
            category = candidate
            break

    urgent_terms = ("smoke", "fire", "sparking", "injury", "unsafe", "critical", "shutdown")
    high_terms = ("overheat", "overheating", "leak", "loud", "failed", "failure", "stopped")
    priority = "Critical" if any(term in text for term in urgent_terms) else (
        "High" if any(term in text for term in high_terms) else "Medium"
    )
    symptom_causes = (
        (("overheat", "hot", "temperature", "coolant"), "Cooling restriction, fan/pump degradation, or abnormal thermal load"),
        (("noise", "vibration", "rattle", "grinding"), "Loose or worn rotating components, bearing damage, or alignment imbalance"),
        (("leak", "dripping", "fluid", "pressure"), "A leaking seal/connection or an abnormal fluid-system pressure condition"),
        (("won't start", "wont start", "not starting", "stopped", "shutdown"), "A supply, interlock, control, or mechanical condition preventing normal startup"),
        (("alarm", "error", "fault code", "sensor"), "A sensor, control input, or recorded fault-code condition requiring verification"),
        (("slow", "weak", "low output", "reduced"), "A restriction, wear condition, or supply issue reducing normal output"),
        (("spark", "smoke", "burning"), "An electrical fault or overheated component requiring safe isolation"),
    )
    causes = [
        cause for terms, cause in symptom_causes
        if any(term in text for term in terms)
    ]
    if not causes:
        causes = [
            f"A fault in the {category.lower()} system affecting the reported {description.strip()[:100]}",
            f"A worn, obstructed, or misadjusted component in the {equipment_type or equipment_name} assembly",
        ]
    causes = causes[:4]
    inspect_target = {
        "Cooling": "cooling airflow, fan operation, and coolant condition",
        "Electrical": "the power source, isolation points, and damaged wiring",
        "Hydraulic": "fluid level, visible leaks, and pressure indications",
        "Controls": "the displayed fault code, affected sensor, and control connections",
        "Mechanical": "the reported component for looseness, wear, and alignment",
    }[category]
    recommendation = (
        f"Because the report mentions {description.strip()[:120]}, follow site isolation procedures before "
        f"inspection. Check {inspect_target}; record any fault codes or measurements and have a qualified "
        "technician confirm the cause before returning the equipment to service."
    )
    technician_id, routing_reason = _local_technician_match(
        description, equipment_name, equipment_type, category, causes, technicians
    )
    return {
        "issue": f"{equipment_name}: {description.strip()}",
        "category": category,
        "priority": priority,
        "possible_causes": causes,
        "recommendation": recommendation,
        "provider": "Local rules-based triage",
        "assigned_technician_id": technician_id,
        "technician_match_reason": routing_reason,
        "routing_provider": "Local skill matching",
    }


def triage_issue(
    description: str,
    equipment_name: str,
    technicians: list[dict[str, Any]] | None = None,
    equipment_type: str = "",
) -> tuple[dict[str, Any], str | None]:
    """Triage an issue and route it against the actual technician roster."""
    roster = technicians or []
    if not groq_configured():
        return _local_triage(description, equipment_name, equipment_type, roster), None

    technician_context = [
        {
            "id": technician["id"],
            "name": technician["name"],
            "skills": technician.get("skills", ""),
            "availability": technician.get("availability", "Unknown"),
            "active_work_orders": technician.get("active_work_orders", 0),
        }
        for technician in roster
    ]
    try:
        raw = _completion(
            "You are a maintenance triage and technician-routing assistant. Analyze only the reported "
            "symptoms; never claim a cause is certain. Return only JSON with keys: issue, category, "
            "priority, possible_causes (array of specific, symptom-related strings), recommendation, "
            "assigned_technician_id (integer from the supplied roster or null), technician_match_reason. "
            "Priority must be Low, Medium, High, or Critical. Choose the single best technician based on "
            "documented skills, availability, and active workload. Assign only a technician whose availability "
            "is Available. Never invent a technician or ID; use null if no available roster member is a suitable "
            "match. Give a specific, actionable, safety-conscious recommendation for this exact report.",
            f"Equipment: {equipment_name}\nEquipment type: {equipment_type or 'Not specified'}"
            f"\nReported problem: {description}\nTechnician roster: {json.dumps(technician_context)}",
        )
        result = _parse_json_response(raw)
        result["priority"] = str(result.get("priority", "Medium")).title()
        if result["priority"] not in {"Low", "Medium", "High", "Critical"}:
            result["priority"] = "Medium"
        causes = result.get("possible_causes", [])
        result["possible_causes"] = [str(cause) for cause in causes][:6] if isinstance(causes, list) else []
        result["issue"] = str(result.get("issue") or description)
        result["category"] = str(result.get("category") or "General")
        result["recommendation"] = str(
            result.get("recommendation") or "Have a qualified technician inspect the equipment."
        )
        result["provider"] = "Groq"

        available_by_id = {
            int(tech["id"]): tech
            for tech in roster
            if str(tech.get("availability", "")).strip().lower() == "available"
        }
        raw_selected_id = result.get("assigned_technician_id")
        invalid_selected_id = isinstance(raw_selected_id, bool)
        selected_id = None
        if isinstance(raw_selected_id, int) and not invalid_selected_id:
            selected_id = raw_selected_id
        elif isinstance(raw_selected_id, str) and raw_selected_id.strip().isdigit():
            selected_id = int(raw_selected_id.strip())
        elif raw_selected_id is not None:
            invalid_selected_id = True
        if selected_id in available_by_id:
            result["assigned_technician_id"] = selected_id
            result["technician_match_reason"] = str(
                result.get("technician_match_reason") or "Selected by Groq based on the technician roster."
            )
            result["routing_provider"] = "Groq"
            return result, None

        if selected_id is not None or invalid_selected_id:
            routing_error = "Groq returned an invalid or unavailable technician; local skill matching was used."
        else:
            routing_error = None
        technician_id, routing_reason = _local_technician_match(
            description, equipment_name, equipment_type, result["category"], result["possible_causes"], roster
        )
        result["assigned_technician_id"] = technician_id
        result["technician_match_reason"] = routing_reason
        result["routing_provider"] = "Local skill matching"
        return result, routing_error
    except Exception as exc:
        return _local_triage(description, equipment_name, equipment_type, roster), str(exc)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def retrieve_chunks(question: str, documents: list[dict[str, str]], limit: int = 4) -> list[dict[str, str]]:
    """Retrieve matching document passages using a lightweight local term scorer."""
    query_terms = set(_tokens(question))
    if not query_terms:
        return []
    passages: list[dict[str, str]] = []
    for document in documents:
        text = document["content"]
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        chunks: list[str] = []
        buffer = ""
        for paragraph in paragraphs or [text]:
            if len(buffer) + len(paragraph) > 1100 and buffer:
                chunks.append(buffer)
                buffer = ""
            buffer = f"{buffer}\n{paragraph}".strip()
        if buffer:
            chunks.append(buffer)
        for chunk in chunks:
            terms = _tokens(chunk)
            counts = Counter(terms)
            score = sum(min(counts[term], 3) for term in query_terms)
            if score:
                passages.append({"filename": document["filename"], "content": chunk, "score": str(score)})
    passages.sort(key=lambda passage: int(passage["score"]), reverse=True)
    return passages[:limit]


def answer_knowledge_question(
    question: str, documents: list[dict[str, str]]
) -> tuple[str, list[dict[str, str]], str | None]:
    passages = retrieve_chunks(question, documents)
    if not passages:
        return (
            "I could not find a matching passage in the uploaded maintenance documents. "
            "Add the relevant manual or procedure to the Knowledge base before relying on a document-grounded answer.",
            [],
            None,
        )
    context = "\n\n".join(
        f"[Source: {passage['filename']}]\n{passage['content']}" for passage in passages
    )
    if not os.getenv("GROQ_API_KEY"):
        excerpts = "\n\n".join(
            f"**{passage['filename']}**\n> {passage['content'][:900]}" for passage in passages
        )
        return f"Relevant passages from your uploaded documents:\n\n{excerpts}", passages, None
    try:
        answer = _completion(
            "Answer the maintenance question using only the supplied source excerpts. Clearly say when "
            "the sources do not contain an answer. Include relevant safety cautions and do not invent procedures.",
            f"Question: {question}\n\nSource excerpts:\n{context}",
        )
        return answer, passages, None
    except Exception as exc:
        excerpts = "\n\n".join(
            f"**{passage['filename']}**\n> {passage['content'][:900]}" for passage in passages
        )
        return f"Relevant passages from your uploaded documents:\n\n{excerpts}", passages, str(exc)


def summarize_maintenance_history(rows: list[dict[str, Any]]) -> str:
    """Summarize recurring issues from database-derived maintenance history."""
    if not rows:
        return "There is not enough maintenance history yet to identify recurring patterns."
    counts = Counter(row["equipment_name"] for row in rows)
    recurring = [f"{name}: {count} record(s)" for name, count in counts.most_common(5)]
    latest = rows[:3]
    recent = "; ".join(
        f"{row['equipment_name']} — {row['work_performed'][:120]}" for row in latest
    )
    return (
        f"Analyzed {len(rows)} maintenance record(s). Equipment with the most recorded work: "
        f"{', '.join(recurring)}. Recent work: {recent}"
    )

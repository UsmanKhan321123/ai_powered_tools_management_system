"""Optional AI integrations and local, no-key-required maintenance workflows."""

import json
import os
import re
from collections import Counter
from typing import Any


def _groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    from groq import Groq

    return Groq(api_key=api_key)


def _completion(system_prompt: str, user_prompt: str) -> str:
    client = _groq_client()
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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


def _local_triage(description: str, equipment_name: str) -> dict[str, Any]:
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
    causes_by_category = {
        "Cooling": ["Blocked airflow or dirty filters", "Cooling fan or pump fault", "Low coolant level"],
        "Electrical": ["Loose or damaged wiring", "Power supply or protection fault", "Motor or connection issue"],
        "Hydraulic": ["Worn seal or loose connection", "Low fluid level", "Blocked filter or pressure fault"],
        "Controls": ["Faulty sensor or connection", "Control setting or software issue", "Intermittent power supply"],
        "Mechanical": ["Wear or misalignment", "Loose or damaged component", "Insufficient lubrication"],
    }
    return {
        "issue": f"{equipment_name}: {description.strip()}",
        "category": category,
        "priority": priority,
        "possible_causes": causes_by_category[category],
        "recommendation": (
            "Follow site lockout/tagout and safety procedures. Inspect the equipment and isolate it "
            "if continued operation could cause damage or injury; have a qualified technician verify the cause."
        ),
        "provider": "Local rules-based triage",
    }


def triage_issue(description: str, equipment_name: str) -> tuple[dict[str, Any], str | None]:
    """Classify an issue; use local triage if the optional provider is unavailable."""
    if not os.getenv("GROQ_API_KEY"):
        return _local_triage(description, equipment_name), None
    try:
        raw = _completion(
            "You are a maintenance triage assistant. Return only JSON with keys: issue, category, "
            "priority, possible_causes (array of strings), recommendation. Category should be a concise "
            "maintenance discipline. Priority must be Low, Medium, High, or Critical. Be safety-conscious "
            "and do not claim a diagnosis is certain.",
            f"Equipment: {equipment_name}\nReported problem: {description}",
        )
        result = _parse_json_response(raw)
        result["priority"] = str(result.get("priority", "Medium")).title()
        if result["priority"] not in {"Low", "Medium", "High", "Critical"}:
            result["priority"] = "Medium"
        causes = result.get("possible_causes", [])
        result["possible_causes"] = [str(cause) for cause in causes][:6] if isinstance(causes, list) else []
        result["issue"] = str(result.get("issue") or description)
        result["category"] = str(result.get("category") or "General")
        result["recommendation"] = str(result.get("recommendation") or "Have a qualified technician inspect the equipment.")
        result["provider"] = "Groq"
        return result, None
    except Exception as exc:
        return _local_triage(description, equipment_name), str(exc)


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

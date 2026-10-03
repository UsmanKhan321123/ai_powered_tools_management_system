"""MaintainIQ: AI-assisted maintenance management in Streamlit."""

import hashlib
import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

import maintenance_db as db
from ai_services import (
    answer_knowledge_question,
    groq_configured,
    summarize_maintenance_history,
    triage_issue,
)


st.set_page_config(page_title="MaintainIQ | Maintenance Operations", page_icon="🛠️", layout="wide")
db.initialize()

st.markdown(
    """
    <style>
    :root {
        --ink: #152238;
        --muted: #718096;
        --line: #e8edf4;
        --surface: #ffffff;
        --canvas: #f5f7fb;
        --brand: #4968e8;
        --brand-dark: #3553cf;
        --mint: #13b89a;
    }
    html, body, [class*="css"] {font-family: Inter, 'Segoe UI', sans-serif;}
    [data-testid="stAppViewContainer"] {background: var(--canvas);}
    [data-testid="stHeader"] {background: transparent;}
    [data-testid="stMainBlockContainer"] {max-width: 1500px; padding: 2.1rem 3rem 4rem;}
    h1, h2, h3 {font-family: Inter, 'Segoe UI', sans-serif !important; color: var(--ink);}
    h1 {font-size: 2.15rem !important; font-weight: 800 !important; letter-spacing: -.055em !important;}
    h2 {font-size: 1.2rem !important; font-weight: 700 !important; letter-spacing: -.025em !important;}
    h3 {font-size: 1rem !important; font-weight: 700 !important;}
    p, label, li {color: #40506a;}

    [data-testid="stSidebar"] {background: #111b2d; border-right: 1px solid #1e2b40;}
    [data-testid="stSidebar"] > div:first-child {padding: 1.4rem 1rem;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color: #a6b3c6;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {color: #dbe4f2;}
    [data-testid="stSidebar"] [data-testid="stButton"] button {text-align:left; justify-content:flex-start;
        min-height:43px; padding:0 13px; border-radius:9px; font-size:13px;}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"] {
        color:#b2bfd0; background:transparent; border-color:transparent; box-shadow:none;}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="secondary"]:hover {
        color:#ffffff; background:#202d42; border-color:#202d42;}
    [data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
        color:#ffffff; background:linear-gradient(100deg,#334b9f,#3c56ad);
        border-color:transparent; box-shadow:0 5px 14px #0b13252b;}
    [data-testid="stSidebar"] hr {border-color: #2b374a;}

    .brand-lockup {display:flex; align-items:center; gap:12px; padding: 8px 8px 25px;}
    .brand-mark {width:42px; height:42px; display:flex; align-items:center; justify-content:center;
        border-radius:14px; background:linear-gradient(145deg,#637ef5,#3b57d0);
        color:white; font-size:21px; box-shadow:0 8px 22px #334db54d;}
    .brand-name {font-family:Inter,'Segoe UI',sans-serif; color:white; font-size:19px; font-weight:800; letter-spacing:-.7px;}
    .brand-sub {color:#8694a9; font-size:11px; margin-top:2px; letter-spacing:.3px;}
    .sidebar-caption {margin: 19px 8px 8px; color:#75859c; font-size:10px; font-weight:700; letter-spacing:1.25px; text-transform:uppercase;}
    .sidebar-foot {margin: 30px 8px 8px; padding-top:16px; border-top:1px solid #2b374a;
        color:#8795a9; font-size:12px; line-height:1.8;}
    .online-dot {display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:#21c994;}

    .page-intro {display:flex; justify-content:space-between; align-items:flex-end; gap:24px; margin:0 0 25px;}
    .page-eyebrow {color:#5570dd; font-size:10px; font-weight:700; letter-spacing:1.45px; text-transform:uppercase; margin-bottom:8px;}
    .page-title {font-family:Inter,'Segoe UI',sans-serif; color:var(--ink); font-size:32px; line-height:1.17;
        font-weight:800; letter-spacing:-1.15px; margin:0;}
    .page-subtitle {color:var(--muted); font-size:14px; margin-top:8px; max-width:730px; line-height:1.55;}
    .page-pill {white-space:nowrap; padding:8px 12px; border:1px solid #e2e8f2; border-radius:9px;
        background:white; color:#637087; font-size:11px; font-weight:600;}

    [data-testid="stMetric"] {height:100%; background:var(--surface); border:1px solid var(--line);
        padding:19px 20px; border-radius:14px; box-shadow:0 2px 7px #15223806;}
    [data-testid="stMetricLabel"] p {color:#718096; font-size:12px; font-weight:600;}
    [data-testid="stMetricValue"] {color:var(--ink); font-family:Inter,'Segoe UI',sans-serif; font-size:29px; font-weight:800;}
    [data-testid="stMetricDelta"] {font-size:11px;}
    [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {gap:1rem;}
    [data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid var(--line); border-radius:12px; overflow:hidden;}
    [data-testid="stDataFrame"] th {background:#f7f9fc;}

    [data-testid="stForm"], [data-testid="stExpander"] {border:1px solid var(--line); border-radius:13px; background:white;}
    [data-testid="stExpander"] summary {font-weight:600;}
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input, [data-testid="stDateInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {border-radius:9px;}
    [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
    [data-testid="stDownloadButton"] button {border-radius:9px; font-weight:600; min-height:40px;}
    [data-testid="stFormSubmitButton"] button[kind="primary"], [data-testid="stButton"] button[kind="primary"] {
        background:var(--brand); border-color:var(--brand);}
    [data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
    [data-testid="stButton"] button[kind="primary"]:hover {background:var(--brand-dark); border-color:var(--brand-dark);}
    [data-testid="stAlert"] {border-radius:11px;}
    [data-testid="stFileUploader"] section {border:1px dashed #c9d3e1; border-radius:12px; background:#fbfcfe;}
    .section-note {font-size:12px; color:var(--muted); margin-top:-8px; margin-bottom:15px;}
    .empty-state {padding:23px 20px; border:1px dashed #dce3ed; border-radius:12px;
        background:#ffffff; color:#7b8799; font-size:13px; line-height:1.6;}

    @media (max-width: 800px) {
        [data-testid="stMainBlockContainer"] {padding:1.4rem 1rem 2rem;}
        .page-intro {align-items:flex-start;}
        .page-pill {display:none;}
        .page-title {font-size:27px;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def page_header(eyebrow: str, title: str, subtitle: str, badge: str = "MAINTENANCE WORKSPACE") -> None:
    st.markdown(
        f"""
        <div class="page-intro">
            <div>
                <div class="page-eyebrow">{eyebrow}</div>
                <h1 class="page-title">{title}</h1>
                <div class="page-subtitle">{subtitle}</div>
            </div>
            <div class="page-pill">✦ &nbsp;{badge}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def safe_frame(data: list[dict], columns: dict[str, str] | None = None) -> None:
    if not data:
        st.markdown('<div class="empty-state">Nothing to show yet. New activity will appear here.</div>', unsafe_allow_html=True)
        return
    frame = pd.DataFrame(data)
    if columns:
        frame = frame.rename(columns=columns)
    st.dataframe(frame, width="stretch", hide_index=True)


def equipment_options() -> list[dict]:
    return db.rows("SELECT id, name, equipment_type, location, status FROM equipment ORDER BY name")


def technician_options() -> list[dict]:
    return db.rows(
        """SELECT t.id, t.name, t.skills, t.availability,
                  (SELECT COUNT(*) FROM issues i
                   WHERE i.assigned_technician_id = t.id AND i.status != 'Closed') AS active_work_orders
           FROM technicians t ORDER BY t.name"""
    )


def page_dashboard() -> None:
    page_header(
        "OVERVIEW",
        "Maintenance dashboard",
        "A clear view of asset health, open work, and the latest maintenance activity.",
        "LIVE OPERATIONS",
    )
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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total equipment", len(equipment), help="Assets currently in your register")
    c2.metric("Open requests", open_issues, delta=f"{critical_issues} critical", delta_color="inverse")
    c3.metric("Work completed", records_count, help="Logged maintenance records")
    c4.metric("Issues reported", total_issues)

    left, right = st.columns([1.45, 1])
    with left:
        st.subheader("Requests requiring attention")
        st.markdown('<div class="section-note">Prioritized by severity, with the most urgent work first.</div>', unsafe_allow_html=True)
        safe_frame(
            issues[:8],
            {
                "id": "ID",
                "equipment": "Equipment",
                "title": "Issue",
                "category": "Category",
                "priority": "Priority",
                "status": "Status",
                "technician": "Assigned technician",
                "created_at": "Reported",
            },
        )
    with right:
        st.subheader("Equipment health")
        if equipment:
            counts = pd.Series([item["status"] for item in equipment]).value_counts().rename_axis("Status").reset_index(name="Assets")
            chart = (
                alt.Chart(counts)
                .mark_arc(innerRadius=57, outerRadius=91, cornerRadius=4)
                .encode(
                    theta=alt.Theta("Assets:Q", stack=True),
                    color=alt.Color(
                        "Status:N",
                        scale=alt.Scale(
                            domain=["Operational", "Needs Attention", "Offline"],
                            range=["#20b894", "#f2a641", "#e15b64"],
                        ),
                        legend=alt.Legend(orient="bottom", direction="horizontal", title=None),
                    ),
                    tooltip=[
                        alt.Tooltip("Status:N", title="Equipment status"),
                        alt.Tooltip("Assets:Q", title="Assets"),
                    ],
                )
                .properties(height=245)
                .configure_view(strokeOpacity=0)
                .configure_legend(labelFont="Inter", labelColor="#65738a", labelFontSize=11, symbolSize=90)
            )
            st.altair_chart(chart, width="stretch")
        else:
            st.info("Add equipment to get started.")
        st.subheader("Latest recommendations")
        recommendations = db.rows(
            """SELECT r.created_at, e.name AS equipment, r.recommendation
               FROM recommendations r JOIN equipment e ON e.id = r.equipment_id
               ORDER BY r.created_at DESC LIMIT 4"""
        )
        for recommendation in recommendations:
            st.markdown(
                f"**{recommendation['equipment']}** · {recommendation['created_at'][:10]}  \n"
                f"{recommendation['recommendation']}"
            )
        if not recommendations:
            st.caption("AI recommendations will appear when the first issue is triaged.")

    st.divider()
    st.subheader("Equipment overview")
    st.markdown('<div class="section-note">Asset condition and active requests across your equipment register.</div>', unsafe_allow_html=True)
    inventory = db.rows(
        """SELECT e.name AS equipment, e.equipment_type, e.location, e.status,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id AND i.status != 'Closed') AS open_requests,
                  (SELECT COUNT(*) FROM maintenance_records r WHERE r.equipment_id = e.id) AS service_records
           FROM equipment e ORDER BY open_requests DESC, e.name"""
    )
    safe_frame(
        inventory,
        {
            "equipment": "Equipment",
            "equipment_type": "Type",
            "location": "Location",
            "status": "Health status",
            "open_requests": "Open requests",
            "service_records": "Service records",
        },
    )


def page_equipment() -> None:
    page_header("ASSET MANAGEMENT", "Equipment & team", "Manage your equipment register and the technicians who keep assets running.")
    equipment = equipment_options()
    technicians = technician_options()
    st.subheader("Equipment register")
    safe_frame(
        equipment,
        {
            "id": "ID",
            "name": "Asset",
            "equipment_type": "Equipment type",
            "location": "Location",
            "status": "Status",
        },
    )
    with st.expander("Add equipment"):
        with st.form("add_equipment_form"):
            name = st.text_input("Asset ID or name", placeholder="e.g. CNC-004")
            kind = st.text_input("Equipment type", placeholder="e.g. CNC milling machine")
            location = st.text_input("Location")
            installed = st.date_input("Installation date", value=None)
            submitted = st.form_submit_button("Add equipment", type="primary")
        if submitted:
            if not name.strip() or not kind.strip():
                st.error("Asset ID/name and equipment type are required.")
            else:
                try:
                    db.add_equipment(name, kind, location, installed.isoformat() if installed else None)
                    st.success("Equipment added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("An equipment item with that asset ID/name already exists.")

    st.divider()
    st.subheader("Technicians")
    safe_frame(
        technicians,
        {
            "id": "ID",
            "name": "Name",
            "skills": "Skills",
            "availability": "Availability",
            "active_work_orders": "Active work orders",
        },
    )
    with st.expander("Add technician"):
        with st.form("add_technician_form"):
            name = st.text_input("Technician name")
            skills = st.text_input("Skills (comma-separated)")
            contact = st.text_input("Contact details (optional)")
            submitted = st.form_submit_button("Add technician", type="primary")
        if submitted:
            if not name.strip():
                st.error("Technician name is required.")
            else:
                try:
                    db.add_technician(name, skills, contact)
                    st.success("Technician added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("A technician with that name already exists.")


def page_issue_intake() -> None:
    page_header("REQUEST INTAKE", "Report an issue", "Describe what happened. AI triage will help prioritize and route the request.", "AI-ASSISTED TRIAGE")
    equipment = equipment_options()
    technicians = technician_options()
    if not equipment:
        st.warning("Add equipment before reporting an issue.")
        return
    if groq_configured():
        st.caption("Groq AI will analyze the symptoms and select a technician using their actual skills, availability, and active workload.")
    else:
        st.warning("Groq AI is not configured. This request will use local rule-based triage and skill matching. Set GROQ_API_KEY and restart the app for AI-generated analysis and routing.")
    with st.form("report_issue_form"):
        selected_asset = st.selectbox(
            "Equipment",
            equipment,
            format_func=lambda item: f"{item['name']} — {item['equipment_type']} ({item['location'] or 'Location not set'})",
        )
        description = st.text_area(
            "Describe the problem",
            placeholder="Example: CNC-001 is overheating and making unusual noise.",
            height=140,
        )
        submitted = st.form_submit_button("Analyze & create maintenance request", type="primary")
    if submitted:
        if len(description.strip()) < 8:
            st.error("Please describe the problem in a little more detail (at least 8 characters).")
            return
        with st.spinner("Analyzing the issue and routing it to a technician..."):
            triage, provider_error = triage_issue(
                description,
                selected_asset["name"],
                technicians,
                selected_asset["equipment_type"],
            )
            tech_id = triage["assigned_technician_id"]
            issue_id = db.create_issue(selected_asset["id"], description, triage, tech_id)
        if provider_error:
            st.warning(
                f"Groq AI was unavailable or returned an invalid routing result; local symptom-based triage or skill matching was used. Details: {provider_error}"
            )
        st.success(f"Request #{issue_id} created and added to the maintenance work queue.")
        st.markdown(f"**Category:** {triage['category']} · **Priority:** {triage['priority']}")
        if tech_id:
            tech_name = next((tech["name"] for tech in technicians if tech["id"] == tech_id), "Assigned")
            st.markdown(f"**Suggested technician:** {tech_name}")
        else:
            st.warning("No suitable available technician was found. The request is unassigned and needs manual routing.")
        st.caption(f"Routing: {triage['routing_provider']} · {triage['technician_match_reason']}")
        st.markdown(f"**Initial recommendation:** {triage['recommendation']}")
        if triage["possible_causes"]:
            st.markdown("**Possible causes:**")
            for cause in triage["possible_causes"]:
                st.markdown(f"- {cause}")
        st.caption(
            f"Triage: {triage['provider']} · Routing: {triage['routing_provider']}. "
            "Verify all findings with a qualified technician."
        )


def page_work_orders() -> None:
    page_header("WORK MANAGEMENT", "Work orders", "Assign technicians, track progress, and close requests with a documented repair.", "LIVE QUEUE")
    issues = db.rows(
        """SELECT i.*, e.name AS equipment, COALESCE(t.name, 'Unassigned') AS technician
           FROM issues i JOIN equipment e ON e.id = i.equipment_id
           LEFT JOIN technicians t ON t.id = i.assigned_technician_id
           ORDER BY CASE i.status WHEN 'Open' THEN 1 WHEN 'In Progress' THEN 2 WHEN 'On Hold' THEN 3 ELSE 4 END,
             CASE i.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,
             i.created_at DESC"""
    )
    if not issues:
        st.info("No work orders yet. Report an equipment issue to create one.")
        return
    technicians = technician_options()
    status_options = ["Open", "In Progress", "On Hold", "Closed"]
    for issue in issues:
        title = f"#{issue['id']} · {issue['equipment']} · {issue['priority']} · {issue['status']}"
        with st.expander(title):
            st.write(issue["description"])
            st.caption(f"Category: {issue['category']} · Reported: {issue['created_at']} · Due: "
                       f"{(db.row('SELECT due_date FROM maintenance_tasks WHERE issue_id = ?', (issue['id'],)) or {}).get('due_date', '—')}")
            st.markdown(f"**AI recommendation:** {issue['recommendation'] or 'No recommendation available.'}")
            if issue.get("technician_match_reason"):
                st.caption(
                    f"Routing: {issue.get('routing_provider') or 'Manual'} · "
                    f"{issue['technician_match_reason']}"
                )
            with st.form(f"update_issue_{issue['id']}"):
                current_status = issue["status"] if issue["status"] in status_options else "Open"
                status = st.selectbox("Status", status_options, index=status_options.index(current_status), key=f"status_{issue['id']}")
                technician_ids = [None] + [tech["id"] for tech in technicians]
                current_tech = issue["assigned_technician_id"]
                selected_tech = st.selectbox(
                    "Assigned technician",
                    technician_ids,
                    index=technician_ids.index(current_tech) if current_tech in technician_ids else 0,
                    format_func=lambda value: "Unassigned" if value is None else next(
                        tech["name"] for tech in technicians if tech["id"] == value
                    ),
                    key=f"tech_{issue['id']}",
                )
                saved = st.form_submit_button("Save work order")
            if saved:
                db.update_issue(issue["id"], status, selected_tech)
                st.success("Work order updated.")
                st.rerun()
            with st.form(f"record_work_{issue['id']}"):
                st.markdown("**Log completed maintenance**")
                work = st.text_area("Work performed", key=f"work_{issue['id']}")
                parts = st.text_input("Parts used (optional)", key=f"parts_{issue['id']}")
                hours = st.number_input("Duration (hours)", min_value=0.0, max_value=1000.0, step=0.5, key=f"hours_{issue['id']}")
                technician_choice = st.selectbox(
                    "Technician who completed the work",
                    [None] + [tech["id"] for tech in technicians],
                    index=0,
                    format_func=lambda value: "Use current assignment" if value is None else next(
                        tech["name"] for tech in technicians if tech["id"] == value
                    ),
                    key=f"record_tech_{issue['id']}",
                )
                recorded = st.form_submit_button("Save maintenance record & close request")
            if recorded:
                if not work.strip():
                    st.error("Describe the work performed before saving.")
                else:
                    db.add_maintenance_record(
                        issue["equipment_id"],
                        issue["id"],
                        technician_choice if technician_choice is not None else issue["assigned_technician_id"],
                        work,
                        parts,
                        hours,
                    )
                    st.success("Maintenance record saved and request closed.")
                    st.rerun()


def page_records() -> None:
    page_header("SERVICE HISTORY", "Maintenance records", "Capture completed work and keep an auditable history for every asset.")
    equipment = equipment_options()
    technicians = technician_options()
    issues = db.rows(
        "SELECT id, equipment_id, title, status FROM issues ORDER BY created_at DESC"
    )
    with st.expander("Log planned or unlinked maintenance"):
        if not equipment:
            st.info("Add equipment first.")
        else:
            with st.form("planned_maintenance_form"):
                asset = st.selectbox("Equipment", equipment, format_func=lambda item: item["name"])
                issue_choices = [None] + [issue["id"] for issue in issues if issue["status"] != "Closed"]
                linked_issue = st.selectbox(
                    "Link to open issue (optional)",
                    issue_choices,
                    format_func=lambda value: "No linked issue" if value is None else next(
                        f"#{issue['id']} — {issue['title'][:65]}" for issue in issues if issue["id"] == value
                    ),
                )
                tech_id = st.selectbox(
                    "Technician",
                    [None] + [tech["id"] for tech in technicians],
                    format_func=lambda value: "Not specified" if value is None else next(
                        tech["name"] for tech in technicians if tech["id"] == value
                    ),
                )
                work = st.text_area("Work performed")
                parts = st.text_input("Parts used (optional)")
                hours = st.number_input("Duration (hours)", min_value=0.0, max_value=1000.0, step=0.5)
                submit = st.form_submit_button("Save maintenance record", type="primary")
            if submit:
                if not work.strip():
                    st.error("Describe the completed maintenance work.")
                else:
                    db.add_maintenance_record(asset["id"], linked_issue, tech_id, work, parts, hours)
                    st.success("Maintenance record saved.")
                    st.rerun()
    records = db.rows(
        """SELECT r.id, e.name AS equipment, COALESCE(t.name, 'Not specified') AS technician,
                  r.work_performed, r.parts_used, r.duration_hours, r.completed_at,
                  COALESCE(i.title, 'Planned / unlinked') AS issue
           FROM maintenance_records r JOIN equipment e ON e.id = r.equipment_id
           LEFT JOIN technicians t ON t.id = r.technician_id
           LEFT JOIN issues i ON i.id = r.issue_id
           ORDER BY r.completed_at DESC"""
    )
    safe_frame(
        records,
        {
            "id": "ID",
            "equipment": "Equipment",
            "issue": "Linked request",
            "technician": "Technician",
            "work_performed": "Work performed",
            "parts_used": "Parts used",
            "duration_hours": "Hours",
            "completed_at": "Completed",
        },
    )


def extract_document(uploaded_file) -> tuple[str, str]:
    filename = uploaded_file.name
    data = uploaded_file.getvalue()
    if filename.lower().endswith(".pdf"):
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            text = "\n\n".join(page.get_text() for page in pdf)
    else:
        text = data.decode("utf-8-sig", errors="replace")
    return text.strip(), hashlib.sha256(data).hexdigest()


def page_assistant() -> None:
    page_header("TECHNICAL KNOWLEDGE", "AI knowledge assistant", "Find answers in your uploaded manuals, troubleshooting guides, and safety procedures.", "DOCUMENT-ASSISTED")
    uploaded = st.file_uploader(
        "Add manuals, troubleshooting guides, and safety procedures",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        help="Documents are text-extracted and stored locally in your SQLite database.",
    )
    if uploaded:
        for item in uploaded:
            try:
                content, digest = extract_document(item)
                if not content:
                    st.warning(f"No extractable text found in {item.name}. Scanned PDFs need OCR before upload.")
                    continue
                if db.save_document(item.name, content, digest):
                    st.success(f"Indexed {item.name}.")
                else:
                    st.info(f"{item.name} is already in the knowledge base.")
            except (OSError, UnicodeError, ValueError) as exc:
                st.error(f"Could not process {item.name}: {exc}")
            except ImportError as exc:
                st.error(f"PDF processing dependency is missing: {exc}")
    docs = db.rows("SELECT id, filename, content, uploaded_at FROM knowledge_documents ORDER BY uploaded_at DESC")
    st.caption(f"{len(docs)} document(s) indexed.")
    if docs:
        safe_frame([{"filename": doc["filename"], "uploaded_at": doc["uploaded_at"]} for doc in docs],
                   {"filename": "Document", "uploaded_at": "Indexed"})
    with st.form("assistant_question_form"):
        question = st.text_input(
            "Your question",
            placeholder="What does the CNC manual recommend when the machine overheats?",
        )
        asked = st.form_submit_button("Search knowledge base", type="primary")
    if asked:
        if not question.strip():
            st.error("Enter a question to search the knowledge base.")
        else:
            with st.spinner("Searching indexed maintenance information..."):
                answer, sources, provider_error = answer_knowledge_question(
                    question, [{"filename": doc["filename"], "content": doc["content"]} for doc in docs]
                )
            st.subheader("Answer")
            st.write(answer)
            if provider_error:
                st.warning(f"Groq AI could not be reached; showing retrieved source passages instead. Details: {provider_error}")
            if sources:
                st.caption("Retrieved source passages")
                for source in sources:
                    with st.expander(f"{source['filename']} · relevance {source['score']}"):
                        st.write(source["content"])
            st.caption("Use the source manual and site safety procedures as the authority for maintenance work.")


def page_reports() -> None:
    page_header("ANALYTICS", "Reports & insights", "Understand asset health, recurring issues, and maintenance activity across your operation.")
    equipment = db.rows(
        """SELECT e.id, e.name, e.equipment_type, e.location, e.status,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id) AS total_issues,
                  (SELECT COUNT(*) FROM issues i WHERE i.equipment_id = e.id AND i.status != 'Closed') AS open_issues,
                  (SELECT COUNT(*) FROM maintenance_records r WHERE r.equipment_id = e.id) AS maintenance_records
           FROM equipment e ORDER BY open_issues DESC, total_issues DESC, e.name"""
    )
    st.subheader("Equipment health summary")
    safe_frame(
        equipment,
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
    )
    if equipment:
        csv = pd.DataFrame(equipment).to_csv(index=False).encode("utf-8")
        st.download_button("Download equipment health CSV", csv, "maintainiq_equipment_health.csv", "text/csv")
    st.subheader("Recurring issue analysis")
    recurring = db.rows(
        """SELECT e.name AS equipment, i.category, COUNT(*) AS issue_count,
                  SUM(CASE WHEN i.status != 'Closed' THEN 1 ELSE 0 END) AS open_count
           FROM issues i JOIN equipment e ON e.id = i.equipment_id
           GROUP BY e.id, i.category ORDER BY issue_count DESC"""
    )
    safe_frame(recurring, {"equipment": "Equipment", "category": "Category", "issue_count": "Reported", "open_count": "Still open"})
    records = db.rows(
        """SELECT e.name AS equipment_name, r.work_performed, r.completed_at
           FROM maintenance_records r JOIN equipment e ON e.id = r.equipment_id
           ORDER BY r.completed_at DESC"""
    )
    st.subheader("Analytics agent: maintenance history")
    st.write(summarize_maintenance_history(records))
    st.subheader("AI recommendation report")
    recommendations = db.rows(
        """SELECT r.created_at, e.name AS equipment, r.recommendation,
                  COALESCE(i.priority, '—') AS priority, COALESCE(i.status, '—') AS status
           FROM recommendations r JOIN equipment e ON e.id = r.equipment_id
           LEFT JOIN issues i ON i.id = r.issue_id ORDER BY r.created_at DESC"""
    )
    safe_frame(
        recommendations,
        {"created_at": "Created", "equipment": "Equipment", "recommendation": "Recommendation", "priority": "Priority", "status": "Issue status"},
    )
    if recommendations:
        data = pd.DataFrame(recommendations).to_csv(index=False).encode("utf-8")
        st.download_button("Download recommendation report", data, "maintainiq_recommendations.csv", "text/csv")


PAGES = {
    "Dashboard": page_dashboard,
    "Equipment & team": page_equipment,
    "Report an issue": page_issue_intake,
    "Work orders": page_work_orders,
    "Maintenance records": page_records,
    "AI knowledge assistant": page_assistant,
    "Reports & insights": page_reports,
}

with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
            <div class="brand-mark">✳</div>
            <div><div class="brand-name">MaintainIQ</div>
            <div class="brand-sub">INTELLIGENT OPERATIONS</div></div>
        </div>
        <div class="sidebar-caption">WORKSPACE</div>
        """,
        unsafe_allow_html=True,
    )
    page_icons = [
        "dashboard",
        "precision_manufacturing",
        "assignment",
        "build",
        "history",
        "auto_awesome",
        "monitoring",
    ]
    selected_page = st.session_state.get("selected_page", "Dashboard")
    for (page_label, _), icon in zip(PAGES.items(), page_icons):
        if st.button(
            page_label,
            key=f"nav_{page_label}",
            icon=f":material/{icon}:",
            type="primary" if page_label == selected_page else "secondary",
            width="stretch",
        ):
            st.session_state.selected_page = page_label
            st.rerun()
    st.markdown(
        """
        <div class="sidebar-foot">
            <span class="online-dot"></span> All systems operational<br>
            SQLite · Local-first
        </div>
        """,
        unsafe_allow_html=True,
    )
    if groq_configured():
        st.caption("Groq key configured · API checked per request")
    else:
        st.caption("Local AI fallback · GROQ_API_KEY not set")

PAGES[selected_page]()

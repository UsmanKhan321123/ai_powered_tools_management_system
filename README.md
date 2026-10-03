# MaintainIQ — AI-Powered Maintenance Management

MaintainIQ is a local-first maintenance workflow app built with Streamlit and SQLite. It includes an equipment register, issue intake and AI triage, technician routing, work orders, maintenance records, a document-grounded knowledge assistant, and downloadable operations reports.

## Requirements

- Python 3.10 or newer
- Optional: a Groq API key for generated triage and document-grounded answers. The app remains usable without a key by using local triage rules and showing the retrieved source passages directly.

## Run on Windows

From this project folder, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (usually `http://localhost:8501`). On first run, the app creates `maintainiq.db` and seeds example equipment and technicians.

The interface uses a custom MaintainIQ theme, native Streamlit icon navigation, and Altair charts. Fonts fall back to local system fonts; the UI does not require external font services.

To enable Groq, set the key in the same PowerShell window before starting Streamlit:

```powershell
$env:GROQ_API_KEY = "your-groq-api-key"
python -m streamlit run app.py
```

Alternatively, put the key in `.streamlit/secrets.toml` (do not commit this file):

```toml
GROQ_API_KEY = "your-groq-api-key"
```

The app also supports a `[groq]` secrets section with `api_key` and optional `model` entries. Restart Streamlit after editing the secrets file. The environment variable takes precedence over Streamlit secrets. The default model is `openai/gpt-oss-120b`; override it with `GROQ_MODEL` or the `[groq].model` secret if your account uses a different available model. The key is read from Streamlit secrets or the process environment and is never stored in the database.

Set `MAINTAINIQ_DB` to use a different SQLite file path. Otherwise, the database is stored alongside `app.py`.

## Main workflows

1. **Equipment & team:** Add assets and technicians; sample assets and technicians are supplied on first run.
2. **Report an issue:** Describe a problem, review its category, priority, symptom-specific potential causes, and recommendation, then create a routed work order. With Groq configured, one model request analyzes the issue and selects an available technician from the actual roster using documented skills and current open-workload counts. The selected ID is checked against the roster before it is saved.
3. **Work orders:** Assign a technician, update status, and log completed work. Saving a completion record closes the linked request.
4. **Maintenance records:** Log planned work or review the complete maintenance history.
5. **AI knowledge assistant:** Upload PDF, TXT, or Markdown manuals, then search relevant passages. Text-based PDFs are supported; scanned documents need OCR before upload.
6. **Reports & insights:** Review equipment health and recurring issues, inspect maintenance-history analysis, and download CSV reports.

## AI and data notes

- Groq is optional. For AI-generated issue analysis and technician routing, configure `GROQ_API_KEY` in the environment that launches Streamlit or in `.streamlit/secrets.toml`. The sidebar indicates whether the key is configured, and each new issue shows which provider handled triage and routing. Without a key or if the request fails, symptom-specific local rules and documented-skill matching are used and identified as a fallback; unmatched issues remain unassigned rather than going to an arbitrary technician. Document answers show retrieved source passages if Groq is unavailable.
- The document retriever uses local term matching. Uploaded document text is stored in the local SQLite database; no vector database or embedding model is required.
- AI suggestions are decision support, not a confirmed diagnosis. Qualified technicians and site safety procedures remain authoritative.
- The local SQLite database contains operational data and extracted document text. Protect it according to your organization's retention and access policies.

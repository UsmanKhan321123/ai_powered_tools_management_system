# MaintainIQ — AI-Powered Maintenance Management

MaintainIQ is a local-first maintenance workflow app built with a FastAPI backend, a
vanilla HTML/CSS/JS front end, and SQLite. It includes an equipment register, issue intake
and AI triage, technician routing, work orders, maintenance records, a document-grounded
knowledge assistant, and downloadable operations reports.

## Requirements

- Python 3.11 or newer (the configuration loader uses the standard-library `tomllib`)
- Optional: a Groq API key for generated triage and document-grounded answers. The app
  remains usable without a key by using local triage rules and showing the retrieved
  source passages directly.

## Run on Windows

From this project folder, run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn api:app --reload
```

Open `http://127.0.0.1:8000`. On first run, the app creates `maintainiq.db` and seeds
example equipment and technicians.

The interface is a single-page app served from `static/`. It uses a light and dark theme
with a toggle in the top bar, hand-rolled inline SVG charts, and no external CDN or font
services — the whole UI works offline.

To enable Groq, set the key in the same PowerShell window before starting the server:

```powershell
$env:GROQ_API_KEY = "your-groq-api-key"
python -m uvicorn api:app --reload
```

Alternatively, put the key in `.streamlit/secrets.toml` (do not commit this file):

```toml
GROQ_API_KEY = "your-groq-api-key"
```

The app also supports a `[groq]` secrets section with `api_key` and optional `model`
entries. The environment variable takes precedence over the secrets file, and values in a
`.env` file are loaded as a fallback. Restart the server after editing the secrets file.
The default model is `openai/gpt-oss-120b`; override it with `GROQ_MODEL` or the
`[groq].model` secret if your account uses a different available model. The key is read
from the environment or the secrets file and is never stored in the database.

Set `MAINTAINIQ_DB` to use a different SQLite file path. Otherwise, the database is stored
alongside `api.py`.

## Architecture

```
Browser (static/)  ──fetch/JSON──▶  api.py (FastAPI)  ──▶  maintenance_db.py
                                                            ai_services.py
                                                            rag_service.py
```

| Path | Role |
| --- | --- |
| `api.py` | REST endpoints and the static file mount |
| `static/index.html` | App shell: sidebar, top bar, view container |
| `static/css/styles.css` | Design system, light/dark themes, responsive layout |
| `static/js/api.js` | `fetch` wrapper |
| `static/js/ui.js` | Shared components: toasts, modals, tables, chips, SVG charts |
| `static/js/views.js` | The seven views |
| `static/js/main.js` | Hash router, theme toggle, sidebar drawer, status |
| `maintenance_db.py` | SQLite schema and data access |
| `ai_services.py` | Groq integration plus local triage/routing fallback |
| `rag_service.py` | ChromaDB + sentence-transformers retrieval pipeline |

Interactive API documentation is available at `http://127.0.0.1:8000/docs` while the
server is running.

## Main workflows

1. **Equipment & team:** Add assets and technicians; sample assets and technicians are
   supplied on first run.
2. **Report an issue:** Describe a problem and analyze it. The triage result shows its
   category, priority, symptom-specific potential causes, recommendation, and the selected
   technician — review it, then create the routed work order. With Groq configured, one
   model request analyzes the issue and selects an available technician from the actual
   roster using documented skills and current open-workload counts. The selected ID is
   checked against the roster before it is saved. The preview and the creation each run
   triage; with no Groq key both use the local fallback and cost nothing.
3. **Work orders:** Filter the queue, assign a technician, update status, and log completed
   work. Saving a completion record closes the linked request.
4. **Maintenance records:** Log planned work or review the complete maintenance history.
5. **AI knowledge assistant:** Upload PDF, TXT, or Markdown manuals, then search
   semantically relevant passages. Documents are stored under `data/manuals`, with
   embeddings and the vector index stored locally under `data/chroma`. Text-based PDFs are
   supported; scanned documents need OCR before upload.
6. **Reports & insights:** Review equipment health, recurring-issue analysis, and the
   maintenance-history summary, and download CSV reports from the server.

## AI and data notes

- Groq is optional. For AI-generated issue analysis and technician routing, configure
  `GROQ_API_KEY` in the environment that launches the server or in
  `.streamlit/secrets.toml`. The top bar indicates whether the key is configured, and each
  new issue shows which provider handled triage and routing. Without a key, or if the
  request fails, symptom-specific local rules and documented-skill matching are used and
  identified as a fallback; unmatched issues remain unassigned rather than going to an
  arbitrary technician. Document answers show retrieved source passages if Groq is
  unavailable.
- The document retriever uses ChromaDB and the local `sentence-transformers/all-MiniLM-L6-v2`
  embedding model. The model is downloaded on first use; uploaded source documents, the
  vector index, and its manifest remain local. Documents stored only in the SQLite
  knowledge table are migrated into the semantic index when the assistant is opened.
- AI suggestions are decision support, not a confirmed diagnosis. Qualified technicians and
  site safety procedures remain authoritative.
- The local SQLite database contains operational data and extracted document text. Protect
  it according to your organization's retention and access policies.

# MediShield Backend

FastAPI ingestion API for the multi-agent document intake pipeline.

## Run (from `backend/`)

```powershell
# from repo root, venv already active:
pip install -r backend\requirements.txt
uvicorn app.main:app --reload --app-dir backend
```

Then open http://127.0.0.1:8000/docs (Swagger UI).

## Day 1 endpoints

| Method | Path                              | Purpose                                  |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/health`                         | liveness check                           |
| POST   | `/cases/{case_id}/documents`      | upload a file into a case (created if new) |
| GET    | `/cases`                          | dashboard list of case summaries         |
| GET    | `/cases/{case_id}`                | full case with all documents             |

Upload accepts JPEG / PNG / TIFF / PDF; anything else returns 415.
Files are stored under `backend/storage/{case_id}/`; metadata in `backend/medishield.db` (SQLite).

## Acceptance test

In Swagger, POST a dataset PNG (e.g. `dataset/id_documents/id_PT_19116.png`) to
`/cases/C_001/documents`, then GET `/cases` — the case shows 1 document in status `RECEIVED`.

## Layout

```
backend/app/
  schemas.py   typed agent contracts (Pydantic + Enums)
  db.py        SQLite persistence (cases + documents)
  storage.py   filesystem file store (swap for S3 in prod)
  main.py      FastAPI app + endpoints
```

## Not wired yet (next days)

The classifier -> specialist -> fraud -> orchestrator pipeline. Uploads currently
land in `RECEIVED`; Day 2 adds a background task that advances the case through
the LangGraph state machine.

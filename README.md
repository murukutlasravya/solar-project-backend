# Solar Project AI Workspace - Backend

Simple FastAPI backend for managing projects, documents, and Q&A entries.
This is a starter backend for your capstone. It does **not** yet include AI or embeddings,
but the endpoints and data model are ready for that.

## Features

- SQLite database using SQLAlchemy
- Projects CRUD (basic)
- Upload documents per project (files stored on disk)
- List documents per project
- Ask questions per project (Q&A stored in DB, dummy answer for now)
- CORS enabled for a React frontend at http://localhost:5173

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload
```

API docs will be at: http://127.0.0.1:8000/docs

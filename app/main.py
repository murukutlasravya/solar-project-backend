from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
from pypdf import PdfReader

from .database import Base, engine, get_db
from . import schemas, crud
from .config import settings



# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Solar Project AI Workspace Backend",
    version="0.1.0",
)

# CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_ROOT = Path("uploads")
UPLOAD_ROOT.mkdir(exist_ok=True)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Projects


@app.get("/projects", response_model=List[schemas.Project])
def list_projects(db: Session = Depends(get_db)):
    return crud.get_projects(db)


@app.post("/projects", response_model=schemas.Project, status_code=201)
def create_project(project_in: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db, project_in)


@app.get("/projects/{project_id}", response_model=schemas.Project)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# Documents


@app.get("/projects/{project_id}/documents", response_model=List[schemas.Document])
def list_documents(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.get_documents_for_project(db, project_id)


@app.post("/projects/{project_id}/documents", response_model=schemas.Document, status_code=201)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    print(f"[upload_document] project_id={project_id}, filename={file.filename}")

    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 1) Save file to disk
    project_dir = UPLOAD_ROOT / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    dest_path = project_dir / file.filename

    content = await file.read()
    with dest_path.open("wb") as f:
        f.write(content)

    print(f"[upload_document] Saved file to {dest_path}")

    # 2) Create Document row
    doc = crud.create_document(
        db,
        project_id=project_id,
        file_name=file.filename,
        file_path=str(dest_path),
        status="ready",
    )
    print(f"[upload_document] Created Document id={doc.id}")

    # 3) Extract text and create chunks
    try:
        reader = PdfReader(str(dest_path))
        print(f"[upload_document] PDF has {len(reader.pages)} pages")

        for page_index, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            page_text = page_text.strip()
            print(f"[upload_document] Page {page_index+1} text length={len(page_text)}")

            if not page_text:
                continue

            crud.create_document_chunk(
                db,
                document_id=doc.id,
                project_id=project_id,
                page_number=page_index + 1,
                text=page_text,
            )

        db.commit()
        db.refresh(doc)
        print("[upload_document] Committed chunks to DB")

    except Exception as e:
        print(f"[upload_document] Error extracting text for document {doc.id}: {e}")

    return doc


# Q&A


@app.get("/projects/{project_id}/qa", response_model=List[schemas.QAEntry])
def list_qa(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return crud.get_qa_for_project(db, project_id)


@app.post("/projects/{project_id}/ask", response_model=schemas.QAEntry, status_code=201)
def ask_question(
    project_id: int,
    question_in: schemas.QuestionCreate,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # TODO: Replace this dummy answer with real AI + RAG logic
    dummy_answer = (
        "This is a placeholder answer from the backend. "
        "Once AI integration is added, this endpoint will call your agent "
        "to search project documents and generate a real answer."
    )

    qa = crud.create_qa_entry(db, project_id=project_id, question=question_in.question, answer=dummy_answer)
    return qa


@app.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
def delete_document(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = crud.get_document(db, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to remove file from disk
    try:
        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"[delete_document] Failed to delete file {doc.file_path}: {e}")

    ok = crud.delete_document(db, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")

    return Response(status_code=204)




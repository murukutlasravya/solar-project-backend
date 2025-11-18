from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List
from pypdf import PdfReader

from .database import Base, engine, get_db
from . import schemas, crud
from .config import settings
from .extractors import extract_pdf_text, extract_docx_text, extract_xlsx_text
from .rag import index_document_for_rag
from .agents import orchestrator_agent


# Debug: confirm OpenAI key loaded
print("DEBUG Google API KEY LOADED:", settings.GOOGLE_API_KEY)

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create DB tables
Base.metadata.create_all(bind=engine)

# Upload root
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
    """
    Upload a document (PDF, Word, or Excel), save it to disk,
    extract text into DocumentChunk rows, and index it for RAG.
    """
    # 1) Check project exists
    project = crud.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2) Save file under uploads/{project_id}/
    project_dir = UPLOAD_ROOT / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    dest_path = project_dir / file.filename

    content = await file.read()
    with dest_path.open("wb") as f:
        f.write(content)

    # 3) Create Document row
    doc = crud.create_document(
        db,
        project_id=project_id,
        file_name=file.filename,
        file_path=str(dest_path),
        status="ready",  # you can use 'processing' if you later background this
    )

    # 4) Extract text based on file type
    suffix = dest_path.suffix.lower()
    chunks_data: list[tuple[int, str]] = []

    try:
        if suffix == ".pdf":
            # returns list[(page_number, text)]
            chunks_data = extract_pdf_text(dest_path)
            print(f"[upload_document] Extracted {len(chunks_data)} PDF chunks for doc {doc.id}")

        elif suffix in (".docx",):
            # returns list[(section_index, text)]
            chunks_data = extract_docx_text(dest_path)
            print(f"[upload_document] Extracted {len(chunks_data)} DOCX chunks for doc {doc.id}")

        elif suffix in (".xlsx", ".xlsm", ".xls"):
            # returns list[(sheet_index, text)]
            chunks_data = extract_xlsx_text(dest_path)
            print(f"[upload_document] Extracted {len(chunks_data)} XLSX chunks for doc {doc.id}")

        else:
            print(f"[upload_document] Unsupported file type for text extraction: {suffix}")
            chunks_data = []

        # 5) Store chunks in DB
         # 5) Collect just the texts and store chunks in DB + vectorstore
        chunk_texts: list[str] = []
        for _, text in chunks_data:
            text = (text or "").strip()
            if text:
                chunk_texts.append(text)

        if chunk_texts:
            crud.create_document_chunks(
                db=db,
                project_id=project_id,
                document_id=doc.id,
                chunks=chunk_texts,
            )
            print(
                f"[upload_document] Saved {len(chunk_texts)} chunks for doc {doc.id} "
                "and indexed them in the vector store."
            )
        else:
            print(f"[upload_document] No non-empty text chunks for document {doc.id}.")

        # Ensure doc state is up to date for the response
        db.refresh(doc)

        # 6) Index for RAG (if any chunks exist)
        try:
            if chunks_data:
                index_document_for_rag(db, document_id=doc.id)
                print(f"[upload_document] Indexed document {doc.id} in vector store.")
            else:
                print(f"[upload_document] No text chunks to index for document {doc.id}.")
        except Exception as e:
            print(f"[RAG] Failed to index document {doc.id}: {e}")

    except Exception as e:
        print(f"[upload_document] Error processing document {doc.id}: {e}")

    # 7) Return Document info to frontend
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

    question = question_in.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Call orchestrator agent directly – assume OpenAI API is configured
    try:
        result = orchestrator_agent(db=db, project_id=project_id, question=question)
        final_answer = result.get("answer", "No answer produced by agents.")
    except Exception as e:
        # Fallback if agents / OpenAI fail
        final_answer = (
            "I ran into an error while running the AI agents. "
            "Backend is up, but the AI pipeline failed with:\n"
            f"{e}"
        )

    qa = crud.create_qa_entry(
        db,
        project_id=project_id,
        question=question,
        answer=final_answer,
    )
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

    doc = crud.get_document(db, project_id, document_id)
    if not doc or doc.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to remove file from disk
    try:
        file_path = Path(doc.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception as e:
        print(f"[delete_document] Failed to delete file {doc.file_path}: {e}")

    ok = crud.delete_document(db, project_id, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")

    return Response(status_code=204)


@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_endpoint(
    project_id: int,
    db: Session = Depends(get_db),
):
    deleted = crud.delete_project(db, project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)





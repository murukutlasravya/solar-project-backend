# app/crud.py

from __future__ import annotations

from typing import List, Optional, Any

from sqlalchemy.orm import Session

from . import models, schemas

# Vectorstore helpers (wrapped so missing imports don't crash the app)
try:
    from .vectorstore import (
        index_chunks,
        delete_project_vectors,
        delete_document_vectors,
    )
except Exception:  # pragma: no cover
    def index_chunks(chunks: List[dict]) -> None:
        print("[WARN] vectorstore.index_chunks not available")

    def delete_project_vectors(project_id: int) -> None:
        print(f"[WARN] vectorstore.delete_project_vectors not available for project {project_id}")

    def delete_document_vectors(project_id: int, document_id: int) -> None:
        print(f"[WARN] vectorstore.delete_document_vectors not available for doc {document_id}")


# ---------------------------------------------------------------------------
# PROJECTS
# ---------------------------------------------------------------------------

def get_projects(db: Session) -> List[models.Project]:
    """Return all projects ordered by newest first."""
    return (
        db.query(models.Project)
        .order_by(models.Project.created_at.desc())
        .all()
    )


def get_project(db: Session, project_id: int) -> Optional[models.Project]:
    """Return a single project by ID."""
    return (
        db.query(models.Project)
        .filter(models.Project.id == project_id)
        .first()
    )


def create_project(db: Session, project_in: schemas.ProjectCreate) -> models.Project:
    """Create a new project."""
    project = models.Project(
        name=project_in.name,
        description=project_in.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int) -> bool:
    """
    Delete a project and all related data:
    - QA entries
    - document chunks
    - documents + files
    - vectorstore entries
    """
    project = get_project(db, project_id)
    if not project:
        return False

    # Delete QA entries
    if hasattr(models, "QAEntry"):
        db.query(models.QAEntry).filter(
            models.QAEntry.project_id == project_id
        ).delete()

    # Delete chunks at DB level (if model exists)
    if hasattr(models, "DocumentChunk"):
        db.query(models.DocumentChunk).filter(
            models.DocumentChunk.project_id == project_id
        ).delete()

    # Delete all documents (DB rows, chunks, vectors, files)
    docs: List[models.Document] = (
        db.query(models.Document)
        .filter(models.Document.project_id == project_id)
        .all()
    )
    for doc in docs:
        delete_document(db, project_id, doc.id)

    # Delete vectorstore project-level entries (if implemented)
    try:
        delete_project_vectors(project_id)
    except Exception as e:
        print(f"[WARN] Failed to delete vectors for project {project_id}: {e}")

    # Finally delete project
    db.delete(project)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# DOCUMENTS
# ---------------------------------------------------------------------------

def create_document(
    db: Session,
    project_id: int,
    file_name: str,
    file_path: str,
    status: str = "processing",
) -> models.Document:
    """
    Create a Document row for an uploaded file.

    This is defensive about column names to avoid crashes like:
    'file_name' is an invalid keyword argument for Document
    """
    # Start with only fields we are sure exist
    doc = models.Document(
        project_id=project_id,
        status=status,
    )

    # Handle file name column variations
    if hasattr(models.Document, "file_name"):
        setattr(doc, "file_name", file_name)
    elif hasattr(models.Document, "filename"):
        setattr(doc, "filename", file_name)
    else:
        # Last resort: try generic "name"
        if hasattr(models.Document, "name"):
            setattr(doc, "name", file_name)

    # Handle file path column variations
    if hasattr(models.Document, "file_path"):
        setattr(doc, "file_path", file_path)
    elif hasattr(models.Document, "filepath"):
        setattr(doc, "filepath", file_path)
    else:
        if hasattr(models.Document, "path"):
            setattr(doc, "path", file_path)

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document(
    db: Session,
    project_id: int,
    document_id: int,
) -> Optional[models.Document]:
    """Fetch one document for a project."""
    return (
        db.query(models.Document)
        .filter(
            models.Document.id == document_id,
            models.Document.project_id == project_id,
        )
        .first()
    )


def get_documents_for_project(db: Session, project_id: int) -> List[models.Document]:
    """List all documents for a project."""
    return (
        db.query(models.Document)
        .filter(models.Document.project_id == project_id)
        .order_by(models.Document.uploaded_at.desc())
        .all()
    )


def delete_document(
    db: Session,
    project_id: int,
    document_id: int,
) -> bool:
    """
    Delete a single document, its chunks, vectors, and (optionally) file.
    """
    doc = get_document(db, project_id, document_id)
    if not doc:
        return False

    # Delete chunks tied to this document
    if hasattr(models, "DocumentChunk"):
        db.query(models.DocumentChunk).filter(
            models.DocumentChunk.document_id == document_id
        ).delete()

    # Delete vectorstore entries for this doc
    try:
        delete_document_vectors(project_id, document_id)
    except Exception as e:
        print(f"[WARN] Failed to delete vectors for doc {document_id}: {e}")

    # Try to delete the file from disk if path information exists
    try:
        from pathlib import Path

        file_path_value: Optional[str] = None
        if hasattr(doc, "file_path"):
            file_path_value = getattr(doc, "file_path")
        elif hasattr(doc, "filepath"):
            file_path_value = getattr(doc, "filepath")
        elif hasattr(doc, "path"):
            file_path_value = getattr(doc, "path")

        if file_path_value:
            p = Path(file_path_value)
            if p.exists():
                p.unlink()
    except Exception as e:
        print(f"[WARN] Failed to delete file for doc {document_id}: {e}")

    db.delete(doc)
    db.commit()
    return True


# Optional helper if you want to store text chunks in DB
def create_document_chunks(
    db: Session,
    project_id: int,
    document_id: int,
    chunks: List[str],
) -> None:
    """
    Store text chunks in DocumentChunk table and index them in the vectorstore.
    """
    if not hasattr(models, "DocumentChunk"):
        # No DB model defined; just index in vectorstore
        payload = [
            {
                "project_id": project_id,
                "document_id": document_id,
                "chunk_index": idx,
                "content": text,
            }
            for idx, text in enumerate(chunks)
        ]
        index_chunks(payload)
        return

    db_chunks: List[models.DocumentChunk] = []
    for idx, text in enumerate(chunks):
        db_chunks.append(
            models.DocumentChunk(
                project_id=project_id,
                document_id=document_id,
                chunk_index=idx,
                content=text,
            )
        )
    db.add_all(db_chunks)
    db.commit()

    # Prepare payload for vectorstore
    payload = [
        {
            "project_id": project_id,
            "document_id": document_id,
            "chunk_index": idx,
            "content": text,
        }
        for idx, text in enumerate(chunks)
    ]
    index_chunks(payload)


# ---------------------------------------------------------------------------
# Q&A ENTRIES
# ---------------------------------------------------------------------------

def get_qa_for_project(db: Session, project_id: int) -> List[models.QAEntry]:
    """Return all Q&A entries for a project, newest first."""
    if not hasattr(models, "QAEntry"):
        return []

    return (
        db.query(models.QAEntry)
        .filter(models.QAEntry.project_id == project_id)
        .order_by(models.QAEntry.created_at.asc())
        .all()
    )


def create_qa_entry(
    db: Session,
    project_id: int,
    question: str,
    answer: str,
    agent: Optional[str] = None,
    intent: Optional[str] = None,
) -> models.QAEntry:
    """
    Store a Q&A entry.

    Handles cases where the QA model may or may not have agent/intent columns.
    """
    if not hasattr(models, "QAEntry"):
        raise RuntimeError("QAEntry model is not defined in models.py")

    kwargs: dict[str, Any] = {
        "project_id": project_id,
        "question": question,
        "answer": answer,
    }

    # Only set these if columns exist
    if agent is not None and hasattr(models.QAEntry, "agent"):
        kwargs["agent"] = agent
    if intent is not None and hasattr(models.QAEntry, "intent"):
        kwargs["intent"] = intent

    qa = models.QAEntry(**kwargs)
    db.add(qa)
    db.commit()
    db.refresh(qa)
    return qa

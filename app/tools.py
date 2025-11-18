# app/tools.py

from typing import Dict, Any
from sqlalchemy.orm import Session

from . import models
from .rag import answer_question_with_rag


def rag_answer_for_project(
    db: Session,
    project_id: int,
    question: str,
) -> Dict[str, Any]:
    """
    Wrapper around the RAG engine to return answer + sources.
    """
    answer, sources = answer_question_with_rag(
        db=db,
        project_id=project_id,
        question=question,
        top_k=5,
    )
    return {"answer": answer, "sources": sources}


def quick_project_summary(db: Session, project_id: int) -> str:
    """
    Build a rough textual context using the first N chunks
    for use in summarization.
    """
    chunks = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.project_id == project_id)
        .order_by(models.DocumentChunk.id.asc())
        .limit(25)
        .all()
    )
    if not chunks:
        return "No document chunks are indexed for this project yet."

    parts = [c.text.strip().replace("\n", " ") for c in chunks]
    return "\n\n".join(parts)


def analyze_diagram_page(
    db: Session,
    project_id: int,
    document_id: int,
    page_number: int,
) -> str:
    """
    Very simple diagram 'analysis':
    For now, just concatenates text chunks for the given document & page.
    Later, you can upgrade this to true vision (PDF -> image -> Gemini).
    """
    chunks = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.project_id == project_id)
        .filter(models.DocumentChunk.document_id == document_id)
        .filter(models.DocumentChunk.page_number == page_number)
        .all()
    )
    if not chunks:
        return (
            f"No text chunks found for doc {document_id}, page {page_number}. "
            f"Either the page has no text, or it hasn't been indexed yet."
        )

    parts = [c.text.strip().replace("\n", " ") for c in chunks]
    context = "\n\n".join(parts)
    header = (
        f"Diagram / page context for project {project_id}, "
        f"document {document_id}, page {page_number}:\n\n"
    )
    return header + context

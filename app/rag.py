# app/rag.py

from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
import google.generativeai as genai

from .config import settings
from . import models

# Single source of truth for model name
GEMINI_TEXT_MODEL = "gemini-2.5-flash"


def index_document_for_rag(db: Session, document_id: int) -> None:
    """
    NO-OP for now.

    Previously, this would index document chunks into a vector store (Chroma)
    using embeddings. Since we're currently not using embeddings, we just log
    and return. This keeps the upload flow working without errors.
    """
    print(f"[RAG] Skipping vectorstore indexing for document {document_id} (embeddings disabled).")
    return


def _load_project_chunks(
    db: Session,
    project_id: int,
    max_chunks: int = 50,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Simple fallback context builder:

    1) Try to load chunks for this project_id.
    2) If none found, fall back to first N chunks in the whole table
       (so the system still works even if project_id wasn't set correctly).
    """
    chunks = (
        db.query(models.DocumentChunk)
        .filter(models.DocumentChunk.project_id == project_id)
        .order_by(models.DocumentChunk.id.asc())
        .limit(max_chunks)
        .all()
    )
    print(f"[RAG DEBUG] Loaded {len(chunks)} chunks for project {project_id}")

    if not chunks:
        chunks = (
            db.query(models.DocumentChunk)
            .order_by(models.DocumentChunk.id.asc())
            .limit(max_chunks)
            .all()
        )
        print(
            f"[RAG DEBUG] No chunks for project {project_id}, "
            f"falling back to {len(chunks)} global chunks"
        )

    if not chunks:
        return "", []

    parts: List[str] = []
    sources: List[Dict[str, Any]] = []

    for c in chunks:
        content = (c.content or "").strip().replace("\n", " ")
        parts.append(
            f"(Project {c.project_id}, Doc {c.document_id}, ChunkIndex {c.chunk_index}) {content}"
        )
        sources.append(
            {
                "project_id": c.project_id,
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
            }
        )

    context = "\n\n".join(parts)
    return context, sources


def generate_answer_from_context(question: str, context: str) -> str:
    """
    Use Gemini to generate an answer based on the context.
    """
    if not settings.GOOGLE_API_KEY:
        return (
            "AI is not configured yet (missing GOOGLE_API_KEY). "
            "Please configure the backend to enable RAG answers."
        )

    if not context:
        return (
            "I couldn't find any indexed text for this project yet. "
            "Try uploading project documents or checking that chunking worked."
        )

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    print("[LLM DEBUG] Using model:", GEMINI_TEXT_MODEL)
    model = genai.GenerativeModel(GEMINI_TEXT_MODEL)

    system_prompt = (
        "You are a senior electrical engineer specializing in utility-scale solar PV, "
        "BESS, and substation design. Answer based ONLY on the provided context from "
        "project documents. If the answer is not in the context, say you don't know."
    )

    user_prompt = (
        f"{system_prompt}\n\n"
        f"Context from project documents:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer in 2–5 clear sentences, and keep it practical for an engineer."
    )

    resp = model.generate_content(user_prompt)
    return resp.text or ""


def answer_question_with_rag(
    db: Session,
    project_id: int,
    question: str,
    top_k: int = 5,  # kept for compatibility; not used in this fallback mode
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Main RAG entry point in NO-EMBEDDINGS mode.
    """
    context, sources = _load_project_chunks(
        db=db,
        project_id=project_id,
        max_chunks=50,
    )
    answer = generate_answer_from_context(question=question, context=context)
    return answer, sources

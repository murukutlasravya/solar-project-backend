# app/vectorstore.py
from pathlib import Path
from .config import settings
from typing import List, Dict, Optional, Any

import chromadb
from chromadb import PersistentClient

client = PersistentClient(path=str(Path("chroma_db")))

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Call Gemini embedding API for a list of texts.
    Returns a list of embedding vectors.
    """
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    # Configure Gemini each time (cheap & safe)
    genai.configure(api_key=settings.GOOGLE_API_KEY)

    embeddings: List[List[float]] = []
    for t in texts:
        resp = genai.embed_content(
            model=settings.GEMINI_EMBED_MODEL,
            content=t,
            task_type="retrieval_document",
        )
        embeddings.append(resp["embedding"])
    return embeddings

def index_chunks(chunks: List[Dict[str, Any]]) -> None:
    """
    Index a batch of chunks in Chroma.

    Each chunk dict must have:
      - id: str
      - text: str
      - project_id: int
      - document_id: int
      - page_number: int
    """
    if not chunks:
        return

    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [
        {
            "project_id": c["project_id"],
            "document_id": c["document_id"],
            "page_number": c["page_number"],
        }
        for c in chunks
    ]

    embeddings = embed_texts(texts)

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def query_project_chunks(
    project_id: int,
    question: str,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Query Chroma for chunks relevant to a question within a given project.
    Returns the raw Chroma query result.
    """
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    q_emb = embed_texts([question])[0]

    results = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        where={"project_id": project_id},
    )
    return results


def delete_project_vectors(project_id: int) -> None:
    """
    Delete the Chroma collection for a given project.
    Safe to call even if the collection doesn't exist.
    """
    collection_name = f"project_{project_id}"
    try:
        client.delete_collection(name=collection_name)
        print(f"[VECTORSTORE] Deleted collection {collection_name}")
    except Exception as e:
        # Don't crash project deletes if Chroma is missing or already gone
        print(f"[VECTORSTORE] Failed to delete collection {collection_name}: {e}")



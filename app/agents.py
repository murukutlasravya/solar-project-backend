# app/agents.py

from typing import Literal, Dict, Any, List
from sqlalchemy.orm import Session
import google.generativeai as genai

from .config import settings
from . import crud, models
from .tools import (
    rag_answer_for_project,
    quick_project_summary,
    analyze_diagram_page,
)
from .rag import generate_answer_from_context

Intent = Literal["qa", "summary", "diagram", "other"]

GEMINI_TEXT_MODEL = "gemini-2.5-flash"


# ---------- Intent classification ----------

def classify_intent(question: str) -> Intent:
    """
    Heuristic + optional Gemini classification.
    """
    q = question.lower()

    diagram_keywords = [
        "one-line",
        "one line",
        "single line",
        "sld",
        "diagram",
        "schematic",
        "layout",
        "on the drawing",
        "in the drawing",
        "on the one line",
        "on the single line",
    ]
    if any(k in q for k in diagram_keywords):
        return "diagram"

    summary_keywords = [
        "summary",
        "overview",
        "high level",
        "explain this project",
        "what is this project",
        "give me an overview",
    ]
    if any(k in q for k in summary_keywords):
        return "summary"

    if not settings.GOOGLE_API_KEY:
        return "qa"

    try:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        print("[LLM DEBUG] classify_intent using model:", GEMINI_TEXT_MODEL)
        model = genai.GenerativeModel(GEMINI_TEXT_MODEL)
        prompt = (
            "You are a classifier for a solar engineering assistant. "
            "You must categorize the user's intent into one of: "
            "'qa' (question about project details), "
            "'summary' (asking for a summary or overview), "
            "'diagram' (question about the one-line, layout, or diagram), "
            "'other'.\n\n"
            f"Question: {question}\n\n"
            "Return ONLY one of: qa, summary, diagram, other."
        )
        resp = model.generate_content(prompt)
        content = (resp.text or "").strip().lower()
    except Exception:
        return "qa"

    if "diagram" in content:
        return "diagram"
    if "summary" in content:
        return "summary"
    if "qa" in content:
        return "qa"
    return "other"


# ---------- Project Q&A agent (Text RAG) ----------

def project_qa_agent(db: Session, project_id: int, question: str) -> str:
    tool_result = rag_answer_for_project(db=db, project_id=project_id, question=question)
    answer = tool_result["answer"]
    sources = tool_result.get("sources") or []

    if sources:
        citations: List[str] = []
        for s in sources:
            citations.append(
                f"Doc {s.get('document_id')} Page {s.get('page_number')}"
            )
        unique_cites = sorted(set(citations))
        answer += "\n\nSources: " + ", ".join(unique_cites)

    return answer


# ---------- Summarizer agent ----------

def project_summarizer_agent(db: Session, project_id: int, question: str) -> str:
    base_context = quick_project_summary(db=db, project_id=project_id)

    if not settings.GOOGLE_API_KEY:
        return base_context

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    print("[LLM DEBUG] summarizer using model:", GEMINI_TEXT_MODEL)
    model = genai.GenerativeModel(GEMINI_TEXT_MODEL)

    system_prompt = (
        "You are a senior electrical engineer summarizing a utility-scale solar project. "
        "You will be given some raw excerpts from project documents. "
        "Write a clear, concise summary or respond to the user's request, "
        "but only use the information provided in the context."
    )

    user_prompt = (
        f"{system_prompt}\n\n"
        f"Context excerpts:\n{base_context}\n\n"
        f"User request: {question}\n\n"
        "Write a 1–3 paragraph summary that is useful for an engineer reviewing this project."
    )

    resp = model.generate_content(user_prompt)
    return resp.text or ""


# ---------- Diagram agent ----------

def diagram_agent(
    db: Session,
    project_id: int,
    question: str,
    document_id: int | None = None,
    page_number: int = 1,
) -> str:
    if document_id is None:
        docs = (
            db.query(models.Document)
            .filter(models.Document.project_id == project_id)
            .order_by(models.Document.uploaded_at.desc())
            .all()
        )
        pdf_docs = [d for d in docs if d.file_name.lower().endswith(".pdf")]
        if not pdf_docs:
            return (
                "I couldn't find any PDF documents for this project to analyze as a diagram. "
                "Please upload a one-line or layout drawing as a PDF."
            )
        document_id = pdf_docs[0].id

    diagram_text = analyze_diagram_page(
        db=db,
        project_id=project_id,
        document_id=document_id,
        page_number=page_number,
    )

    if not settings.GOOGLE_API_KEY:
        return diagram_text

    return generate_answer_from_context(question=question, context=diagram_text)


# ---------- Orchestrator ----------

def orchestrator_agent(
    db: Session,
    project_id: int,
    question: str,
) -> Dict[str, Any]:
    project = crud.get_project(db, project_id)
    if not project:
        return {
            "answer": "Project not found.",
            "agent": "orchestrator",
            "intent": "other",
        }

    intent = classify_intent(question)

    if intent == "diagram":
        answer = diagram_agent(db=db, project_id=project_id, question=question)
        return {"answer": answer, "agent": "diagram_agent", "intent": intent}

    if intent == "summary":
        answer = project_summarizer_agent(db=db, project_id=project_id, question=question)
        return {"answer": answer, "agent": "project_summarizer_agent", "intent": intent}

    if intent == "qa":
        answer = project_qa_agent(db=db, project_id=project_id, question=question)
        return {"answer": answer, "agent": "project_qa_agent", "intent": intent}

    # Fallback: treat as QA
    answer = project_qa_agent(db=db, project_id=project_id, question=question)
    answer = (
        "I wasn't sure if this was a summary or diagram question, "
        "so I answered it as a project Q&A.\n\n" + answer
    )
    return {"answer": answer, "agent": "project_qa_agent", "intent": intent}

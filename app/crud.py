from sqlalchemy.orm import Session
from . import models, schemas


def get_projects(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Project).order_by(models.Project.created_at.desc()).offset(skip).limit(limit).all()


def get_project(db: Session, project_id: int):
    return db.query(models.Project).filter(models.Project.id == project_id).first()


def create_project(db: Session, project_in: schemas.ProjectCreate):
    db_project = models.Project(name=project_in.name, description=project_in.description)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


def get_documents_for_project(db: Session, project_id: int):
    return db.query(models.Document).filter(models.Document.project_id == project_id).order_by(models.Document.uploaded_at.desc()).all()


def create_document(db: Session, project_id: int, file_name: str, file_path: str, status: str = "ready"):
    db_doc = models.Document(
        project_id=project_id,
        file_name=file_name,
        file_path=file_path,
        status=status,
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


def get_qa_for_project(db: Session, project_id: int):
    return db.query(models.QAEntry).filter(models.QAEntry.project_id == project_id).order_by(models.QAEntry.created_at.desc()).all()


def create_qa_entry(db: Session, project_id: int, question: str, answer: str):
    db_qa = models.QAEntry(
        project_id=project_id,
        question=question,
        answer=answer,
    )
    db.add(db_qa)
    db.commit()
    db.refresh(db_qa)
    return db_qa


def create_document_chunk(
    db: Session,
    *,
    document_id: int,
    project_id: int,
    page_number: int,
    text: str,
):
    chunk = models.DocumentChunk(
        document_id=document_id,
        project_id=project_id,
        page_number=page_number,
        text=text,
    )
    db.add(chunk)
    return chunk


def get_document(db: Session, document_id: int):
    return db.query(models.Document).filter(models.Document.id == document_id).first()


def delete_document(db: Session, document_id: int) -> bool:
    doc = get_document(db, document_id)
    if not doc:
        return False

    # Delete any chunks explicitly (in case DB-level cascade isn't active)
    db.query(models.DocumentChunk).filter(
        models.DocumentChunk.document_id == document_id
    ).delete()

    db.delete(doc)
    db.commit()
    return True


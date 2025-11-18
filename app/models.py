# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    documents = relationship(
        "Document",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    qa_entries = relationship(
        "QAEntry",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    # Must match crud.create_document kwargs
    file_name = Column(String, nullable=False)    # e.g., "PPC_Narrative.pdf"
    file_path = Column(String, nullable=False)    # e.g., "uploads/1/PPC_Narrative.pdf"

    uploaded_at = Column(DateTime, server_default=func.now())
    status = Column(String, default="processing")  # "processing" | "ready" | "error"

    # Relationships
    project = relationship("Project", back_populates="documents")
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)

    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="chunks")
    document = relationship("Document", back_populates="chunks")


class QAEntry(Base):
    __tablename__ = "qa_entries"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    project = relationship("Project", back_populates="qa_entries")

from datetime import datetime
from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    description: str | None = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class Document(BaseModel):
    id: int
    project_id: int
    file_name: str
    file_path: str
    uploaded_at: datetime
    status: str

    class Config:
        from_attributes = True


class QAEntry(BaseModel):
    id: int
    project_id: int
    question: str
    answer: str
    created_at: datetime

    class Config:
        from_attributes = True


class QuestionCreate(BaseModel):
    question: str

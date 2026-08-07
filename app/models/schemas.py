# app/models/schemas.py

from pydantic import BaseModel


class RepoCreateRequest(BaseModel):
    owner: str
    repo: str


class MessageRequest(BaseModel):
    question: str

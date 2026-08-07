# app/main.py

from fastapi import FastAPI
from app.routes import repos, conversations, auth

app = FastAPI(title="RAG GitHub Bot")
app.include_router(repos.router)
app.include_router(conversations.router)
app.include_router(auth.router)

# app/routes/conversations.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import MessageRequest
from app.query.generate import stream_llm_response
from app.query.prompts import build_prompt
from app.storage import db
from app.storage.vector_store import search

router = APIRouter(tags=["conversations"])


@router.post("/repos/{repo_id}/conversations")
def create_conversation(repo_id: str):
    repo = db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    conversation_id = db.create_conversation(repo_id)
    return {"conversation_id": conversation_id, "repo_id": repo_id}


@router.get("/conversations")
def list_conversations(repo_id: str | None = None):
    return db.list_conversations(repo_id)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {**conversation, "messages": db.get_messages(conversation_id)}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    conversation = db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete_conversation(conversation_id)
    return {"conversation_id": conversation_id, "deleted": True}


@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, payload: MessageRequest):
    conversation = db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Repeat the "is the repo actually ready" guard here even though Phase 1
    # already checks it on ingestion — a conversation can point at a repo
    # that's still pending or failed a re-sync, and silently querying an
    # incomplete index would return a misleading answer instead of an
    # honest error.
    repo = db.get_repo(conversation["repo_id"])
    if not repo or repo["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Repo is not ready for queries (status: {repo['status'] if repo else 'missing'})",
        )

    question = payload.question
    history = db.get_recent_messages(conversation_id)
    chunks = search(question, repo_id=conversation["repo_id"])

    # Save the user's message before generating — if the LLM call fails
    # partway through, the conversation still has an accurate record of
    # what was actually asked.
    db.add_message(conversation_id, role="user", content=question)

    prompt = build_prompt(question, chunks, history)
    sources = [{"path": c["path"], "chunk_index": c["chunk_index"]} for c in chunks]

    def stream_and_persist():
        # Once StreamingResponse is returned, nothing after this function's
        # `return` ever runs — FastAPI just iterates this generator. So
        # persisting the final assistant message has to happen in here,
        # after the yield loop is exhausted, not after the route returns.
        full_text = ""
        for token in stream_llm_response(prompt):
            full_text += token
            yield token
        db.add_message(conversation_id, role="assistant", content=full_text, sources=sources)

    return StreamingResponse(stream_and_persist(), media_type="text/event-stream")

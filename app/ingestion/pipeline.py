# app/ingestion/pipeline.py — the orchestrator the background task runs

from app.ingestion.github_fetch import fetch_repo_files
from app.ingestion.filters import filter_files
from app.ingestion.chunker import chunk_files
from app.ingestion.embedder import embed_chunks
from app.storage.vector_store import add_chunks, delete_repo as delete_repo_vectors
from app.storage import db
from app.config import GITHUB_TOKEN


def ingest_repo(repo_id: str, owner: str, repo_name: str) -> None:
    """
    Runs as a background task after POST /repos (fresh ingest) or
    PATCH /repos/{repo_id} (re-sync) already responded. Wrapped in
    try/except specifically because exceptions in a background task never
    reach the client — this is what lets GET /repos/{repo_id} report a
    real failure instead of "pending" forever.
    """
    try:
        # Prefer a connected OAuth token (lets private repos the user
        # authorized get ingested) over the .env PAT, which was only ever
        # there to raise the unauthenticated rate limit. Resolved fresh on
        # every call, not at import time, since OAuth can get connected
        # after the app has already started.
        token = db.get_github_token() or GITHUB_TOKEN
        raw_files = fetch_repo_files(owner, repo_name, token)
        filtered = filter_files(raw_files)
        chunks = chunk_files(filtered, repo_id=repo_id)
        embedded = embed_chunks(chunks)

        # Clear any vectors already indexed under this repo_id before adding
        # the fresh ones — a no-op on a first-ever ingest, but required for
        # re-sync so chunks from files that were edited/deleted since the
        # last index don't linger alongside the new ones.
        delete_repo_vectors(repo_id)
        add_chunks(embedded)

        db.mark_completed(repo_id, file_count=len(filtered), chunk_count=len(chunks))

    except Exception as e:
        db.mark_failed(repo_id, error_message=str(e))

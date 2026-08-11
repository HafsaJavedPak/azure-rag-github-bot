# app/ingestion/pipeline.py — the orchestrator the background task runs

from app.ingestion.github_fetch import (
    fetch_repo_files,
    fetch_file_content,
    get_changed_files,
    get_head_sha,
)
from app.ingestion.filters import filter_files
from app.ingestion.chunker import chunk_files
from app.ingestion.embedder import embed_chunks
from app.storage.vector_store import (
    add_chunks,
    delete_chunks_by_path,
    delete_repo as delete_repo_vectors,
    get_repo_stats,
)
from app.storage import db
from app.config import GITHUB_TOKEN


def _resolve_token() -> str:
    """Prefer a connected OAuth token (lets private repos the user
    authorized get ingested) over the .env PAT, which was only ever there
    to raise the unauthenticated rate limit. Resolved fresh on every call,
    not at import time, since OAuth can get connected after the app has
    already started."""
    return db.get_github_token() or GITHUB_TOKEN


def ingest_repo(repo_id: str, owner: str, repo_name: str) -> None:
    """
    Full ingest — runs as a background task after POST /repos, and as the
    fallback path from resync_repo_incremental() below whenever a diff-based
    re-sync isn't possible. Wrapped in try/except specifically because
    exceptions in a background task never reach the client — this is what
    lets GET /repos/{repo_id} report a real failure instead of "pending"
    forever.
    """
    try:
        token = _resolve_token()
        head_sha = get_head_sha(owner, repo_name, token)
        raw_files = fetch_repo_files(owner, repo_name, token)
        filtered = filter_files(raw_files)
        chunks = chunk_files(filtered, repo_id=repo_id)
        embedded = embed_chunks(chunks)

        # Clear any vectors already indexed under this repo_id before adding
        # the fresh ones — a no-op on a first-ever ingest, but required when
        # this runs as resync_repo_incremental's fallback, so chunks from
        # files edited/deleted since the last index don't linger.
        delete_repo_vectors(repo_id)
        add_chunks(embedded)

        db.mark_completed(
            repo_id, file_count=len(filtered), chunk_count=len(chunks), last_indexed_sha=head_sha
        )

    except Exception as e:
        db.mark_failed(repo_id, error_message=str(e))


def resync_repo_incremental(repo_id: str, owner: str, repo_name: str) -> None:
    """
    Diff-based re-sync — only fetches, re-chunks, and re-embeds files that
    actually changed since the last successful sync, instead of
    re-processing the whole repo. Always falls back to a full ingest_repo()
    run rather than introducing a new way to fail: no prior SHA on record,
    a diff too large to trust as complete, or a base commit GitHub can no
    longer find (force-push/rebase) all degrade to "just do what POST does".
    """
    try:
        token = _resolve_token()
        repo = db.get_repo(repo_id)
        base_sha = repo.get("last_indexed_sha") if repo else None

        if not base_sha:
            return ingest_repo(repo_id, owner, repo_name)

        head_sha = get_head_sha(owner, repo_name, token)

        if head_sha == base_sha:
            # Nothing changed since last sync — no work needed, just record
            # that a sync ran and confirm the counts are still accurate.
            stats = get_repo_stats(repo_id)
            db.mark_completed(
                repo_id,
                file_count=stats["file_count"],
                chunk_count=stats["chunk_count"],
                last_indexed_sha=head_sha,
            )
            return

        changed_files = get_changed_files(owner, repo_name, token, base_sha, head_sha)

        if changed_files is None:
            return ingest_repo(repo_id, owner, repo_name)

        for entry in changed_files:
            path = entry["path"]
            status = entry["status"]
            previous_path = entry.get("previous_path")

            # Clear old vectors for whichever path(s) this entry touches —
            # covers modified/removed/renamed uniformly. A no-op if that
            # path was never actually indexed (e.g. filtered out before).
            if previous_path:
                delete_chunks_by_path(repo_id, previous_path)
            delete_chunks_by_path(repo_id, path)

            if status == "removed":
                continue

            content = fetch_file_content(owner, repo_name, token, path, head_sha)
            filtered = filter_files([{"path": path, "content": content}])
            if not filtered:
                continue  # excluded by the same rules a fresh ingest applies

            chunks = chunk_files(filtered, repo_id=repo_id)
            embedded = embed_chunks(chunks)
            add_chunks(embedded)

        stats = get_repo_stats(repo_id)
        db.mark_completed(
            repo_id,
            file_count=stats["file_count"],
            chunk_count=stats["chunk_count"],
            last_indexed_sha=head_sha,
        )

    except Exception as e:
        db.mark_failed(repo_id, error_message=str(e))

# app/routes/repos.py

from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.models.schemas import RepoCreateRequest
from app.ingestion.pipeline import ingest_repo
from app.storage import db
from app.storage.vector_store import delete_repo as delete_repo_vectors

router = APIRouter(prefix="/repos", tags=["repos"])


@router.post("/")
def create_repo(payload: RepoCreateRequest, background_tasks: BackgroundTasks):
    repo_id = f"{payload.owner}_{payload.repo}"

    db.create_repo(repo_id=repo_id, name=payload.repo, owner=payload.owner)
    background_tasks.add_task(ingest_repo, repo_id, payload.owner, payload.repo)

    # returns immediately — status is "pending", ingestion keeps running after this
    return {"repo_id": repo_id, "status": "pending"}


@router.get("/")
def list_repos():
    return db.list_repos()


@router.get("/{repo_id}")
def get_repo(repo_id: str):
    repo = db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.patch("/{repo_id}")
def resync_repo(repo_id: str, background_tasks: BackgroundTasks):
    repo = db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Simplest version, per plan: just re-run the whole ingestion pipeline
    # for this repo rather than diffing changed files — same background-task
    # shape as POST /repos, but reusing the existing repo_id (and owner/name
    # already on file) so any conversations pointed at it stay valid.
    db.mark_pending(repo_id)
    background_tasks.add_task(ingest_repo, repo_id, repo["owner"], repo["name"])

    return {"repo_id": repo_id, "status": "pending"}


@router.delete("/{repo_id}")
def delete_repo(repo_id: str):
    repo = db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    delete_repo_vectors(repo_id)   # clean the vector store first
    db.delete_repo(repo_id)         # then the metadata row
    return {"repo_id": repo_id, "deleted": True}

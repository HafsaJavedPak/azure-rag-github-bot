import base64
import io
import tarfile
from urllib.parse import quote

import requests

from app.ingestion.filters import BINARY_PLACEHOLDER


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def fetch_repo_files(owner: str, repo: str, token: str) -> list[dict]:
    headers = _headers(token)

    # 1. Get default branch
    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    repo_resp = requests.get(repo_url, headers=headers)
    repo_resp.raise_for_status()
    default_branch = repo_resp.json().get("default_branch", "main")

    repo_size_kb = repo_resp.json().get("size", 0)
    if repo_size_kb > 500_000:  # ~500 MB, adjust as you like
        raise ValueError(f"Repo too large to ingest ({repo_size_kb} KB) — size limit exceeded")

    # 2. Download the whole repo as a tarball — one request, regardless of file count
    archive_url = f"{repo_url}/tarball/{default_branch}"
    archive_resp = requests.get(archive_url, headers=headers)
    archive_resp.raise_for_status()

    files = []

    # 3. Read the tarball straight from memory, no disk write
    with tarfile.open(fileobj=io.BytesIO(archive_resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue  # skip directory entries

            # GitHub wraps everything in "owner-repo-<sha>/" — strip that prefix
            path_parts = member.name.split("/", 1)
            if len(path_parts) < 2:
                continue
            relative_path = path_parts[1]

            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            raw_bytes = extracted.read()

            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = BINARY_PLACEHOLDER

            files.append({
                "path": relative_path,
                "content": content
            })

    return files


def get_head_sha(owner: str, repo: str, token: str, branch: str | None = None) -> str:
    """
    Returns the current HEAD commit SHA of the given branch (the repo's
    default branch if none given). Used to detect whether anything has
    changed since the last sync, and as the "new" endpoint of a diff.
    """
    headers = _headers(token)

    if branch is None:
        repo_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
        repo_resp.raise_for_status()
        branch = repo_resp.json().get("default_branch", "main")

    branch_resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}", headers=headers
    )
    branch_resp.raise_for_status()
    return branch_resp.json()["commit"]["sha"]


def get_changed_files(
    owner: str, repo: str, token: str, base_sha: str, head_sha: str
) -> list[dict] | None:
    """
    Uses GitHub's compare API to list every file that changed between two
    commits — status is "added", "modified", "removed", "renamed", etc.

    Returns None (rather than raising) when the diff can't be trusted as
    complete — base_sha no longer reachable after a force-push/rebase, or
    the file list looks like it hit GitHub's cap on the compare endpoint —
    so the caller can fall back to a full re-ingest instead of silently
    acting on a partial diff.
    """
    headers = _headers(token)
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/compare/{base_sha}...{head_sha}",
        headers=headers,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    files = resp.json().get("files", [])

    if len(files) >= 300:
        return None

    return [
        {
            "path": f["filename"],
            "status": f["status"],
            "previous_path": f.get("previous_filename"),
        }
        for f in files
    ]


def fetch_file_content(owner: str, repo: str, token: str, path: str, ref: str) -> str:
    """
    Fetches one file's content at a specific commit — used by incremental
    re-sync to pull just the files that changed, instead of re-downloading
    the whole repo. Mirrors fetch_repo_files' binary handling so downstream
    filtering behaves identically no matter which path fetched the content.
    """
    headers = _headers(token)
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(path, safe='/')}",
        headers=headers,
        params={"ref": ref},
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        raw_bytes = base64.b64decode(data["content"])
        return raw_bytes.decode("utf-8")
    except (UnicodeDecodeError, KeyError):
        return BINARY_PLACEHOLDER

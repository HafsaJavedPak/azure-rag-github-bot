import requests
import tarfile
import io

def fetch_repo_files(owner: str, repo: str, token: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

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
                content = "<binary or non-UTF-8 content>"

            files.append({
                "path": relative_path,
                "content": content
            })

    return files

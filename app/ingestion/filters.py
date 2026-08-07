import os

EXCLUDED_DIRS = {
    "node_modules", ".git", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", "vendor", "target", "env"
}

EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", "poetry.lock",
    "Pipfile.lock", "composer.lock", "Cargo.lock"
}

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt",
    ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".sh", ".sql", ".html", ".css", ".scss"
}

BINARY_PLACEHOLDER = "<binary or non-UTF-8 content>"


def filter_files(files: list[dict]) -> list[dict]:
    filtered = []

    for f in files:
        path = f["path"]
        content = f["content"]

        # cheapest check first — already computed by fetch_repo_files
        if content == BINARY_PLACEHOLDER:
            continue

        path_parts = path.split("/")

        # directory exclusion
        if any(part in EXCLUDED_DIRS for part in path_parts):
            continue

        filename = path_parts[-1]

        # exact filename exclusion (lockfiles etc.)
        if filename in EXCLUDED_FILENAMES:
            continue

        # allowlist extension check
        ext = os.path.splitext(filename)[1]
        if ext not in ALLOWED_EXTENSIONS:
            continue

        # skip empty files
        if not content.strip():
            continue

        filtered.append(f)

    return filtered

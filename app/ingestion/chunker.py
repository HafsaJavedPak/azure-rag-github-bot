# app/ingestion/chunker.py

from app.ingestion import ast_chunker
from app.ingestion.text_chunker import split_text


def chunk_file(path: str, content: str, chunk_size: int = 600, overlap: int = 100) -> list[dict]:
    """
    Split a single file's content into chunks ready for embedding.

    Tries AST-aware chunking first (app/ingestion/ast_chunker.py) — whole
    functions/classes as chunks, for the languages it has a grammar wired
    up for. Falls back to the plain fixed-size character splitter
    (app/ingestion/text_chunker.py) for anything else: unsupported
    languages, non-code files like README/YAML/JSON, or a file that fails
    to parse. This keeps the fallback behavior identical to what every
    file got before AST chunking existed — no regression for the files
    that don't have a grammar yet.

    Args:
        path: file's path within the repo — carried as metadata for later
              filtering (by repo_id/file) and for deletion when a repo is
              removed or a file changes.
        content: full text content of the file.
        chunk_size: target chunk size in characters (also the budget AST
              chunking uses to decide whether a node is "oversized").
        overlap: characters shared between consecutive chunks, wherever
              the character splitter (not AST boundaries) is doing the
              splitting.

    Returns:
        List of chunk dicts: {"path", "chunk_index", "content"}.
        (repo_id gets attached one level up, in chunk_files — this function
        doesn't know which repo it belongs to.)
    """
    ast_result = ast_chunker.chunk_code_file(path, content, chunk_size, overlap)
    if ast_result is not None:
        return ast_result

    raw_chunks = split_text(content, chunk_size, overlap)
    return [
        {
            "path": path,
            "chunk_index": i,
            "content": chunk_text,
        }
        for i, chunk_text in enumerate(raw_chunks)
    ]


def chunk_files(files: list[dict], repo_id: str, chunk_size: int = 600, overlap: int = 100) -> list[dict]:
    """
    Run chunk_file over every file in a filtered file list (output of
    filter_files), attaching repo_id to every resulting chunk.

    repo_id is what makes the "shared collection, filter at query time"
    design work later — every chunk needs to carry it so the vector store
    can filter to one repo on query, or delete every chunk for a repo on
    DELETE /repos/{repo_id}.
    """
    all_chunks = []
    for f in files:
        for chunk in chunk_file(f["path"], f["content"], chunk_size, overlap):
            chunk["repo_id"] = repo_id
            all_chunks.append(chunk)
    return all_chunks

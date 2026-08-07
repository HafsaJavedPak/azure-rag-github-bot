# app/ingestion/chunker.py

from langchain_text_splitters import RecursiveCharacterTextSplitter
# pip install langchain-text-splitters
# (lighter-weight than pulling in all of `langchain` — just the splitter)


def chunk_file(path: str, content: str, chunk_size: int = 600, overlap: int = 100) -> list[dict]:
    """
    Split a single file's content into overlapping chunks ready for embedding.

    Sizing rationale (settled earlier):
    - chunk_size=600 chars approximates staying safely under the embedding
      model's 256-token limit, using ~4 chars/token as a rough guide for
      English text — with headroom built in, since code tends to tokenize
      denser than prose (lots of short symbol/operator tokens).
    - overlap=100 chars (~17% of chunk_size) keeps content that straddles a
      boundary intact in at least one chunk, without creating so much
      duplication that top-k retrieval fills up with near-identical chunks.

    Args:
        path: file's path within the repo — carried as metadata for later
              filtering (by repo_id/file) and for deletion when a repo is removed.
        content: full text content of the file.
        chunk_size: target chunk size in characters.
        overlap: characters shared between consecutive chunks.

    Returns:
        List of chunk dicts: {"path", "chunk_index", "content"}.
        (repo_id gets attached one level up, in chunk_files — this function
        doesn't know which repo it belongs to.)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        # Separator priority: try the "nicest" break point first, only fall
        # back to a raw character cut if nothing better fits. This is what
        # keeps a chunk boundary from slicing through the middle of a
        # function or sentence when it can be avoided.
        separators=["\n\n", "\n", " ", ""],
    )

    raw_chunks = splitter.split_text(content)  # flat list of strings, no metadata yet

    return [
        {
            "path": path,
            "chunk_index": i,       # position within the file — useful for debugging/ordering
            "content": chunk_text,  # the actual text that gets embedded
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

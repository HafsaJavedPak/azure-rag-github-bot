# app/ingestion/embedder.py

from sentence_transformers import SentenceTransformer

# Loaded once, at import time — top-level code in a module runs exactly once,
# the first time it's imported anywhere. Every call to embed_chunks() below
# reuses this same in-memory model instead of reloading it from disk each time.
model = SentenceTransformer("all-MiniLM-L6-v2")


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Takes the output of chunk_files() (list of dicts with repo_id, path,
    chunk_index, content) and returns the same dicts with an added
    "embedding" field — the vector for that chunk's content.

    Batches all chunk texts into a single .encode() call rather than
    looping and calling it once per chunk — same "fewer round-trips through
    the expensive part" logic as the tarball fetch.
    """
    texts = [chunk["content"] for chunk in chunks]

    vectors = model.encode(texts)  # shape: (num_chunks, 384) — one row per chunk, in the same order as `texts`

    embedded_chunks = []
    for chunk, vector in zip(chunks, vectors):
        embedded_chunks.append({
            **chunk,                        # repo_id, path, chunk_index, content — carried through untouched
            "embedding": vector.tolist(),   # numpy array -> plain list, easier to pass around/store as JSON
        })

    return embedded_chunks

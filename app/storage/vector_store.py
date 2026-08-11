# app/storage/vector_store.py

import chromadb
from app.ingestion.embedder import model  # reuse the already-loaded model — no reloading here

# PersistentClient writes to disk, so the index survives an app restart —
# unlike an in-memory client, which forgets everything when the process ends.
client = chromadb.PersistentClient(path="./chroma_data")

# get_or_create so this works whether the collection already exists from a
# previous run, or needs to be created fresh on first launch.
collection = client.get_or_create_collection(name="repo_chunks")


def add_chunks(chunks: list[dict]) -> None:
    """
    Takes the direct output of embed_chunks() and stores it in Chroma.
    Builds the four parallel lists Chroma's .add() needs internally, so
    the caller never has to reshape data themselves.
    """
    ids = [f"{c['repo_id']}::{c['path']}::{c['chunk_index']}" for c in chunks]
    embeddings = [c["embedding"] for c in chunks]
    documents = [c["content"] for c in chunks]
    metadatas = [
        {"repo_id": c["repo_id"], "path": c["path"], "chunk_index": c["chunk_index"]}
        for c in chunks
    ]

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def search(question: str, repo_id: str | None = None, n_results: int = 5) -> list[dict]:
    """
    Embeds the question internally, then searches. repo_id=None searches
    every repo (the mechanism the deferred cross-repo feature reuses later);
    repo_id="some-repo" filters to just that repo — your single-repo case.
    """
    query_vector = model.encode([question])[0].tolist()
    where_filter = {"repo_id": repo_id} if repo_id else None

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        where=where_filter,
    )

    # Chroma nests results one level deep (per query) — zip back into one
    # dict per match for easier use downstream.
    return [
        {
            "content": doc,
            "repo_id": meta["repo_id"],
            "path": meta["path"],
            "chunk_index": meta["chunk_index"],
            "distance": distance,
        }
        for doc, meta, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]


def delete_repo(repo_id: str) -> None:
    """Removes every chunk belonging to a repo in one call via metadata filter."""
    collection.delete(where={"repo_id": repo_id})


def delete_chunks_by_path(repo_id: str, path: str) -> None:
    """The surgical counterpart to delete_repo() — removes just the vectors
    for one file within a repo, used by incremental re-sync so unrelated
    files' vectors are never touched. A no-op if that path was never
    actually indexed (e.g. it was previously filtered out)."""
    collection.delete(where={"$and": [{"repo_id": repo_id}, {"path": path}]})


def get_repo_stats(repo_id: str) -> dict:
    """Derives current file_count/chunk_count straight from what's actually
    stored, rather than incrementally maintaining counters through a series
    of per-file adds/deletes — avoids drift if an incremental sync fails
    partway through."""
    results = collection.get(where={"repo_id": repo_id}, limit=100000)
    paths = {meta["path"] for meta in results["metadatas"]}
    return {"file_count": len(paths), "chunk_count": len(results["ids"])}

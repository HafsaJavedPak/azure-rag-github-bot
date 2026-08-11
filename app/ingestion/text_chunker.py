# app/ingestion/text_chunker.py

from langchain_text_splitters import RecursiveCharacterTextSplitter
# pip install langchain-text-splitters
# (lighter-weight than pulling in all of `langchain` — just the splitter)


def split_text(content: str, chunk_size: int = 600, overlap: int = 100) -> list[str]:
    """
    Plain fixed-size recursive splitter — the fallback chunking strategy
    used by chunker.py for non-code files (markdown, YAML, JSON, plain
    text) and for any code file whose language doesn't have an AST grammar
    wired up in ast_chunker.py. Also reused by ast_chunker.py itself, to
    sub-split a single function/class node too large to embed as one chunk,
    and to sweep up top-level text that sits outside any chunkable node
    (imports, module-level constants).

    Sizing rationale (settled earlier):
    - chunk_size=600 chars approximates staying safely under the embedding
      model's 256-token limit, using ~4 chars/token as a rough guide for
      English text — with headroom built in, since code tends to tokenize
      denser than prose (lots of short symbol/operator tokens).
    - overlap=100 chars (~17% of chunk_size) keeps content that straddles a
      boundary intact in at least one chunk, without creating so much
      duplication that top-k retrieval fills up with near-identical chunks.

    Returns a flat list of chunk strings — no path/chunk_index attached,
    that's the caller's job (both chunker.py and ast_chunker.py attach it
    differently depending on context).
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
    return splitter.split_text(content)

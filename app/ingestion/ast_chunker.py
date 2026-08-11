# app/ingestion/ast_chunker.py

import os

import tree_sitter_go as tsgo
import tree_sitter_javascript as tsjavascript
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from app.ingestion.text_chunker import split_text

# Each entry: extension -> (Language, set of top-level node type names
# worth treating as one whole chunk). Node-type names are grammar-specific
# and were confirmed empirically against each parser, not guessed from
# docs — e.g. Python wraps a decorated function/class in
# "decorated_definition" (whole span already includes the decorator, no
# need to unwrap it), and TypeScript wraps an exported declaration in
# "export_statement" the same way.
_LANGUAGES = {
    ".py": (
        Language(tspython.language()),
        {"function_definition", "class_definition", "decorated_definition"},
    ),
    ".js": (
        Language(tsjavascript.language()),
        {"function_declaration", "class_declaration", "lexical_declaration"},
    ),
    ".jsx": (
        Language(tsjavascript.language()),
        {"function_declaration", "class_declaration", "lexical_declaration"},
    ),
    ".ts": (
        Language(tsts.language_typescript()),
        {"function_declaration", "class_declaration", "lexical_declaration", "export_statement"},
    ),
    ".tsx": (
        Language(tsts.language_tsx()),
        {"function_declaration", "class_declaration", "lexical_declaration", "export_statement"},
    ),
    ".go": (
        Language(tsgo.language()),
        {"function_declaration", "method_declaration", "type_declaration"},
    ),
}

# A top-level node whose own text is more than this many chunk_sizes long
# gets sub-split instead of kept whole — "never split unless truly
# necessary" rather than "never split at all", since the embedding model
# still has a token limit a single giant function could blow past.
_OVERSIZED_MULTIPLIER = 2


def chunk_code_file(
    path: str, content: str, chunk_size: int = 600, overlap: int = 100
) -> list[dict] | None:
    """
    AST-aware chunking for a supported language: each function/class/etc.
    becomes one whole chunk wherever possible, instead of an arbitrary
    character cut that can slice through the middle of a function.

    Returns None — not an empty list — when this path's extension has no
    grammar wired up, or when parsing the content fails outright (a syntax
    error, or any other parse-time exception). Either way, that's the
    signal to chunker.chunk_file() that it should fall back to the plain
    character splitter instead: a None here is never treated as "this file
    has no chunks", only as "AST chunking doesn't apply here".
    """
    ext = os.path.splitext(path)[1]
    if ext not in _LANGUAGES:
        return None

    language, chunkable_types = _LANGUAGES[ext]

    try:
        parser = Parser(language)
        source_bytes = content.encode("utf-8")
        tree = parser.parse(source_bytes)
    except Exception:
        return None

    chunks: list[str] = []
    leftover_start = 0

    def flush_leftover(end_byte: int) -> None:
        # Sweeps any top-level text between chunkable nodes (imports,
        # module-level constants, comments, blank lines) into its own
        # chunk(s) via the plain splitter, so nothing in the file is
        # silently dropped just because it wasn't a function or class.
        nonlocal leftover_start
        segment = source_bytes[leftover_start:end_byte].decode("utf-8", errors="ignore").strip()
        if segment:
            chunks.extend(split_text(segment, chunk_size, overlap))
        leftover_start = end_byte

    for node in tree.root_node.children:
        if node.type not in chunkable_types:
            continue

        flush_leftover(node.start_byte)

        node_text = source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="ignore"
        )

        if len(node_text) > chunk_size * _OVERSIZED_MULTIPLIER:
            chunks.extend(split_text(node_text, chunk_size, overlap))
        else:
            chunks.append(node_text)

        leftover_start = node.end_byte

    flush_leftover(len(source_bytes))

    return [
        {"path": path, "chunk_index": i, "content": chunk_text}
        for i, chunk_text in enumerate(chunks)
    ]

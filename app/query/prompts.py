# app/query/prompts.py

HISTORY_LIMIT = 6  # last N messages (~3 user/assistant pairs) fed into the prompt


def build_prompt(question: str, chunks: list[dict], history: list[dict] | None = None) -> str:
    """
    Shapes retrieval chunks + recent conversation history + the current
    question into one prompt string for the LLM.

    Pure text-shaping, no API calls — keeps this file's only job "build the
    right string", separate from generate.py's job of "send it and stream
    back a response".

    Args:
        question: the current user question.
        chunks: output of vector_store.search() — dicts with at least
            "path" and "content".
        history: prior messages in the conversation, oldest first — dicts
            with "role" ("user"/"assistant") and "content". Only the last
            HISTORY_LIMIT are used, sliced here rather than trusted from
            the caller, so this function is the one place that owns the
            "how much history fits in a prompt" policy.

    Returns:
        The full prompt text, ready to hand to stream_llm_response().
    """
    parts = []

    if history:
        parts.append("Conversation so far:")
        for message in history[-HISTORY_LIMIT:]:
            role = "User" if message["role"] == "user" else "Assistant"
            parts.append(f"{role}: {message['content']}")
        parts.append("")

    parts.append("Context from the repo:")
    for chunk in chunks:
        parts.append(f"[{chunk['path']}]")
        parts.append(chunk["content"])
    parts.append("")

    parts.append(f"Question: {question}")
    parts.append("Answer using only the context above. If it doesn't contain the answer, say so.")

    return "\n".join(parts)

# app/query/generate.py

from typing import Generator

from google import genai
from app.config import GEMINI_API_KEY

# Loaded once, at import time — same pattern as the embedding model in
# embedder.py, so every call reuses this client instead of building a new
# one (and re-reading the API key) per request.
client = genai.Client(api_key=GEMINI_API_KEY)


def stream_llm_response(prompt: str) -> Generator[str, None, None]:
    """
    Sends the prompt to the LLM and yields each text fragment as it
    arrives, instead of blocking until the full answer is generated.

    A generator, not a plain function returning a string — this is the
    mechanism StreamingResponse needs to forward pieces to the client as
    they're produced. One function covers both use cases: consuming it
    directly gives streaming, "".join(stream_llm_response(prompt)) gives
    the full string if streaming isn't needed somewhere.
    """
    stream = client.models.generate_content_stream(
        model="gemini-flash-latest",
        contents=prompt,
    )

    for chunk in stream:
        if chunk.text:
            yield chunk.text

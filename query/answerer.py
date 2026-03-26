"""
Answer generation using Ollama chat.

Two modes:
  qa        — direct question answering with citations
  writing   — bullet-point synthesis for a thesis section
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHAT_MODEL


_SYSTEM_PROMPT = """You are a research assistant for Kris, a postgraduate student at Newcastle University Business School writing a thesis on: "Does social connectedness (measured by Facebook's Social Connectedness Index) affect post-M&A ESG performance?"

IMPORTANT RULES:
1. Answer ONLY using the provided research materials below. Never use your own knowledge to fill gaps.
2. Always cite sources using [N] notation corresponding to the numbered list.
3. If the provided materials do not contain enough information to answer, say: "I couldn't find this in your indexed materials. Try re-indexing or searching with different keywords."
4. Be concise and academic in tone.
5. When quoting directly, use quotation marks and cite the source."""

_WRITING_SYSTEM = """You are a research assistant helping Kris write his thesis on the impact of social connectedness (Facebook SCI) on post-M&A ESG performance.

Using ONLY the provided research materials, produce a structured synthesis for a thesis section. Format your response as:
- **Key themes** (3-5 bullet points summarising what the literature says)
- **Methodological approaches** (how papers study this topic)
- **Research gaps** (what is missing or contradictory)
- **Suggested citations** (list papers most relevant to cite here)

Cite using [N] notation. Only use the provided materials."""


def _build_context(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        author   = c.get("author", "Unknown")
        year     = c.get("year", "")
        label    = c.get("label", "Document")
        filename = c.get("filename", "")
        author_str = f"{author} ({year})" if year else author
        lines.append(
            f"[{i}] Source: {author_str} | Type: {label} | File: {filename}\n"
            f"    {c['text'][:800]}"
        )
    return "\n\n".join(lines)


def _stream_tokens(stream):
    """
    Yield clean text from an Ollama stream, hiding <think>...</think> blocks
    that qwen3 models produce internally.
    """
    in_think = False
    pending = ""  # buffer for partial tag detection across chunks

    for chunk in stream:
        pending += chunk["message"]["content"]

        output = ""
        while pending:
            if not in_think:
                idx = pending.find("<think>")
                if idx == -1:
                    # No think tag — safe to yield all but last 6 chars
                    # (keeps enough to detect a split "<think>" across chunks)
                    safe = max(0, len(pending) - 6)
                    output += pending[:safe]
                    pending = pending[safe:]
                    break
                else:
                    output += pending[:idx]
                    pending = pending[idx + len("<think>"):]
                    in_think = True
            else:
                idx = pending.find("</think>")
                if idx == -1:
                    pending = ""  # discard thinking content
                    break
                else:
                    pending = pending[idx + len("</think>"):]
                    in_think = False

        if output:
            yield output

    # Flush remainder
    if pending and not in_think:
        yield pending


def answer(question: str, chunks: list[dict]) -> str:
    """Generate a cited answer to a question from retrieved chunks."""
    import ollama

    context = _build_context(chunks)
    user_msg = (
        f"Research materials:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer (with [N] citations):"
    )

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    return response["message"]["content"].strip()


def answer_stream(question: str, chunks: list[dict]):
    """Streaming version of answer() — yields tokens as Ollama generates them."""
    import ollama

    context = _build_context(chunks)
    user_msg = (
        f"Research materials:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer (with [N] citations):"
    )

    stream = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        stream=True,
    )
    yield from _stream_tokens(stream)


def synthesize(topic: str, chunks: list[dict]) -> str:
    """Generate a writing synthesis for a thesis section on `topic`."""
    import ollama

    context = _build_context(chunks)
    user_msg = (
        f"Research materials:\n\n{context}\n\n"
        f"I am writing a thesis section on: {topic}\n\n"
        "Produce a structured synthesis using the materials above."
    )

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _WRITING_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
    )
    return response["message"]["content"].strip()


def synthesize_stream(topic: str, chunks: list[dict]):
    """Streaming version of synthesize() — yields tokens as Ollama generates them."""
    import ollama

    context = _build_context(chunks)
    user_msg = (
        f"Research materials:\n\n{context}\n\n"
        f"I am writing a thesis section on: {topic}\n\n"
        "Produce a structured synthesis using the materials above."
    )

    stream = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _WRITING_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        stream=True,
    )
    yield from _stream_tokens(stream)

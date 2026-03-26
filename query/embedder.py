"""
Ollama embeddings using nomic-embed-text.
"""
import time
from pathlib import Path
from typing import Optional
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EMBED_MODEL, OLLAMA_BASE_URL

_cache: dict[str, list[float]] = {}


_MAX_EMBED_CHARS = 6000  # safety truncation — nomic-embed-text context limit

def _ollama_embed(text: str) -> list[float]:
    import ollama
    response = ollama.embeddings(model=EMBED_MODEL, prompt=text[:_MAX_EMBED_CHARS])
    return response["embedding"]


def embed_single(text: str, use_cache: bool = True) -> list[float]:
    """Embed one text string. Results are cached in memory."""
    if use_cache and text in _cache:
        return _cache[text]
    vec = _ollama_embed(text)
    if use_cache:
        _cache[text] = vec
    return vec


def embed_batch(texts: list[str], batch_size: int = 8) -> list[list[float]]:
    """Embed a list of texts in batches. No caching (ingestion use)."""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        for text in batch:
            vec = _ollama_embed(text)
            results.append(vec)
        if i + batch_size < len(texts):
            time.sleep(0.1)   # small pause between batches
    return results


def check_ollama_running() -> bool:
    """Return True if Ollama is reachable."""
    try:
        import ollama
        ollama.list()
        return True
    except Exception:
        return False


def ensure_model_available():
    """Pull embed model if not yet downloaded."""
    import ollama
    try:
        models = [m.model for m in ollama.list().models]
        if not any(EMBED_MODEL in m for m in models):
            print(f"Pulling embedding model '{EMBED_MODEL}'...")
            ollama.pull(EMBED_MODEL)
            print("Done.")
    except Exception as e:
        raise RuntimeError(
            f"Could not check/pull Ollama model '{EMBED_MODEL}': {e}\n"
            "Make sure Ollama is running (open the Ollama app or run 'ollama serve')."
        )

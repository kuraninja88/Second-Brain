"""
ChromaDB vector store wrapper.
Single collection; source type and theme stored as metadata for filtering.
"""
from pathlib import Path
from typing import Optional
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_DIR, COLLECTION_NAME

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    import chromadb
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def add_chunks(
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict],
):
    col = _get_collection()
    # ChromaDB metadata values must be str/int/float/bool
    clean_meta = []
    for m in metadatas:
        clean_meta.append({k: (str(v) if v is not None else "") for k, v in m.items()})
    col.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=clean_meta)


def query(
    query_embedding: list[float],
    n_results: int = 8,
    where: Optional[dict] = None,
) -> list[dict]:
    col = _get_collection()
    kwargs = dict(
        query_embeddings=[query_embedding],
        n_results=min(n_results, col.count() or 1),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where
    results = col.query(**kwargs)
    items = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        items.append({"text": doc, "metadata": meta, "distance": dist})
    return items


def delete_by_file(file_path: str):
    col = _get_collection()
    col.delete(where={"file_path": file_path})


def get_total_chunks() -> int:
    return _get_collection().count()


def reset_collection():
    """Delete and recreate the collection (full reindex)."""
    global _client, _collection
    col = _get_collection()
    _client.delete_collection(COLLECTION_NAME)
    _collection = None
    _get_collection()

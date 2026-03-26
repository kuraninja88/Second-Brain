"""
Semantic retriever — embeds a query and fetches the most relevant chunks.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from query.embedder import embed_single
from store.vector_store import query as chroma_query


SOURCE_TYPE_LABELS = {
    "pdf":               "Paper (PDF)",
    "paper_note":        "Your reading note",
    "daily_note":        "Your research note",
    "thesis_draft":      "Thesis draft",
    "literature_review": "Literature Review matrix",
    "lit_notes":         "Lit review notes",
    "general":           "Document",
}


def retrieve(
    question: str,
    n_results: int = 8,
    source_filter: str = "all",   # "all" | "papers" | "notes" | "thesis"
    theme_filter: str  = "",
) -> list[dict]:
    """
    Returns up to n_results de-duplicated chunks most relevant to `question`.
    Each item: {text, author, year, filename, source_type, label, score, file_path}
    """
    q_embedding = embed_single(question)

    # Build ChromaDB 'where' filter
    where = None
    conditions = []
    if source_filter == "papers":
        conditions.append({"source_type": {"$in": ["pdf", "literature_review", "lit_notes"]}})
    elif source_filter == "notes":
        conditions.append({"source_type": {"$in": ["paper_note", "daily_note"]}})
    elif source_filter == "thesis":
        conditions.append({"source_type": {"$eq": "thesis_draft"}})
    if theme_filter:
        conditions.append({"theme": {"$eq": theme_filter}})

    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    raw = chroma_query(q_embedding, n_results=n_results * 2, where=where)

    # De-duplicate: keep best chunk per (file_path, author)
    seen_files: dict[str, dict] = {}
    for item in raw:
        meta = item["metadata"]
        fp   = meta.get("file_path", "")
        score = 1 - item["distance"]   # cosine similarity (higher = better)
        if fp not in seen_files or score > seen_files[fp]["score"]:
            seen_files[fp] = {
                "text":        item["text"],
                "author":      meta.get("author", ""),
                "year":        meta.get("year", ""),
                "filename":    meta.get("filename", Path(fp).name),
                "source_type": meta.get("source_type", "general"),
                "label":       SOURCE_TYPE_LABELS.get(meta.get("source_type", ""), "Document"),
                "theme":       meta.get("theme", ""),
                "score":       score,
                "file_path":   fp,
                "date":        meta.get("date", ""),
                "section":     meta.get("section", ""),
            }

    results = sorted(seen_files.values(), key=lambda x: x["score"], reverse=True)
    return results[:n_results]

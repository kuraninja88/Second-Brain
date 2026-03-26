"""
Ingestion pipeline - indexes all source files into ChromaDB + SQLite.

Usage:
    python brain/ingest/pipeline.py          # incremental (skips unchanged)
    python brain/ingest/pipeline.py --force  # reindex everything
"""
import hashlib
import platform
import sys
import uuid
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SOURCE_DIRS, EXTRA_FILES, LIT_REVIEW_XLSX, BRAIN_DIR
from store.metadata_db import (
    init_db, update_index_log, get_file_hash,
    upsert_paper, clear_papers_from_source, get_indexed_file_count,
    paper_exists_for, delete_papers_by_author_year,
)
from store.vector_store import add_chunks, delete_by_file
from query.embedder import embed_batch, ensure_model_available, check_ollama_running
from ingest.excel_extractor import extract_excel
from ingest.pdf_extractor import extract_pdf
from ingest.docx_extractor import extract_docx


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_type_for(file_path: Path) -> str:
    """Determine source_type based on which source directory the file is in."""
    fp = str(file_path).replace("\\", "/").lower()
    if "bacaan/catatan" in fp or "bacaan\\catatan" in fp.replace("/", "\\"):
        return "paper_note"
    if "/catatan/" in fp or "\\catatan\\" in fp:
        return "daily_note"
    if "/thesis/" in fp or "\\thesis\\" in fp:
        return "thesis_draft"
    if "lit_review_notes" in fp:
        return "lit_notes"
    if file_path.suffix.lower() == ".pdf":
        return "pdf"
    return "general"


def _make_chunk_ids(file_path: Path, count: int) -> list[str]:
    base = hashlib.md5(str(file_path).encode()).hexdigest()[:12]
    return [f"{base}_{i}" for i in range(count)]


def _ingest_excel(path: Path, force: bool) -> int:
    current_hash = file_hash(path)
    stored_hash  = get_file_hash(str(path))
    if not force and stored_hash == current_hash:
        return 0

    print(f"  Indexing: {path.name}")
    chunks = extract_excel(path)
    if not chunks:
        return 0

    # Clear previous SQLite rows for this file
    clear_papers_from_source(str(path))
    # Delete previous ChromaDB entries
    delete_by_file(str(path))

    texts     = [c["text"]     for c in chunks]
    metas     = [c["metadata"] for c in chunks]
    db_rows   = [c["db_row"]   for c in chunks]
    ids       = _make_chunk_ids(path, len(chunks))

    print(f"    Embedding {len(texts)} paper entries...")
    embeddings = embed_batch(texts)

    add_chunks(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)

    for row in db_rows:
        upsert_paper(row)

    update_index_log(str(path), current_hash, len(chunks), "literature_review")
    return len(chunks)


def _ingest_pdf(path: Path, source_folder: str, force: bool, reextract_meta: bool = False) -> int:
    current_hash = file_hash(path)
    stored_hash  = get_file_hash(str(path))
    is_new = stored_hash is None          # True only the very first time this file is seen

    if not force and stored_hash == current_hash:
        if reextract_meta:
            # File unchanged — skip re-embedding but re-run LLM metadata extraction
            chunks, _ = extract_pdf(path, source_folder)
            if chunks:
                _auto_extract_paper_meta(path, chunks, force_meta=True)
        return 0

    chunks, quality = extract_pdf(path, source_folder)
    if not chunks:
        update_index_log(str(path), current_hash, 0, "pdf", quality)
        return 0

    delete_by_file(str(path))
    texts  = [c["text"]     for c in chunks]
    metas  = [c["metadata"] for c in chunks]
    ids    = _make_chunk_ids(path, len(chunks))

    embeddings = embed_batch(texts)
    add_chunks(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
    update_index_log(str(path), current_hash, len(chunks), "pdf", quality)

    if is_new or reextract_meta:
        _auto_extract_paper_meta(path, chunks, force_meta=reextract_meta)

    return len(chunks)


def _auto_extract_paper_meta(path: Path, chunks: list[dict], force_meta: bool = False):
    """
    Use local Ollama LLM to extract paper metadata and add to the papers table.
    force_meta=True: overwrite any existing entry (from Excel or previous extraction).
    """
    from ingest.meta_extractor import extract_metadata_llm

    file_meta = chunks[0]["metadata"]
    author = file_meta.get("author", "")
    year   = file_meta.get("year", "")

    if force_meta:
        # Remove any existing entry for this PDF or matching Excel entry
        clear_papers_from_source(str(path))
        delete_papers_by_author_year(author, year)
    elif paper_exists_for(author, year):
        print(f"      [meta] already in matrix — skipping LLM extraction")
        return

    print(f"      [meta] extracting metadata via LLM...")
    full_text = "\n\n".join(c["text"] for c in chunks[:5])
    extracted = extract_metadata_llm(full_text, path.name)

    if extracted and any(v for v in extracted.values()):
        extracted["source_file"]    = str(path)
        extracted["relevant_quote"] = ""
        extracted["citation"]       = ""
        upsert_paper(extracted)
        print(f"      [meta] ✓ {extracted.get('author', '?')} ({extracted.get('year', '?')})")
    else:
        print(f"      [meta] extraction returned no data")


def _ingest_docx(path: Path, source_type: str, force: bool) -> int:
    current_hash = file_hash(path)
    stored_hash  = get_file_hash(str(path))
    if not force and stored_hash == current_hash:
        return 0

    chunks = extract_docx(path, source_type)
    if not chunks:
        update_index_log(str(path), current_hash, 0, source_type)
        return 0

    delete_by_file(str(path))
    texts  = [c["text"]     for c in chunks]
    metas  = [c["metadata"] for c in chunks]
    ids    = _make_chunk_ids(path, len(chunks))

    embeddings = embed_batch(texts)
    add_chunks(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
    update_index_log(str(path), current_hash, len(chunks), source_type)
    return len(chunks)


_LOCK_FILE = BRAIN_DIR / ".brain.lock"


def run_ingestion(force: bool = False, reextract_meta: bool = False):
    print("=" * 60)
    print("Second Brain — Ingestion Pipeline")
    if reextract_meta:
        print("Mode: RE-EXTRACT METADATA from PDFs (replaces Excel entries)")
    print("=" * 60)

    # ── Lock file: prevent simultaneous access from two machines ───────────────
    if _LOCK_FILE.exists():
        owner = _LOCK_FILE.read_text().strip()
        print(f"\n[ERROR] The database is locked by: {owner}")
        print("Make sure the app is not running on another machine.")
        print(f"If that machine is off, delete: {_LOCK_FILE}")
        sys.exit(1)
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LOCK_FILE.write_text(platform.node())

    try:
        _run_ingestion_inner(force, reextract_meta)
    finally:
        _LOCK_FILE.unlink(missing_ok=True)


def _run_ingestion_inner(force: bool = False, reextract_meta: bool = False):
    if not check_ollama_running():
        print("\n[ERROR] Ollama is not running.")
        print("Please start the Ollama app, then try again.")
        sys.exit(1)

    ensure_model_available()
    init_db()

    total_new   = 0
    total_skip  = 0
    total_error = 0

    # ── 1. Literature Review Excel ─────────────────────────────────────────────
    print("\n[1/4] Literature Review Excel")
    if LIT_REVIEW_XLSX.exists():
        n = _ingest_excel(LIT_REVIEW_XLSX, force)
        if n:
            print(f"      -> {n} entries indexed")
            total_new += n
        else:
            print("      -> unchanged, skipped")
            total_skip += 1
    else:
        print(f"      [WARN] Not found: {LIT_REVIEW_XLSX}")

    # ── 2. PDFs ────────────────────────────────────────────────────────────────
    print("\n[2/4] PDF papers")
    pdf_dirs = {
        "papers_read":   SOURCE_DIRS["papers_read"],
        "papers_supp":   SOURCE_DIRS["papers_supp"],
        "papers_review": SOURCE_DIRS["papers_review"],
    }
    for dir_name, dir_path in pdf_dirs.items():
        if not dir_path.exists():
            print(f"  [SKIP] {dir_path} not found")
            continue
        pdfs = list(dir_path.rglob("*.pdf"))
        print(f"  {dir_name}: {len(pdfs)} PDFs")
        for idx, pdf in enumerate(pdfs, 1):
            if reextract_meta:
                print(f"  [{idx}/{len(pdfs)}] {pdf.name[:55]}")
            try:
                n = _ingest_pdf(pdf, dir_name, force, reextract_meta=reextract_meta)
                if n:
                    print(f"    + {pdf.name[:60]} ({n} chunks)")
                    total_new += 1
                else:
                    total_skip += 1
            except Exception as e:
                print(f"    ! ERROR {pdf.name}: {e}")
                total_error += 1

    # ── 3. DOCX files ─────────────────────────────────────────────────────────
    print("\n[3/4] DOCX notes and drafts")
    docx_dirs = {
        "paper_notes": ("paper_note",   SOURCE_DIRS["paper_notes"]),
        "daily_notes": ("daily_note",   SOURCE_DIRS["daily_notes"]),
        "thesis":      ("thesis_draft", SOURCE_DIRS["thesis"]),
    }
    for dir_name, (stype, dir_path) in docx_dirs.items():
        if not dir_path.exists():
            print(f"  [SKIP] {dir_path} not found")
            continue
        docxs = list(dir_path.glob("*.docx"))
        print(f"  {dir_name}: {len(docxs)} files")
        for docx in docxs:
            if docx.name.startswith("~$"):
                continue  # skip temp files
            try:
                n = _ingest_docx(docx, stype, force)
                if n:
                    print(f"    + {docx.name[:60]} ({n} chunks)")
                    total_new += 1
                else:
                    total_skip += 1
            except Exception as e:
                print(f"    ! ERROR {docx.name}: {e}")
                total_error += 1

    # ── 4. Extra standalone files ──────────────────────────────────────────────
    print("\n[4/4] Extra files")
    for fp in EXTRA_FILES:
        if not fp.exists():
            continue
        try:
            stype = _source_type_for(fp)
            n = _ingest_docx(fp, stype, force)
            if n:
                print(f"  + {fp.name} ({n} chunks)")
                total_new += 1
            else:
                print(f"  → {fp.name}: unchanged")
                total_skip += 1
        except Exception as e:
            print(f"  ! ERROR {fp.name}: {e}")
            total_error += 1

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total_indexed = get_indexed_file_count()
    print(f"Done. New/updated: {total_new} | Skipped: {total_skip} | Errors: {total_error}")
    print(f"Total files in index: {total_indexed}")
    print("=" * 60)


if __name__ == "__main__":
    force          = "--force"     in sys.argv
    reextract_meta = "--reextract" in sys.argv
    run_ingestion(force=force, reextract_meta=reextract_meta)

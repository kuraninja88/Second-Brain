"""
Extract text chunks from PDF files.

Strategy:
  1. Try pdfplumber (handles multi-column academic layouts)
  2. Fall back to pypdf
  3. Clean text, chunk, return with metadata
"""
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHUNK_SIZE, CHUNK_OVERLAP, MIN_CHUNK_LEN

# Regex for filenames like "31. Barros et al (2022) - M&A activity.pdf"
_FNAME_RE = re.compile(
    r"^(?:\d+\.\s*)?"                     # optional leading number
    r"(.+?)\s*"                            # author(s)
    r"\(?(\d{4})\)?"                       # year in optional parens
    r"(?:\s*[-–]\s*(.+))?$"              # optional title after dash
)


def _parse_filename(stem: str) -> dict:
    m = _FNAME_RE.match(stem)
    if m:
        return {
            "author": m.group(1).strip(),
            "year":   m.group(2),
            "title":  (m.group(3) or "").strip(),
        }
    return {"author": stem, "year": "", "title": ""}


def _clean_text(text: str) -> str:
    # Fix hyphenated line-breaks: "sustain-\nability" → "sustainability"
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove form-feed characters
    text = text.replace("\f", "\n")
    return text.strip()


def _extract_with_pdfplumber(pdf_path: Path) -> tuple[str, str]:
    """Returns (text, quality) where quality is 'ok' or 'poor'."""
    import pdfplumber
    pages_text = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
    except Exception:
        return "", "poor"

    full = "\n".join(pages_text)
    char_per_page = len(full) / max(len(pages_text), 1)
    quality = "poor" if char_per_page < 200 else "ok"
    return full, quality


def _extract_with_pypdf(pdf_path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t)
        full = "\n".join(pages_text)
        char_per_page = len(full) / max(len(pages_text), 1)
        quality = "poor" if char_per_page < 200 else "ok"
        return full, quality
    except Exception:
        return "", "poor"


def _chunk_text(text: str) -> list[str]:
    MAX_EMBED_CHARS = 6000  # hard cap — nomic-embed-text has 8192 token limit (~4 chars/token)
    size = min(CHUNK_SIZE * 4, MAX_EMBED_CHARS)
    overlap = CHUNK_OVERLAP * 4
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)
        start += size - overlap
    return chunks


def extract_pdf(file_path: Path, source_folder: str) -> tuple[list[dict], str]:
    """
    Returns (chunks, quality).
    chunks: list of {"text": ..., "metadata": {...}}
    quality: "ok" | "poor"
    """
    stem = file_path.stem
    meta_from_name = _parse_filename(stem)

    # Try pdfplumber first, fall back to pypdf
    text, quality = _extract_with_pdfplumber(file_path)
    if not text or quality == "poor":
        text2, q2 = _extract_with_pypdf(file_path)
        if len(text2) > len(text):
            text, quality = text2, q2

    if not text:
        return [], "poor"

    text = _clean_text(text)
    chunks = _chunk_text(text)

    base_meta = {
        "source_type":   "pdf",
        "file_path":     str(file_path),
        "filename":      file_path.name,
        "source_folder": source_folder,
        "author":        meta_from_name["author"],
        "year":          meta_from_name["year"],
        "title":         meta_from_name["title"],
    }

    result = [
        {"text": c, "metadata": {**base_meta, "chunk_index": i}}
        for i, c in enumerate(chunks)
    ]
    return result, quality

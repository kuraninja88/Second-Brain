"""
Second Brain - Configuration
All paths, model names, and parameters in one place.
Supports Windows and macOS (Google Drive shared database).
"""
import platform
from pathlib import Path

# ─── OS-aware base paths ─────────────────────────────────────────────────────
if platform.system() == "Windows":
    # G: drive = Google Drive on Windows
    G_BASE = Path("G:/Other computers/My Laptop/Kuliah/NCL/Dissertation")
    C_BASE = Path("C:/Users/krisb/NCL - claude")

else:
    # macOS — find Google Drive in CloudStorage
    _cloud = Path.home() / "Library/CloudStorage"
    _candidates = sorted(_cloud.glob("GoogleDrive-*")) if _cloud.exists() else []
    if _candidates:
        _gdrive_root = _candidates[0] / "My Drive"
    else:
        _gdrive_root = Path.home() / "Google Drive/My Drive"
    G_BASE = _gdrive_root / "Kuliah/NCL/Dissertation"
    C_BASE = G_BASE  # on Mac, all files live under Google Drive

# ─── Source file locations ────────────────────────────────────────────────────
SOURCE_DIRS = {
    "papers_read":     G_BASE / "Bacaan/1. Read",
    "papers_supp":     G_BASE / "Bacaan/2. Supp - Citations",
    "papers_review":   G_BASE / "Bacaan/3. To Review",
    "paper_notes":     C_BASE / "Bacaan/Catatan",
    "daily_notes":     C_BASE / "Catatan",
    "thesis":          C_BASE / "Thesis",
}

# Extra standalone DOCX files to include
EXTRA_FILES = [
    C_BASE / "lit_review_notes_ESG_MA_SCI_v2.docx",
    G_BASE / "Literature review SCI.docx",
    G_BASE / "Social Connectedness_draft_1.docx",
]

# Literature Review Excel (primary structured source)
LIT_REVIEW_XLSX = C_BASE / "Thesis/Literature Review.xlsx"

# ─── Brain storage (database on Google Drive — shared between Windows & Mac) ──
BRAIN_DIR  = G_BASE / "brain"
DB_PATH    = BRAIN_DIR / "brain.db"
INDEX_LOG  = BRAIN_DIR / "index_log.json"
CHROMA_DIR = BRAIN_DIR / "chroma_db"

# ─── Ollama models ────────────────────────────────────────────────────────────
EMBED_MODEL    = "nomic-embed-text"
CHAT_MODEL     = "qwen3:8b"          # better quality; change to "qwen3:4b" for faster responses
OLLAMA_BASE_URL = "http://localhost:11434"

# ─── Chunking parameters ─────────────────────────────────────────────────────
CHUNK_SIZE    = 800   # approximate tokens per chunk
CHUNK_OVERLAP = 150   # overlap between consecutive chunks
MIN_CHUNK_LEN = 80    # discard chunks shorter than this (chars)

# ─── ChromaDB collection name ────────────────────────────────────────────────
COLLECTION_NAME = "thesis_brain"

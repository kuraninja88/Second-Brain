# 🧠 Second Brain — Thesis Research Assistant

A fully local, offline RAG (Retrieval-Augmented Generation) system for academic thesis writing. Ask questions about your research, get cited answers from your own papers and notes, and browse your literature review matrix — all running on your own machine with no API costs.

Built for a thesis on **"Does social connectedness (Facebook's SCI) affect post-M&A ESG performance?"** at Newcastle University Business School, but the system is general-purpose for any research topic.

---

## Features

| Feature | Description |
|---------|-------------|
| **Ask** | Ask natural-language questions — answers cite your own papers and notes |
| **Help Me Write** | Generate a structured literature synthesis for a thesis section |
| **Find Papers** | Instant search across your literature review matrix |
| **Lit Review Matrix** | Browse + filter all papers, download as CSV |
| **Streaming answers** | See the AI typing the answer in real-time |
| **Auto-metadata** | New PDFs automatically get metadata extracted via LLM |
| **Star relevance** | Sources rated ★★★★★ for relevance |
| **Open PDF** | Click to open the source file directly |
| **Multi-machine sync** | Database lives on Google Drive — shared between Windows and Mac |

---

## How It Works

```
Your files (PDFs, notes, Excel)
        ↓
  Ingestion Pipeline
  (chunks + embeds via Ollama)
        ↓
  ChromaDB (vectors) + SQLite (metadata)
        ↓
  Streamlit Web UI at localhost:8501
        ↓
  You ask a question
        ↓
  1. Search — finds top-K relevant chunks (instant)
  2. Generate — Ollama reads chunks and writes a cited answer (30–90 sec)
```

**Everything runs locally.** No internet after setup. No API costs. No data leaves your machine.

---

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.ai)** — local LLM runner (free, available for Windows and Mac)
- **Models** (pulled via Ollama):
  - `nomic-embed-text` — for embeddings
  - `qwen3:8b` — for generating answers (or any other chat model)

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/second-brain.git
cd second-brain
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Ollama and pull models

Download Ollama from [ollama.ai](https://ollama.ai), then:

```bash
ollama pull nomic-embed-text
ollama pull qwen3:8b
```

### 4. Configure your file paths

Edit `config.py` to point to your files:

```python
# Windows
G_BASE = Path("G:/path/to/your/Dissertation")   # where your PDFs are
C_BASE = Path("C:/path/to/your/notes")           # where your notes/thesis are
BRAIN_DIR = G_BASE / "brain"                     # where the database will live
```

On **macOS**, the config auto-detects your Google Drive path — no changes needed if your files are on Google Drive.

### 5. Index your files

```bash
python ingest/pipeline.py
```

First run takes 15–30 minutes for ~150 files. Subsequent runs are incremental (seconds for new files only).

### 6. Start the app

```bash
streamlit run ui/app.py
```

Open your browser at `http://localhost:8501`.

---

## Source Files Supported

| Type | Location | What it stores |
|------|----------|---------------|
| PDF papers | `Bacaan/1. Read/`, `Bacaan/3. To Review/` | Full text, chunked |
| Reading notes | `Bacaan/Catatan/` | Your notes on each paper |
| Daily notes | `Catatan/` | Research diary |
| Thesis drafts | `Thesis/` | Your writing so far |
| Literature Review Excel | `Thesis/Literature Review.xlsx` | Structured matrix |

---

## CLI Reference

```bash
# Normal run — indexes only new/changed files
python ingest/pipeline.py

# Force re-index everything
python ingest/pipeline.py --force

# Re-extract metadata from PDFs via LLM (replaces Excel entries)
# Use this to get full author names, titles, etc. from actual paper text
python ingest/pipeline.py --reextract

# Start the web app
streamlit run ui/app.py
```

---

## File Structure

```
brain/
├── config.py                  # All paths, model names, parameters
├── requirements.txt
├── ingest/
│   ├── pipeline.py            # Orchestrator — runs all extractors
│   ├── pdf_extractor.py       # PDF text extraction + chunking
│   ├── docx_extractor.py      # DOCX notes + thesis drafts
│   ├── excel_extractor.py     # Literature Review Excel → SQLite
│   └── meta_extractor.py      # LLM-based metadata extraction for new PDFs
├── store/
│   ├── vector_store.py        # ChromaDB wrapper
│   └── metadata_db.py         # SQLite wrapper (papers table + index log)
├── query/
│   ├── embedder.py            # Ollama nomic-embed-text embeddings
│   ├── retriever.py           # Semantic search + deduplication
│   └── answerer.py            # Prompt builder + Ollama chat (streaming)
└── ui/
    └── app.py                 # Streamlit web app (4 tabs)
```

---

## Multi-Machine Setup (Windows + Mac)

The database (`chroma_db/`, `brain.db`, `index_log.json`) lives on Google Drive so it syncs automatically between machines.

**On Windows:** runs as configured
**On Mac:** `config.py` auto-detects the Google Drive path via `~/Library/CloudStorage/GoogleDrive-*/`

**Rule:** never run the app on both machines at the same time — a lock file (`brain/.brain.lock`) will warn you if this happens.

---

## Configuration

All settings are in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `EMBED_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `CHAT_MODEL` | `qwen3:8b` | Ollama model for generating answers |
| `CHUNK_SIZE` | `800` tokens | Chunk size for text splitting |
| `CHUNK_OVERLAP` | `150` tokens | Overlap between chunks |

---

## License

MIT — free to use, adapt, and share.

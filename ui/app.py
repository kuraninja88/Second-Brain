"""
Second Brain — Streamlit Web UI
Run: streamlit run brain/ui/app.py
"""
import sys
from pathlib import Path

# Allow imports from brain/ root
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import platform
import subprocess

import pandas as pd
import streamlit as st
from store.metadata_db import (
    init_db, get_all_themes, get_papers_by_theme,
    search_papers, get_indexed_file_count, get_last_indexed, get_paper_count,
    get_all_papers, find_pdf_for_paper,
)
from store.vector_store import get_total_chunks
from query.retriever import retrieve
from query.answerer import answer_stream, synthesize_stream
from query.embedder import check_ollama_running


def _stars(score: float) -> str:
    """Convert cosine similarity (0-1) to a 1-5 star rating string."""
    if score >= 0.75:   n = 5
    elif score >= 0.60: n = 4
    elif score >= 0.45: n = 3
    elif score >= 0.30: n = 2
    else:               n = 1
    return "★" * n + "☆" * (5 - n)


def _open_file(path: str):
    """Open a file using the OS default application."""
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        st.error(f"Could not open file: {e}")

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Second Brain — Thesis",
    page_icon="🧠",
    layout="wide",
)

init_db()


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 Second Brain")
    st.caption("Thesis: Social Connectedness × ESG × M&A")
    st.divider()

    # Index stats
    n_files  = get_indexed_file_count()
    n_chunks = get_total_chunks()
    n_papers = get_paper_count()
    last_idx = get_last_indexed()
    st.metric("Files indexed", n_files)
    st.metric("Searchable chunks", n_chunks)
    st.metric("Papers in matrix", n_papers)
    if last_idx:
        st.caption(f"Last indexed: {last_idx[:16]}")

    st.divider()

    # Re-index button
    if st.button("🔄 Re-index Files", use_container_width=True):
        with st.spinner("Indexing new/changed files…"):
            try:
                from ingest.pipeline import run_ingestion
                run_ingestion(force=False)
                st.success("Re-indexing complete!")
                st.rerun()
            except Exception as e:
                st.error(f"Error during indexing: {e}")

    st.divider()

    # Filters
    st.subheader("Filters")
    source_filter = st.selectbox(
        "Search in",
        options=["all", "papers", "notes", "thesis"],
        format_func=lambda x: {
            "all":    "All sources",
            "papers": "Papers only",
            "notes":  "My notes only",
            "thesis": "Thesis drafts only",
        }[x],
    )

    themes = [""] + get_all_themes()
    theme_filter = st.selectbox(
        "Theme filter",
        options=themes,
        format_func=lambda x: x if x else "All themes",
    )

    n_results = st.slider("Max results", min_value=3, max_value=15, value=6)

    # Ollama status
    st.divider()
    if check_ollama_running():
        st.success("Ollama: running ✓", icon="✅")
    else:
        st.error("Ollama not running — start the Ollama app first", icon="⚠️")


# ─── Main area ────────────────────────────────────────────────────────────────
st.title("🧠 Second Brain")

tab_ask, tab_write, tab_find, tab_matrix = st.tabs(
    ["💬 Ask", "✍️ Help Me Write", "🔍 Find Papers", "📊 Lit Review Matrix"]
)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: Ask a question
# ══════════════════════════════════════════════════════════════════════════════
with tab_ask:
    st.subheader("Ask a question about your research")
    question = st.text_area(
        "Your question",
        placeholder="e.g. What papers discuss cultural distance in cross-border M&A?",
        height=80,
        key="ask_input",
    )

    if st.button("🔍 Search & Answer", key="ask_btn", type="primary"):
        if not question.strip():
            st.warning("Please enter a question.")
        elif not check_ollama_running():
            st.error("Ollama is not running. Start the Ollama app first.")
        elif n_chunks == 0:
            st.warning("No files indexed yet. Click 'Re-index Files' in the sidebar first.")
        else:
            with st.spinner("Searching your research materials…"):
                chunks = retrieve(
                    question,
                    n_results=n_results,
                    source_filter=source_filter,
                    theme_filter=theme_filter,
                )
            if not chunks:
                st.info("No relevant content found. Try different keywords or broader filters.")
            else:
                st.markdown("### Answer")
                result = st.write_stream(answer_stream(question, chunks))
                st.divider()

                st.markdown(f"### Sources ({len(chunks)})")
                for i, c in enumerate(chunks, 1):
                    author = c.get("author", "Unknown")
                    year   = c.get("year", "")
                    label  = c.get("label", "")
                    score  = c.get("score", 0)
                    date   = c.get("date", "")

                    title_parts = [f"[{i}]", author]
                    if year:
                        title_parts.append(f"({year})")
                    title_parts.append(f"· {label}")
                    if date:
                        title_parts.append(f"· {date}")
                    title_parts.append(f"· {_stars(score)}")

                    with st.expander(" ".join(title_parts)):
                        st.caption(f"File: {c.get('filename', '')}")
                        if c.get("section"):
                            st.caption(f"Section: {c['section']}")
                        st.text_area(
                            "Excerpt",
                            value=c["text"][:1200],
                            height=150,
                            disabled=True,
                            key=f"ask_excerpt_{i}",
                        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Help Me Write
# ══════════════════════════════════════════════════════════════════════════════
with tab_write:
    st.subheader("Get a literature synthesis for a thesis section")
    st.caption(
        "Describe the section you're writing. The brain will pull relevant papers and notes "
        "and produce a structured synthesis with bullet points and citations."
    )

    topic = st.text_area(
        "Section topic",
        placeholder="e.g. Social connectedness as a determinant of cross-border M&A deal flow",
        height=80,
        key="write_input",
    )

    if st.button("✍️ Synthesise Literature", key="write_btn", type="primary"):
        if not topic.strip():
            st.warning("Please describe the section topic.")
        elif not check_ollama_running():
            st.error("Ollama is not running. Start the Ollama app first.")
        elif n_chunks == 0:
            st.warning("No files indexed yet. Click 'Re-index Files' in the sidebar first.")
        else:
            with st.spinner("Retrieving relevant materials…"):
                chunks = retrieve(
                    topic,
                    n_results=n_results,
                    source_filter=source_filter,
                    theme_filter=theme_filter,
                )
            if not chunks:
                st.info("No relevant content found.")
            else:
                st.markdown("### Synthesis")
                result = st.write_stream(synthesize_stream(topic, chunks))
                st.divider()

                st.markdown(f"### Materials used ({len(chunks)})")
                for i, c in enumerate(chunks, 1):
                    author = c.get("author", "Unknown")
                    year   = c.get("year", "")
                    label  = c.get("label", "")
                    score  = c.get("score", 0)

                    header = f"[{i}] {author}"
                    if year:
                        header += f" ({year})"
                    header += f" · {label} · {_stars(score)}"

                    with st.expander(header):
                        st.caption(c.get("filename", ""))
                        st.text_area(
                            "Excerpt",
                            value=c["text"][:1200],
                            height=120,
                            disabled=True,
                            key=f"write_excerpt_{i}",
                        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Find Papers (structured lookup from Excel matrix)
# ══════════════════════════════════════════════════════════════════════════════
with tab_find:
    st.subheader("Browse your Literature Review matrix")
    st.caption(
        "Instant lookup from your Excel matrix — no AI needed, no API cost. "
        "Filter by theme or search by author/keyword."
    )

    col1, col2 = st.columns([1, 2])
    with col1:
        find_theme = st.selectbox(
            "Filter by theme",
            options=themes,
            format_func=lambda x: x if x else "All themes",
            key="find_theme",
        )
    with col2:
        find_query = st.text_input(
            "Search by author, methodology, or keyword",
            placeholder="e.g. Barros, DiD, ESG, gravity model",
            key="find_query",
        )

    if st.button("🔍 Search Matrix", key="find_btn"):
        if find_query.strip():
            st.session_state["find_results"] = search_papers(find_query)
        elif find_theme:
            st.session_state["find_results"] = get_papers_by_theme(find_theme)
        else:
            st.session_state["find_results"] = None
            st.info("Enter a search term or select a theme.")

    # ── Results — read from session_state so "Open PDF" clicks don't wipe them ──
    papers = st.session_state.get("find_results")
    if papers is not None:
        if papers:
            st.markdown(f"**{len(papers)} paper(s) found**")
            for p in papers:
                author = p.get("author", "Unknown")
                year   = p.get("year", "")
                theme  = p.get("theme", "")
                header = f"{author}"
                if year:
                    header += f" ({year})"
                if theme:
                    header += f" — {theme}"

                with st.expander(header):
                    cols = st.columns(2)
                    with cols[0]:
                        if p.get("methodology"):
                            st.markdown(f"**Methodology:** {p['methodology']}")
                        if p.get("variables"):
                            st.markdown(f"**Variables:** {p['variables']}")
                        if p.get("theory"):
                            st.markdown(f"**Theory:** {p['theory']}")
                        if p.get("data_sample"):
                            st.markdown(f"**Data/Sample:** {p['data_sample']}")
                    with cols[1]:
                        if p.get("key_findings"):
                            st.markdown(f"**Key findings:** {p['key_findings']}")
                        if p.get("notes"):
                            st.markdown(f"**Relevance to thesis:** {p['notes']}")
                        if p.get("limitations"):
                            st.markdown(f"**Limitations:** {p['limitations']}")
                    if p.get("relevant_quote"):
                        st.markdown(f"> {p['relevant_quote']}")
                    if p.get("citation"):
                        st.caption(f"Citation: {p['citation']}")

                    # ── Open PDF file ─────────────────────────────────────────
                    pdf_path = find_pdf_for_paper(p.get("author", ""), p.get("year", ""))
                    if pdf_path and Path(pdf_path).exists():
                        st.divider()
                        fcol1, fcol2 = st.columns([1, 3])
                        with fcol1:
                            if st.button("📂 Open PDF", key=f"open_{p.get('id', author)}"):
                                _open_file(pdf_path)
                        with fcol2:
                            st.caption(f"📄 {Path(pdf_path).name}")
        else:
            st.info("No papers found. Try a different keyword or check your Literature Review Excel.")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4: Literature Review Matrix
# ══════════════════════════════════════════════════════════════════════════════
with tab_matrix:
    st.subheader("Literature Review Matrix")
    st.caption(
        "All papers from your Literature Review Excel in one table. "
        "Filter by theme, search by keyword, then download as CSV."
    )

    all_papers = get_all_papers()

    if not all_papers:
        st.info("No papers in the matrix yet. Run 'Re-index Files' to import your Literature Review Excel.")
    else:
        # ── Filters ───────────────────────────────────────────────────────────
        mcol1, mcol2 = st.columns([1, 2])
        with mcol1:
            mat_theme = st.selectbox(
                "Filter by theme",
                options=themes,
                format_func=lambda x: x if x else "All themes",
                key="mat_theme",
            )
        with mcol2:
            mat_query = st.text_input(
                "Search (author, methodology, keyword…)",
                placeholder="e.g. gravity model, ESG, DiD",
                key="mat_query",
            )

        # ── Apply filters ─────────────────────────────────────────────────────
        filtered = all_papers
        if mat_theme:
            filtered = [p for p in filtered if mat_theme.lower() in (p.get("theme") or "").lower()]
        if mat_query.strip():
            q = mat_query.strip().lower()
            filtered = [
                p for p in filtered
                if any(
                    q in (p.get(col) or "").lower()
                    for col in ("author", "theme", "methodology", "key_findings",
                                "theory", "variables", "rq_focus", "notes")
                )
            ]

        st.markdown(f"**{len(filtered)} of {len(all_papers)} papers**")

        # ── Build DataFrame ───────────────────────────────────────────────────
        _COL_NAMES = {
            "author":         "Author(s)",
            "year":           "Year",
            "reference":      "Reference",
            "theme":          "Theme",
            "rq_focus":       "Research Focus",
            "theory":         "Theory / Framework",
            "data_sample":    "Data & Sample",
            "variables":      "Variables",
            "methodology":    "Methodology",
            "key_findings":   "Key Findings",
            "novelty":        "Novelty",
            "limitations":    "Limitations / Gap",
            "notes":          "Notes (Relevance)",
            "relevant_quote": "Relevant Quote",
            "citation":       "Citation",
        }
        display_cols = list(_COL_NAMES.keys())
        df = pd.DataFrame(filtered)[display_cols].rename(columns=_COL_NAMES)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=500,
        )

        # ── Download ──────────────────────────────────────────────────────────
        csv_data = df.to_csv(index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
        st.download_button(
            label="⬇️ Download as CSV",
            data=csv_data,
            file_name="literature_review_matrix.csv",
            mime="text/csv",
            type="primary",
        )

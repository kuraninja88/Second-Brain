"""
Auto-extract paper metadata from PDF text using local Ollama LLM.

Called only for NEW PDFs that have never been indexed before.
Populates the papers table so the paper appears in Find Papers + Lit Review Matrix.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHAT_MODEL

_PROMPT = """You are a research metadata extractor. Read the academic paper excerpt and extract structured information.

Return ONLY a valid JSON object with exactly these keys. Use empty string "" if information is not available.
No extra text, no markdown, no explanation — just the JSON object.

{{
  "author": "All author surnames listed (e.g. Smith, Jones & Williams — include every author, never abbreviate as et al)",
  "year": "Publication year as YYYY",
  "reference": "Full paper title",
  "theme": "Main research theme or topic area (short phrase)",
  "rq_focus": "Main research question or focus of the paper",
  "theory": "Theoretical framework or key theory used",
  "data_sample": "Dataset name and sample description",
  "variables": "Key dependent and independent variables",
  "methodology": "Research method (e.g. OLS regression, DiD, event study, meta-analysis)",
  "key_findings": "Main findings in 2-3 sentences",
  "novelty": "What is novel or unique about this paper",
  "limitations": "Stated limitations or research gaps",
  "notes": "How this paper relates to M&A, ESG, or social connectedness research"
}}

Paper filename: {filename}

Paper text (excerpt):
{text}"""


def _strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks produced by reasoning models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _parse_json(raw: str) -> dict:
    """Extract JSON from model response even if wrapped in extra text."""
    raw = _strip_thinking(raw)
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except Exception:
        pass
    # Find first complete {...} block
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


def extract_metadata_llm(text: str, filename: str) -> dict:
    """
    Call local Ollama LLM to extract paper metadata from text.

    Returns a dict matching the papers table schema, or {} on failure.
    Only the first ~4000 chars of text are sent (abstract + intro is enough).
    """
    import ollama

    prompt = _PROMPT.format(filename=filename, text=text[:4000])

    try:
        response = ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},  # deterministic — no creativity needed
        )
        raw = response["message"]["content"]
        data = _parse_json(raw)

        # Normalise to schema keys, strip "N/A" placeholders
        schema_keys = {
            "author", "year", "reference", "theme", "rq_focus", "theory",
            "data_sample", "variables", "methodology", "key_findings",
            "novelty", "limitations", "notes",
        }
        result = {}
        for k in schema_keys:
            v = str(data.get(k, "")).strip()
            result[k] = "" if v.upper() in ("N/A", "NA", "NONE", "NULL") else v

        return result

    except Exception as e:
        print(f"      [meta] LLM call failed: {e}")
        return {}

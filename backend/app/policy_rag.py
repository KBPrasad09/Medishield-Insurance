"""
Policy RAG module — ingests policy PDFs into a vector store and retrieves the
clauses relevant to a coverage question.

Stack:
  - Docling parses each PDF (per the brief); PyMuPDF is a graceful fallback so a
    Docling install problem can never block the pipeline.
  - Chunk by policy section heading, tag each chunk with the plan tier so
    retrieval can be scoped to the member's plan.
  - Qdrant (local, on-disk) is the vector store; FastEmbed supplies embeddings.
    Both ship prebuilt wheels — no C++ toolchain needed — and Qdrant is one of
    the two vector stores named in the brief.

Retrieval: given a coverage query built from the claim's CPT codes, return the
top-k most relevant policy chunks for the member's plan tier.
"""

from __future__ import annotations

import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
QDRANT_DIR = _BACKEND / ".qdrant"
COLLECTION = "medishield_policies"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"  # small, fast, prebuilt

POLICY_FILES = {
    "GOLD": "medishield_gold_plan.pdf",
    "SILVER": "medishield_silver_plan.pdf",
}
POLICY_DIR = _BACKEND.parent / "dataset" / "policies"

_client_singleton = None


# ──────────────────────────────────────────────────────────────────────
# PDF -> text
# ──────────────────────────────────────────────────────────────────────
def _parse_with_docling(pdf_path: Path) -> str:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    return converter.convert(str(pdf_path)).document.export_to_markdown()


def _parse_with_pymupdf(pdf_path: Path) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    return "\n".join(page.get_text() for page in doc)


def parse_pdf(pdf_path: Path) -> str:
    """Docling first (per brief), PyMuPDF fallback.

    Docling gives layout-aware markdown — headings stay headings and tables stay
    tables — which matters here because chunking keys off section headings and
    the exclusion ranges live in a table. PyMuPDF returns a flatter text stream;
    the chunker copes, but it's the weaker input. The fallback exists so a heavy
    optional dependency can never stop the pipeline from running.
    """
    try:
        text = _parse_with_docling(pdf_path)
        print(f"[policy_rag] Parsed {pdf_path.name} with Docling ({len(text)} chars).")
        return text
    except Exception as exc:  # noqa: BLE001
        print(f"[policy_rag] Docling unavailable ({exc}); using PyMuPDF fallback.")
        text = _parse_with_pymupdf(pdf_path)
        print(f"[policy_rag] Parsed {pdf_path.name} with PyMuPDF ({len(text)} chars).")
        return text


# ──────────────────────────────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────────────────────────────
_SECTION_RE = re.compile(r"(?m)^\s*#{0,3}\s*(\d+(?:\.\d+)?\.?\s+[A-Z][^\n]{0,80})$")


def chunk_by_section(text: str) -> list[tuple[str, str]]:
    """Return (section_title, section_text) pairs; fall back to fixed windows."""
    matches = list(_SECTION_RE.finditer(text))
    chunks: list[tuple[str, str]] = []
    if matches:
        for i, m in enumerate(matches):
            title = m.group(1).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            # Skip Table-of-Contents stubs and other near-empty matches; keep
            # only chunks with real clause text.
            if len(body) >= 40:
                chunks.append((title, body))
        return chunks

    window = 1500
    for i in range(0, len(text), window):
        chunks.append((f"chunk_{i // window}", text[i : i + window]))
    return chunks


# ──────────────────────────────────────────────────────────────────────
# Vector store (Qdrant local + FastEmbed)
# ──────────────────────────────────────────────────────────────────────
def _client():
    global _client_singleton
    if _client_singleton is None:
        from qdrant_client import QdrantClient

        QDRANT_DIR.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(QDRANT_DIR))
        client.set_model(EMBED_MODEL)
        _client_singleton = client
    return _client_singleton


def ingest_policies(policy_dir: Path | None = None) -> int:
    """(Re)build the policy collection from the PDFs. Returns chunk count."""
    policy_dir = policy_dir or POLICY_DIR
    client = _client()

    # Drop the old collection before rebuilding. This must be verified, not
    # attempted: chunk ids are sequential, so if a delete quietly fails and the
    # new parse produces fewer chunks than the old one, the surplus ids survive
    # and the index ends up serving a mix of two different parses.
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
        if client.collection_exists(COLLECTION):
            raise RuntimeError(
                f"Could not delete existing collection {COLLECTION!r}. "
                "Stop the API server (it holds the Qdrant lock) and retry."
            )

    docs, metas, ids = [], [], []
    cid = 0
    for tier, filename in POLICY_FILES.items():
        pdf_path = policy_dir / filename
        if not pdf_path.exists():
            print(f"[policy_rag] WARNING: {pdf_path} not found, skipping.")
            continue
        text = parse_pdf(pdf_path)
        for title, body in chunk_by_section(text):
            docs.append(f"{title}\n{body}")
            metas.append({"plan_tier": tier, "section": title})
            ids.append(cid)
            cid += 1

    if docs:
        client.add(collection_name=COLLECTION, documents=docs, metadata=metas, ids=ids)
        stored = client.count(COLLECTION).count
        if stored != len(docs):
            raise RuntimeError(
                f"Index has {stored} chunks but {len(docs)} were ingested — "
                "stale data from a previous run is still present."
            )
    return len(docs)


def retrieve(query: str, plan_tier: str, k: int = 4) -> list[dict]:
    """Top-k policy chunks for the member's plan tier."""
    from qdrant_client import models

    client = _client()
    flt = None
    if plan_tier:
        flt = models.Filter(
            must=[models.FieldCondition(
                key="plan_tier",
                match=models.MatchValue(value=plan_tier.upper()),
            )]
        )
    hits = client.query(
        collection_name=COLLECTION, query_text=query, query_filter=flt, limit=k
    )
    return [{"section": h.metadata.get("section"), "text": h.document} for h in hits]

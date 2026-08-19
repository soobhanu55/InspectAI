"""Hand-labeled retrieval evaluation for the RAG side: BM25 vs. Dense (local
sentence-transformers). Runs fully locally, no paid API, no ChromaDB server
required -- uses the real BM25Index class as-is, and the real LocalEmbeddings
class with an in-memory cosine index in place of ChromaDB.

20 manufacturing-QC-relevant queries over a 20-passage corpus.

Run: python tests/eval_retrieval.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from langchain_core.documents import Document

from rag.embeddings import LocalEmbeddings
from rag.retriever import BM25Index

CORPUS_TEXTS = [
    "Surface scratches deeper than 0.2mm on aluminum housings are classified as major defects.",
    "Hairline cracks near weld joints require immediate quarantine and root cause analysis.",
    "Dents on non-structural panels under 5mm diameter are accepted within tolerance.",
    "Porosity in cast parts is inspected via X-ray for internal voids exceeding 2% volume.",
    "Corrosion on fasteners after salt-spray testing fails the part per ISO 9227.",
    "Inclusions in forged steel components are flagged during ultrasonic testing.",
    "The calibration schedule for torque wrenches is every 90 days per QMS procedure.",
    "First article inspection requires full dimensional report before production release.",
    "Statistical process control charts flag any point beyond three sigma from the mean.",
    "Incoming raw material batches are sampled at a rate of one unit per 50 in the lot.",
    "The defect tagging system assigns severity levels: low, medium, and high.",
    "Operators must log every rejected unit with a defect code and photo evidence.",
    "Preventive maintenance on the CNC mill is scheduled weekly to reduce tolerance drift.",
    "Non-conforming material is segregated in a red-tagged quarantine area.",
    "The supplier corrective action request process starts within 48 hours of a defect report.",
    "Coating thickness is measured with a magnetic gauge and must exceed 25 microns.",
    "Vibration analysis on rotating equipment detects bearing wear before failure.",
    "The traceability system links every finished part back to its raw material heat number.",
    "Operator training records are audited annually against the skills matrix.",
    "The line stops automatically if defect rate exceeds 3% in a rolling 100-unit window.",
]

EVAL_QUERIES = [
    {"query": "how deep does a scratch have to be to count as a major defect", "correct_idx": 0},
    {"query": "what happens when a crack is found near a weld", "correct_idx": 1},
    {"query": "are small dents acceptable", "correct_idx": 2},
    {"query": "how is internal porosity checked in cast parts", "correct_idx": 3},
    {"query": "what test determines if fasteners fail due to corrosion", "correct_idx": 4},
    {"query": "how are inclusions in forged steel detected", "correct_idx": 5},
    {"query": "how often are torque wrenches calibrated", "correct_idx": 6},
    {"query": "what's required before releasing a part to production", "correct_idx": 7},
    {"query": "when does a control chart flag an out-of-control process", "correct_idx": 8},
    {"query": "what's the sampling rate for incoming materials", "correct_idx": 9},
    {"query": "what severity levels does the defect system use", "correct_idx": 10},
    {"query": "what must an operator log for a rejected part", "correct_idx": 11},
    {"query": "how often is the CNC mill maintained", "correct_idx": 12},
    {"query": "where does non-conforming material get stored", "correct_idx": 13},
    {"query": "how quickly must a supplier respond to a defect report", "correct_idx": 14},
    {"query": "what's the minimum acceptable coating thickness", "correct_idx": 15},
    {"query": "how is bearing wear detected before it fails", "correct_idx": 16},
    {"query": "how are finished parts traced back to raw material", "correct_idx": 17},
    {"query": "how often are operator training records audited", "correct_idx": 18},
    {"query": "what defect rate automatically stops the line", "correct_idx": 19},
]


def bm25_eval() -> tuple[float, float]:
    docs = [Document(page_content=t) for t in CORPUS_TEXTS]
    with tempfile.TemporaryDirectory() as td:
        idx = BM25Index(index_path=f"{td}/bm25.pkl", docs_path=f"{td}/docs.pkl")
        idx.build(docs)

        hits1 = hits3 = 0
        for q in EVAL_QUERIES:
            results = idx.search(q["query"], k=3)
            texts = [d.page_content for d, _ in results]
            correct_text = CORPUS_TEXTS[q["correct_idx"]]
            if texts and texts[0] == correct_text:
                hits1 += 1
            if correct_text in texts:
                hits3 += 1
    n = len(EVAL_QUERIES)
    return hits1 / n, hits3 / n


def dense_eval(embedder: LocalEmbeddings) -> tuple[float, float]:
    vectors = np.array(embedder.embed_documents(CORPUS_TEXTS))
    hits1 = hits3 = 0
    for q in EVAL_QUERIES:
        qvec = np.array(embedder.embed_query(q["query"]))
        sims = vectors @ qvec
        top3 = np.argsort(sims)[::-1][:3]
        if top3[0] == q["correct_idx"]:
            hits1 += 1
        if q["correct_idx"] in top3:
            hits3 += 1
    n = len(EVAL_QUERIES)
    return hits1 / n, hits3 / n


def main() -> None:
    print("BM25 (real BM25Index class)...")
    bm25_r1, bm25_r3 = bm25_eval()
    print(f"BM25            Recall@1={bm25_r1*100:5.1f}%  Recall@3={bm25_r3*100:5.1f}%")

    print("Loading local embedder (real LocalEmbeddings class)...")
    embedder = LocalEmbeddings()
    dense_r1, dense_r3 = dense_eval(embedder)
    print(f"Dense (local)   Recall@1={dense_r1*100:5.1f}%  Recall@3={dense_r3*100:5.1f}%")

    print(f"\n{len(EVAL_QUERIES)} hand-labeled manufacturing-QC queries against a {len(CORPUS_TEXTS)}-passage corpus.")


if __name__ == "__main__":
    main()

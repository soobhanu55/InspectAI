# FertigungsAI - Multimodal AI Quality Control Inspector

## Problem Statement
Germany manufacturing loses €50B/year to defects.
40% of SMEs cannot find AI-qualified workers (BMBF 2024).
This project demonstrates how a student can build a production-grade multimodal AI for this market using entirely free tools.

##  Architecture Diagram

```ascii
Image Upload → FastAPI → YOLOv8n → LangGraph →
[Hybrid RAG: ChromaDB + BM25 + RRF] →
[Cross-Encoder Reranker] →
[Groq LLaMA-3.3-70B] → SSE Stream → React Frontend
```

## Tech Choices Explained
- **Groq API (llama-3.3-70b-versatile):** Selected for its incredible speed and free tier allowing 500K tokens/day without a credit card.
- **YOLOv8n (CPU-only):** Nano version is extremely lightweight, providing fast object detection (~200ms) on HuggingFace's free CPU tier.
- **sentence-transformers/all-MiniLM-L6-v2:** High-quality local embeddings, ensuring GDPR safety by not sending queries to an external API.
- **cross-encoder/ms-marco-MiniLM-L-6-v2:** Used for reranking RAG results locally to improve document retrieval accuracy without extra cost.
- **ChromaDB & rank-bm25:** Used for the Vector Database and Sparse RAG, giving a powerful hybrid search without needing a cloud database subscription.
- **HuggingFace Spaces & Vercel:** Best-in-class free hosting for Docker/FastAPI backends and React frontends.

## MLOps Practices Explained
- **Prometheus Counters/Histograms:** Tracks API latency, inference times, and defect rates in real-time.
- **RAGAS Integration:** ~~Asynchronous evaluation of the RAG pipeline assessing faithfulness, answer relevancy, and context precision.~~ **Correction:** `backend/mlops/evaluation.py` is currently an empty placeholder (`pass`, with a "Placeholder for RAGAS evaluation" comment) — this was claimed as working before it was, and is corrected here rather than left standing. See "Evaluation" below for what actually is measured.
- **Structured Logging:** Utilizes `structlog` for predictable, parsable application logs to debug model behavior quickly.

## ⚠️ Honest limitation: the defect detector is not a trained defect model

`backend/vision/detector.py` runs stock YOLOv8n, pretrained on COCO (everyday objects: people, cars, chairs), not fine-tuned on any manufacturing defect dataset. Whatever COCO class it happens to detect gets remapped onto a defect label (scratch/crack/dent/porosity/corrosion/inclusion) via `cls_id % 6` — the label has no real relationship to an actual defect. When the model finds nothing (the common case on real inspection-style images, which look nothing like COCO photos), the code falls back to a **deterministic, hash-based simulated detection**, explicitly marked `"simulated": True` in the return value and documented in-code as "make demos reproducible and impressive without fine-tuning." `test_vision.py`'s only vision test exercises exactly this fallback path on a black image, not real detection accuracy.

This is stated plainly rather than left for someone to discover by reading the source. No accuracy metric is reported for defect detection because there is nothing real to measure yet — fine-tuning on a real dataset (the code's own comment suggests MVTec Anomaly Detection, which is free) is the next real piece of work here, not something already done.

## Evaluation: RAG retrieval (real, local, $0)

Unlike the vision side, the RAG components (`rag/embeddings.py` LocalEmbeddings, `rag/retriever.py` BM25Index, `rag/reranker.py` CrossEncoderReranker) are genuinely real and run entirely locally via sentence-transformers — no external API, no cost. `tests/eval_retrieval.py` measures BM25 vs. local dense embedding retrieval against 20 hand-labeled manufacturing-QC queries over a 20-passage corpus, using the real, unmodified `BM25Index` and `LocalEmbeddings` classes:

```
BM25            Recall@1=100.0%  Recall@3=100.0%
Dense (local)   Recall@1=100.0%  Recall@3=100.0%
```

Both methods hit 100% on this set — worth being honest about what that does and doesn't prove: the 20 QC passages are topically distinct enough (each query has essentially one clearly-correct match) that this particular eval doesn't stress-test the difference between BM25 and dense retrieval the way RAGForge's comparable eval did (where Hybrid actually underperformed Dense). A harder eval with near-duplicate or ambiguous passages would be needed to meaningfully separate the two methods here; this run confirms both retrieval paths work correctly end-to-end, not that they're equally good under pressure.

## Quick Start
1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR-USERNAME/fertigungsai.git
   cd fertigungsai
   ```
2. Copy environment file and add your Groq API key:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. Run the complete stack via Docker Compose:
   ```bash
   docker-compose up --build
   ```

## Free Deployment Guide Step by Step
1. **Backend (HuggingFace Spaces):**
   - Create a new Space on HuggingFace and select "Docker" as the SDK.
   - Set the `GROQ_API_KEY` in the space settings.
   - Push the contents of the `fertigungsai` repository to the Space.
2. **Frontend (Vercel):**
   - Import the `frontend` folder to a new Vercel project.
   - Set the `VITE_API_URL` environment variable to your HuggingFace Space URL.
   - Deploy.
3. **CI/CD:**
   - Configure your GitHub repository secrets: `GROQ_API_KEY`, `HF_TOKEN`, `HF_USERNAME`, `VERCEL_TOKEN`.

## Cost Breakdown: €0.00/month
- LLM Inference: €0 (Groq)
- Vision Inference: €0 (Local YOLOv8n)
- Vector DB: €0 (Local ChromaDB)
- Backend Hosting: €0 (HuggingFace Spaces)
- Frontend Hosting: €0 (Vercel)
- CI/CD: €0 (GitHub Actions)

## EU AI Act Compliance Note
This system falls under **Minimal Risk (Article 6)**. It acts as an internal quality control system and does not interact with consumers, manipulate human behavior, or make safety-critical decisions autonomously.

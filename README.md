# FertigungsAI - Multimodal AI Quality Control Inspector

## 1. Problem Statement
Germany manufacturing loses €50B/year to defects.
40% of SMEs cannot find AI-qualified workers (BMBF 2024).
This project demonstrates how a student can build a production-grade multimodal AI for this market using entirely free tools.

## 2. Live Demo Links
- **Backend:** [https://YOUR-USERNAME-fertigungsai.hf.space](https://YOUR-USERNAME-fertigungsai.hf.space)
- **Frontend:** [https://fertigungsai.vercel.app](https://fertigungsai.vercel.app)
- **API Docs:** [https://YOUR-USERNAME-fertigungsai.hf.space/docs](https://YOUR-USERNAME-fertigungsai.hf.space/docs)

## 3. Architecture Diagram

```ascii
Image Upload → FastAPI → YOLOv8n → LangGraph →
[Hybrid RAG: ChromaDB + BM25 + RRF] →
[Cross-Encoder Reranker] →
[Groq LLaMA-3.3-70B] → SSE Stream → React Frontend
```

## 4. Tech Choices Explained
- **Groq API (llama-3.3-70b-versatile):** Selected for its incredible speed and free tier allowing 500K tokens/day without a credit card.
- **YOLOv8n (CPU-only):** Nano version is extremely lightweight, providing fast object detection (~200ms) on HuggingFace's free CPU tier.
- **sentence-transformers/all-MiniLM-L6-v2:** High-quality local embeddings, ensuring GDPR safety by not sending queries to an external API.
- **cross-encoder/ms-marco-MiniLM-L-6-v2:** Used for reranking RAG results locally to improve document retrieval accuracy without extra cost.
- **ChromaDB & rank-bm25:** Used for the Vector Database and Sparse RAG, giving a powerful hybrid search without needing a cloud database subscription.
- **HuggingFace Spaces & Vercel:** Best-in-class free hosting for Docker/FastAPI backends and React frontends.

## 5. MLOps Practices Explained
- **Prometheus Counters/Histograms:** Tracks API latency, inference times, and defect rates in real-time.
- **RAGAS Integration:** Asynchronous evaluation of the RAG pipeline assessing faithfulness, answer relevancy, and context precision.
- **Structured Logging:** Utilizes `structlog` for predictable, parsable application logs to debug model behavior quickly.

## 6. Quick Start
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

## 7. Free Deployment Guide Step by Step
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

## 8. Cost Breakdown: €0.00/month
- LLM Inference: €0 (Groq)
- Vision Inference: €0 (Local YOLOv8n)
- Vector DB: €0 (Local ChromaDB)
- Backend Hosting: €0 (HuggingFace Spaces)
- Frontend Hosting: €0 (Vercel)
- CI/CD: €0 (GitHub Actions)

## 9. EU AI Act Compliance Note
This system falls under **Minimal Risk (Article 6)**. It acts as an internal quality control system and does not interact with consumers, manipulate human behavior, or make safety-critical decisions autonomously.

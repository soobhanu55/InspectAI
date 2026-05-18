# FertigungsAI Backend

The backend is built with FastAPI, LangGraph, and runs completely locally using free open-source models (Llama 3.3 via Groq, YOLOv8n, sentence-transformers, ChromaDB, and rank-bm25).

It uses HuggingFace Spaces Docker SDK for free, always-on hosting.

## Running Locally

1. Setup virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run server:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 7860 --reload
   ```

## Tests

Run tests with `pytest`:
```bash
pytest tests/ -v
```

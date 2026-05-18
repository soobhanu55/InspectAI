from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # LLM — Groq free tier
    groq_api_key: str = "gsk_dummy"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.1
    groq_max_tokens: int = 1500

    # Embeddings — local, free
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    device: str = "cpu"  # HuggingFace free tier is CPU only

    # Vector store — local files, free
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "manufacturing_docs"

    # RAG config
    retrieval_top_k: int = 5
    reranker_top_k: int = 3
    dense_weight: float = 0.7
    sparse_weight: float = 0.3
    rrf_k: int = 60

    # Vision — CPU YOLOv8n
    yolo_model: str = "yolov8n.pt"
    yolo_conf_threshold: float = 0.25
    image_size: int = 640

    # MLOps — local SQLite, free
    sqlite_db: str = "./fertigungsai.db"
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"

    # LangSmith — free tier tracing (optional)
    langsmith_api_key: str | None = None
    langsmith_project: str = "fertigungsai"

    # App
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 7860  # HuggingFace Spaces port

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()

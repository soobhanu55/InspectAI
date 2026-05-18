from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog
import os

# Initialize environment paths
if not os.path.exists("./chroma_db"):
    os.makedirs("./chroma_db", exist_ok=True)

from api.routes.inspect import router as inspect_router
from api.routes.chat import router as chat_router
from api.routes.mlops import router as mlops_router
from api.routes.health import router as health_router
from config import get_settings

logger = structlog.get_logger()
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up all models on startup
    logger.info("Warming up models...")
    from rag.embeddings import get_embeddings
    from rag.reranker import get_reranker
    from vision.detector import get_detector
    get_embeddings()   # loads sentence-transformers
    get_reranker()     # loads cross-encoder
    get_detector()     # loads yolov8n
    # Ingest knowledge base docs if vector store empty
    from rag.vectorstore import get_document_count
    from data.ingest import ingest_knowledge_base
    if get_document_count() == 0:
        await ingest_knowledge_base()
        logger.info("Knowledge base ingested")
    logger.info("All models ready")
    yield

app = FastAPI(
    title="FertigungsAI API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vercel frontend URL added in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inspect_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(mlops_router, prefix="/api")
app.include_router(health_router)

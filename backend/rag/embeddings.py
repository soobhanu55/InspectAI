from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings
from functools import lru_cache
from typing import List
from config import get_settings

settings = get_settings()

class LocalEmbeddings(Embeddings):
    """
    GDPR-safe local embeddings. No external API calls.
    Data never leaves the server.
    Cost: €0.
    """
    def __init__(self):
        self.model = SentenceTransformer(
            settings.embedding_model,
            device=settings.device
        )
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(
            texts, batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False
        ).tolist()
    
    def embed_query(self, text: str) -> List[float]:
        return self.model.encode(
            text, normalize_embeddings=True
        ).tolist()

@lru_cache()
def get_embeddings() -> LocalEmbeddings:
    return LocalEmbeddings()

from sentence_transformers import CrossEncoder
from functools import lru_cache
from config import get_settings

settings = get_settings()

@lru_cache()
def get_reranker():
    return CrossEncoder(
        settings.reranker_model,
        device=settings.device,
        max_length=512
    )

class CrossEncoderReranker:
    def rerank(self, query, documents, top_k=3):
        if not documents:
            return []
        model = get_reranker()
        pairs = [(query, doc.page_content) for doc, _ in documents]
        scores = model.predict(pairs, show_progress_bar=False)
        reranked = sorted(
            zip([d for d,_ in documents], scores),
            key=lambda x: x[1], reverse=True
        )
        return reranked[:top_k]

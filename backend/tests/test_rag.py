import pytest
from rag.embeddings import get_embeddings
from rag.retriever import HybridRetriever, BM25Index
from langchain_core.documents import Document

def test_embeddings_dimension():
    embeddings = get_embeddings()
    result = embeddings.embed_query("Kratzer Ursache")
    assert len(result) == 384  # Dimension of all-MiniLM-L6-v2

def test_hybrid_retriever():
    # Create a dummy BM25 index and verify search works
    bm25 = BM25Index(index_path="test_bm25_index.pkl", docs_path="test_bm25_docs.pkl")
    docs = [
        Document(page_content="Kratzer entstehen oft durch Abrieb.", metadata={}),
        Document(page_content="Porosität entsteht beim Gießen.", metadata={})
    ]
    bm25.build(docs)
    
    results = bm25.search("Kratzer", k=1)
    assert len(results) == 1
    assert "Kratzer" in results[0][0].page_content

import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi
import nltk
from langchain_core.documents import Document
from rag.vectorstore import get_vectorstore
from config import get_settings

settings = get_settings()

class BM25Index:
    def __init__(self, index_path="bm25_index.pkl", docs_path="bm25_docs.pkl"):
        self.index_path = Path(index_path)
        self.docs_path = Path(docs_path)
        self.bm25 = None
        self.docs = []
        self._load()
        
    def _tokenize(self, text):
        return nltk.word_tokenize(text.lower())
        
    def build(self, documents: list[Document]):
        self.docs = documents
        tokenized_corpus = [self._tokenize(doc.page_content) for doc in documents]
        self.bm25 = BM25Okapi(tokenized_corpus)
        with open(self.index_path, "wb") as f:
            pickle.dump(self.bm25, f)
        with open(self.docs_path, "wb") as f:
            pickle.dump(self.docs, f)
            
    def _load(self):
        if self.index_path.exists() and self.docs_path.exists():
            with open(self.index_path, "rb") as f:
                self.bm25 = pickle.load(f)
            with open(self.docs_path, "rb") as f:
                self.docs = pickle.load(f)
                
    def search(self, query: str, k: int = 5):
        if not self.bm25:
            return []
        tokenized_query = self._tokenize(query)
        doc_scores = self.bm25.get_scores(tokenized_query)
        top_n = sorted(range(len(doc_scores)), key=lambda i: doc_scores[i], reverse=True)[:k]
        return [(self.docs[i], doc_scores[i]) for i in top_n]

class HybridRetriever:
    def __init__(self):
        self.vectorstore = get_vectorstore()
        self.bm25_index = BM25Index()
    
    def retrieve(self, query: str, top_k: int = 5):
        # 1. Dense retrieval (ChromaDB)
        # Handle cases where vectorstore is empty
        try:
            dense = self.vectorstore.similarity_search_with_relevance_scores(
                query, k=top_k*2
            )
        except Exception:
            dense = []
        
        # 2. Sparse retrieval (BM25)
        sparse = self.bm25_index.search(query, k=top_k*2)
        
        # 3. Reciprocal Rank Fusion
        return self._rrf_fusion(dense, sparse, top_k)
    
    def _rrf_fusion(self, dense, sparse, top_k, k=60):
        scores = {}
        doc_map = {}
        
        for rank, (doc, _) in enumerate(dense):
            did = doc.page_content[:80]
            scores[did] = scores.get(did,0) + settings.dense_weight/(k+rank+1)
            doc_map[did] = doc
        
        for rank, (doc, _) in enumerate(sparse):
            did = doc.page_content[:80]
            scores[did] = scores.get(did,0) + settings.sparse_weight/(k+rank+1)
            doc_map[did] = doc
        
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_map[did], score) for did, score in ranked[:top_k]]

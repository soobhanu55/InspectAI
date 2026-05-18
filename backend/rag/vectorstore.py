from langchain_chroma import Chroma
from functools import lru_cache
from rag.embeddings import get_embeddings
from config import get_settings

settings = get_settings()

@lru_cache()
def get_vectorstore():
    embeddings = get_embeddings()
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=embeddings,
        persist_directory=settings.chroma_persist_dir
    )

def get_document_count() -> int:
    try:
        store = get_vectorstore()
        return len(store.get()['ids'])
    except Exception:
        return 0

def add_documents(documents):
    store = get_vectorstore()
    store.add_documents(documents)

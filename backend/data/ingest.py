from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from pathlib import Path
from rag.vectorstore import add_documents
from rag.retriever import BM25Index

async def ingest_knowledge_base():
    """
    Ingest manufacturing knowledge base docs into ChromaDB.
    Runs once on first startup if vector store is empty.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", ".", " "]
    )
    
    docs = []
    kb_path = Path("data/knowledge_base")
    if not kb_path.exists():
        return
        
    for txt_file in kb_path.glob("*.txt"):
        text = txt_file.read_text(encoding="utf-8")
        chunks = splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            docs.append(Document(
                page_content=chunk,
                metadata={
                    "source": txt_file.name,
                    "chunk": i,
                    "category": "manufacturing"
                }
            ))
    
    if docs:
        add_documents(docs)
        # Also build BM25 index
        bm25 = BM25Index()
        bm25.build(docs)

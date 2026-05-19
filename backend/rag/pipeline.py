from typing import AsyncGenerator
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from rag.retriever import HybridRetriever
from rag.reranker import CrossEncoderReranker
from config import get_settings

settings = get_settings()

def get_context(query: str) -> str:
    retriever = HybridRetriever()
    retrieved = retriever.retrieve(query, top_k=settings.retrieval_top_k)
    
    if not retrieved:
        return ""
        
    reranker = CrossEncoderReranker()
    reranked = reranker.rerank(query, retrieved, top_k=settings.reranker_top_k)
    
    return "\n\n".join([doc.page_content for doc, _ in reranked])

class RAGPipeline:
    def __init__(self):
        api_key = settings.groq_api_key or "gsk_dummy"
        self.llm = ChatGroq(
            model=settings.groq_model,
            temperature=settings.groq_temperature,
            api_key=api_key,
            streaming=True
        )
        self.system_prompt = """You are a German manufacturing quality assistant. 
        Answer user questions based ONLY on the provided context. If the context does not contain the answer, 
        say so. Answer in the language the user asked."""
        
    async def astream(self, query: str, machine: str, session_id: str) -> AsyncGenerator[str, None]:
        context = get_context(query)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", f"Context:\n{context}\n\nMachine: {machine}\n\nQuestion: {query}")
        ])
        
        chain = prompt | self.llm
        
        async for chunk in chain.astream({}):
            if chunk.content:
                yield chunk.content

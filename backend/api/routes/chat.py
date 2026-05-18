from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from rag.pipeline import RAGPipeline
import asyncio

router = APIRouter()

@router.get("/chat")
async def chat_stream(query: str, session_id: str, machine: str):
    async def generate():
        pipeline = RAGPipeline()
        async for chunk in pipeline.astream(query, machine, session_id):
            yield {"data": chunk}
            await asyncio.sleep(0.01)
        yield {"data": "[DONE]"}
        
    return EventSourceResponse(generate())

from fastapi import APIRouter, Query

from app.schemas import KnowledgeSearchResult
from app.config import settings
from app.services.knowledge import search_chunks, split_markdown_chunks

router = APIRouter(tags=["knowledge"])

@router.get("/knowledge/search", response_model=list[KnowledgeSearchResult])
def knowledge_search(q: str = Query(min_length=1), limit: int = 5):
    if not settings.knowledge_path.exists():
        return []
    chunks = split_markdown_chunks(
        settings.knowledge_path.read_text(encoding="utf-8"),
        source_path=str(settings.knowledge_path),
    )
    return search_chunks(chunks, q, limit=limit)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import AgentNoteCreate, ReviewAppendRequest
from app.services.agent_context import (
    append_review_markdown,
    build_asset_context,
    build_research_context,
    build_today_context,
    save_agent_note,
)

router = APIRouter(tags=["agent"])


@router.get("/agent/context/today")
def today_context(topic: str | None = None, session: Session = Depends(get_session)):
    return build_today_context(session, topic=topic)


@router.get("/agent/research-context/today")
def today_research_context(topic: str | None = None, session: Session = Depends(get_session)):
    return build_research_context(session, topic=topic)


@router.get("/agent/analysis-package/today")
def today_analysis_package(topic: str | None = None, session: Session = Depends(get_session)):
    """Stable package endpoint for external Skills and agents."""
    return build_research_context(session, topic=topic)


@router.post("/agent/reviews/append")
def append_review(payload: ReviewAppendRequest):
    try:
        return append_review_markdown(payload.analysis_date, payload.content, payload.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"无法写入复盘文件：{exc}") from exc


@router.get("/agent/assets/{code}")
def asset_context(code: str, session: Session = Depends(get_session)):
    return build_asset_context(session, code)


@router.post("/agent/notes", status_code=201)
def create_agent_note(payload: AgentNoteCreate, session: Session = Depends(get_session)):
    note = save_agent_note(session, payload.title, payload.content, payload.note_date, payload.source)
    return {"id": note.id, "title": note.title, "note_date": note.note_date.isoformat()}

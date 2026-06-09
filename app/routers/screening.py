from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import csv, io

from app.database import get_db
from app.routers.deps import get_current_user
from app.models.user import User
from app.models.screening import ScreeningSession, ScreeningResult, ComplianceReport
from app.services import screening_service
from app.services.report_service import generate_pdf_report

router = APIRouter(prefix="/screening", tags=["screening"])


class ScreenRequest(BaseModel):
    name: str
    country: Optional[str] = None
    entity_type: Optional[str] = None
    date_of_birth: Optional[str] = None
    sources: Optional[List[str]] = None


class ScreenResponse(BaseModel):
    session_id: str
    query_name: str
    status: str
    total_results: int
    hit_count: int
    possible_count: int
    overall_result: str
    results: list
    sources_checked: list


@router.post("", response_model=ScreenResponse)
def screen_entity(
    req: ScreenRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = screening_service.screen_entity(
        db=db,
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        query_name=req.name,
        query_country=req.country,
        query_type=req.entity_type,
        query_dob=req.date_of_birth,
        sources=req.sources,
        ip_address=request.client.host if request.client else None,
    )
    return _session_to_response(session)


@router.post("/batch")
async def screen_batch(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    sessions = []
    for row in reader:
        name = row.get("name") or row.get("Name") or row.get("entity") or ""
        if not name.strip():
            continue
        country = row.get("country") or row.get("Country") or None
        etype   = row.get("type")    or row.get("Type")    or None
        s = screening_service.screen_entity(
            db=db,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id),
            query_name=name.strip(),
            query_country=country,
            query_type=etype,
            sources=None,
        )
        sessions.append(_session_to_response(s))

    return {"total": len(sessions), "sessions": sessions}


@router.get("/history")
def get_history(
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ScreeningSession)\
          .filter(ScreeningSession.tenant_id == current_user.tenant_id)\
          .order_by(ScreeningSession.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [_session_summary(s) for s in items],
    }


@router.get("/{session_id}")
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(ScreeningSession).filter_by(id=session_id, tenant_id=current_user.tenant_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    return _session_to_response(s)


@router.get("/{session_id}/report/download")
def download_report(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(ScreeningSession).filter_by(id=session_id, tenant_id=current_user.tenant_id).first()
    if not s:
        raise HTTPException(404, "Session not found")
    pdf_bytes = generate_pdf_report(s, current_user)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=CIS_Report_{session_id[:8]}.pdf"},
    )


def _session_to_response(s: ScreeningSession) -> dict:
    if s.hit_count > 0:
        overall = "hit"
    elif s.possible_count > 0:
        overall = "possible_match"
    else:
        overall = "clear"

    results = []
    for r in (s.results or []):
        results.append({
            "id": str(r.id),
            "score": r.score,
            "result": r.match_result.value if r.match_result else "clear",
            "name": r.matched_name,
            "source": r.matched_source,
            "type": r.matched_type,
            "country": r.matched_country,
            "program": r.matched_program,
            "detail": r.match_detail or {},
        })

    return {
        "session_id": str(s.id),
        "query_name": s.query_name,
        "status": s.status.value if s.status else "completed",
        "total_results": s.total_results,
        "hit_count": s.hit_count,
        "possible_count": s.possible_count,
        "overall_result": overall,
        "results": sorted(results, key=lambda x: -x["score"]),
        "sources_checked": s.sources_checked or [],
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _session_summary(s: ScreeningSession) -> dict:
    if s.hit_count > 0:
        overall = "hit"
    elif s.possible_count > 0:
        overall = "possible_match"
    else:
        overall = "clear"
    return {
        "session_id": str(s.id),
        "query_name": s.query_name,
        "overall_result": overall,
        "hit_count": s.hit_count,
        "possible_count": s.possible_count,
        "sources_checked": s.sources_checked or [],
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }

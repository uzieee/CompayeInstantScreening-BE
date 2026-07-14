from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from app.database import get_db
from app.routers.deps import get_current_user
from app.models.user import User
from app.models.audit import AuditLog, AuditAction
from app.models.tenant import Tenant

from app.models.screening import ScreeningSession, ScreeningResult, MatchResult

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)

    # Searches today
    searches_today = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_([AuditAction.screening, AuditAction.batch_screening]),
            func.date(AuditLog.created_at) == today,
        )
        .scalar() or 0
    )

    # Searches this month
    searches_month = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_([AuditAction.screening, AuditAction.batch_screening]),
            AuditLog.created_at >= month_start,
        )
        .scalar() or 0
    )

    # Hits today
    hits_today = (
        db.query(func.count(AuditLog.id))
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.result == "hit",
            func.date(AuditLog.created_at) == today,
        )
        .scalar() or 0
    )

    # Pending reviews
    pending = (
        db.query(func.count(AuditLog.id))
        .filter(AuditLog.tenant_id == tenant_id, AuditLog.result == "possible_match")
        .scalar() or 0
    )

    # Recent activity (last 10)
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )

    # 14-day trend
    trend = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        s = (
            db.query(func.count(AuditLog.id))
            .filter(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action.in_([AuditAction.screening, AuditAction.batch_screening]),
                func.date(AuditLog.created_at) == d,
            )
            .scalar() or 0
        )
        h = (
            db.query(func.count(AuditLog.id))
            .filter(
                AuditLog.tenant_id == tenant_id,
                AuditLog.result == "hit",
                func.date(AuditLog.created_at) == d,
            )
            .scalar() or 0
        )
        trend.append({"date": d.isoformat(), "searches": s, "hits": h})

    # Risk breakdown
    def count_result(res):
        return (
            db.query(func.count(AuditLog.id))
            .filter(AuditLog.tenant_id == tenant_id, AuditLog.result == res)
            .scalar() or 0
        )

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    return {
        "total_searches_today": searches_today,
        "total_searches_month": searches_month,
        "hits_today": hits_today,
        "pending_reviews": pending,
        "quota_used": tenant.searches_used if tenant else 0,
        "quota_total": tenant.search_quota if tenant else 500,
        "recent_activity": [
            {
                "id": str(log.id),
                "action": log.action.value.replace("_", " ").title(),
                "entity": log.entity_name or "—",
                "result": log.result or "clear",
                "user": log.user.full_name if log.user else "System",
                "timestamp": log.created_at.isoformat(),
            }
            for log in recent
        ],
        "search_trend": trend,
        "risk_breakdown": {
            "clear": count_result("clear"),
            "hits": count_result("hit"),
            "possible_matches": count_result("possible_match"),
            "pending": count_result("possible_match"),
        },
    }


@router.get("/analytics")
def get_analytics(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)

    # Daily trend for requested period
    trend = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        searches = db.query(func.count(AuditLog.id)).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_([AuditAction.screening, AuditAction.batch_screening]),
            func.date(AuditLog.created_at) == d,
        ).scalar() or 0
        hits = db.query(func.count(AuditLog.id)).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.result == "hit",
            func.date(AuditLog.created_at) == d,
        ).scalar() or 0
        possible = db.query(func.count(AuditLog.id)).filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.result == "possible_match",
            func.date(AuditLog.created_at) == d,
        ).scalar() or 0
        trend.append({"date": d.isoformat(), "searches": searches, "hits": hits, "possible": possible})

    # Source breakdown from screening results
    source_rows = (
        db.query(ScreeningResult.matched_source, func.count(ScreeningResult.id))
        .join(ScreeningSession, ScreeningResult.session_id == ScreeningSession.id)
        .filter(ScreeningSession.tenant_id == tenant_id)
        .group_by(ScreeningResult.matched_source)
        .all()
    )
    source_breakdown = [{"source": r[0] or "Unknown", "count": r[1]} for r in source_rows if r[0]]

    # Entity type breakdown
    type_rows = (
        db.query(ScreeningResult.matched_type, func.count(ScreeningResult.id))
        .join(ScreeningSession, ScreeningResult.session_id == ScreeningSession.id)
        .filter(ScreeningSession.tenant_id == tenant_id, ScreeningResult.match_result == MatchResult.hit)
        .group_by(ScreeningResult.matched_type)
        .all()
    )
    type_breakdown = [{"type": r[0] or "unknown", "count": r[1]} for r in type_rows]

    # Top hit countries
    country_rows = (
        db.query(ScreeningResult.matched_country, func.count(ScreeningResult.id))
        .join(ScreeningSession, ScreeningResult.session_id == ScreeningSession.id)
        .filter(
            ScreeningSession.tenant_id == tenant_id,
            ScreeningResult.match_result == MatchResult.hit,
            ScreeningResult.matched_country != None,
            ScreeningResult.matched_country != "",
        )
        .group_by(ScreeningResult.matched_country)
        .order_by(func.count(ScreeningResult.id).desc())
        .limit(8)
        .all()
    )
    top_countries = [{"country": r[0], "count": r[1]} for r in country_rows]

    # Summary totals
    total_screens = db.query(func.count(AuditLog.id)).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.action.in_([AuditAction.screening, AuditAction.batch_screening]),
        AuditLog.created_at >= start,
    ).scalar() or 0

    total_hits = db.query(func.count(AuditLog.id)).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.result == "hit",
        AuditLog.created_at >= start,
    ).scalar() or 0

    total_possible = db.query(func.count(AuditLog.id)).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.result == "possible_match",
        AuditLog.created_at >= start,
    ).scalar() or 0

    total_clear = db.query(func.count(AuditLog.id)).filter(
        AuditLog.tenant_id == tenant_id,
        AuditLog.result == "clear",
        AuditLog.created_at >= start,
    ).scalar() or 0

    hit_rate = round((total_hits / total_screens * 100), 1) if total_screens > 0 else 0

    return {
        "period_days": days,
        "summary": {
            "total_screens": total_screens,
            "total_hits": total_hits,
            "total_possible": total_possible,
            "total_clear": total_clear,
            "hit_rate": hit_rate,
        },
        "trend": trend,
        "source_breakdown": source_breakdown,
        "type_breakdown": type_breakdown,
        "top_countries": top_countries,
    }

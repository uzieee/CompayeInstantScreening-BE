from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from app.database import get_db
from app.routers.deps import get_current_user
from app.models.user import User
from app.models.audit import AuditLog, AuditAction
from app.models.tenant import Tenant

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

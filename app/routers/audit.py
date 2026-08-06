from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.routers.deps import get_current_user
from app.models.user import User
from app.models.audit import AuditLog, AuditAction

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    page: int = 1,
    per_page: int = 50,
    action: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AuditLog).filter(AuditLog.tenant_id == current_user.tenant_id)
    if action:
        q = q.filter(AuditLog.action == action)
    total = q.count()
    logs = q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [
            {
                "id": str(l.id),
                "action": l.action.value if l.action else "",
                "entity": l.entity_name or "—",
                "result": l.result or "",
                "user": l.user.full_name if l.user else "System",
                "ip": l.ip_address or "",
                "timestamp": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }


@router.get("/connection-report")
def connection_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """TC-RPT-06: User connection (login) activity report."""
    rows = (
        db.query(
            AuditLog.user_id,
            func.count(AuditLog.id).label("login_count"),
            func.min(AuditLog.created_at).label("first_login"),
            func.max(AuditLog.created_at).label("last_login"),
        )
        .filter(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.action == AuditAction.login,
        )
        .group_by(AuditLog.user_id)
        .all()
    )

    report = []
    for row in rows:
        user = db.query(User).filter(User.id == row.user_id).first()
        report.append({
            "user_id": str(row.user_id) if row.user_id else None,
            "user_name": user.full_name if user else "Unknown",
            "user_email": user.email if user else "",
            "login_count": row.login_count,
            "first_login": row.first_login.isoformat() if row.first_login else None,
            "last_login": row.last_login.isoformat() if row.last_login else None,
        })

    return {"total_users": len(report), "report": sorted(report, key=lambda x: -(x["login_count"] or 0))}

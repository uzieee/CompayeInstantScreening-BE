from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.routers.deps import get_current_user
from app.models.user import User
from app.models.audit import AuditLog

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

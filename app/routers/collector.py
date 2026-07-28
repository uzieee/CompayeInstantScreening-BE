"""Trigger sanctions list collection (admin only)."""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.routers.deps import require_roles, get_current_user
from app.models.user import User
from app.collectors import ofac, eu, un, uk, canada, australia, switzerland, bis

router = APIRouter(prefix="/collector", tags=["collector"])

ALL_COLLECTORS = [
    ("ofac",        ofac.collect),
    ("un",          un.collect),
    ("eu",          eu.collect),
    ("uk",          uk.collect),
    ("canada",      canada.collect),
    ("australia",   australia.collect),
    ("seco",        switzerland.collect),
    ("bis",         bis.collect),
]


def _run_all(db: Session):
    results = {}
    for name, fn in ALL_COLLECTORS:
        try:
            results[name] = fn(db)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


@router.post("/run")
def trigger_collection(
    background_tasks: BackgroundTasks,
    source: str = "all",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "tenant_admin")),
):
    """Trigger sanctions list download in the background."""
    background_tasks.add_task(_run_all, db)
    return {"message": "Collection started in background", "source": source}


@router.post("/run/sync")
def trigger_collection_sync(
    source: str = "all",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "tenant_admin")),
):
    """Trigger collection synchronously (for testing)."""
    results = _run_all(db)
    from sqlalchemy import func
    from app.models.sanctions import SanctionedEntity
    total = db.query(func.count(SanctionedEntity.id)).scalar()
    return {"results": results, "total_entities": total}


@router.get("/status")
def collection_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func
    from app.models.sanctions import SanctionedEntity
    rows = db.query(SanctionedEntity.source, func.count(SanctionedEntity.id))\
             .group_by(SanctionedEntity.source).all()
    return {"counts": {r[0]: r[1] for r in rows}}

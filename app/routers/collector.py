"""Trigger sanctions list collection (admin only)."""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.routers.deps import require_roles, get_current_user
from app.models.user import User
from app.collectors import ofac, eu, un, uk

router = APIRouter(prefix="/collector", tags=["collector"])


def _run_all(db: Session):
    results = {}
    try: results["ofac"] = ofac.collect(db)
    except Exception as e: results["ofac"] = {"error": str(e)}
    try: results["un"]   = un.collect(db)
    except Exception as e: results["un"]   = {"error": str(e)}
    try: results["eu"]   = eu.collect(db)
    except Exception as e: results["eu"]   = {"error": str(e)}
    try: results["uk"]   = uk.collect(db)
    except Exception as e: results["uk"]   = {"error": str(e)}
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

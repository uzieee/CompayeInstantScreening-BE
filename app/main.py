from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.config import settings
from app.database import engine, Base

# Register all models before create_all
import app.models.tenant    # noqa
import app.models.user      # noqa
import app.models.audit     # noqa
import app.models.sanctions # noqa
import app.models.screening # noqa

from app.routers import auth, dashboard, screening, audit, collector, users, admin


def _run_migrations():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for sql in [
            "ALTER TABLE screening_sessions ADD COLUMN IF NOT EXISTS ai_narrative TEXT",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                pass
    _seed_super_admins()


def _seed_super_admins():
    """Create Complaye Consulting tenant and super admin accounts if not present."""
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    from app.utils.security import hash_password
    db = SessionLocal()
    try:
        # Ensure Complaye Consulting tenant exists
        tenant = db.query(Tenant).filter(Tenant.slug == "complaye-consulting").first()
        if not tenant:
            tenant = Tenant(name="Complaye Consulting", slug="complaye-consulting",
                            country="BE", plan="enterprise", search_quota=999999)
            db.add(tenant)
            db.flush()

        for email, name in [
            ("tatymcharlene@gmail.com", "Charlene Taty"),
            ("charlene.taty@outlook.fr", "Charlene Taty"),
        ]:
            if not db.query(User).filter(User.email == email).first():
                db.add(User(
                    tenant_id=tenant.id, email=email, full_name=name,
                    hashed_password=hash_password("Complaye2024!"),
                    role=UserRole.super_admin, is_verified=True, is_active=True,
                ))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from app.routers.collector import _run_all_background

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_migrations)

    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_all_background, CronTrigger(hour=0, minute=0), id="daily_sanctions_sync")
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) if settings.DEBUG else "Internal server error"},
    )


PREFIX = "/api/v1"
app.include_router(auth.router,       prefix=PREFIX)
app.include_router(dashboard.router,  prefix=PREFIX)
app.include_router(screening.router,  prefix=PREFIX)
app.include_router(audit.router,      prefix=PREFIX)
app.include_router(collector.router,  prefix=PREFIX)
app.include_router(users.router,      prefix=PREFIX)
app.include_router(admin.router,      prefix=PREFIX)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}

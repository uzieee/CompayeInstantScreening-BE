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

from app.routers import auth, dashboard, screening, audit, collector, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


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


@app.get("/api/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}

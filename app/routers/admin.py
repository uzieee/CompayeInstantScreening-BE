"""Super-admin management endpoints — full cross-tenant visibility."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database import get_db
from app.routers.deps import require_roles
from app.models.user import User, UserRole
from app.models.tenant import Tenant, PlanType
from app.utils.security import hash_password
import re, uuid

router = APIRouter(prefix="/admin", tags=["admin"])

require_super = require_roles("super_admin")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value if hasattr(u.role, "value") else u.role,
        "is_active": u.is_active,
        "two_factor_enabled": u.two_factor_enabled,
        "tenant_id": str(u.tenant_id),
        "tenant_name": u.tenant.name if u.tenant else "",
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


def _tenant_dict(t: Tenant) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "slug": t.slug,
        "country": t.country,
        "plan": t.plan.value if hasattr(t.plan, "value") else t.plan,
        "is_active": t.is_active,
        "search_quota": t.search_quota,
        "searches_used": t.searches_used,
        "user_count": len(t.users),
        "created_at": t.created_at.isoformat(),
    }


# ── Tenants ───────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    name: str
    country: Optional[str] = None
    plan: str = "trial"
    search_quota: int = 500


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [_tenant_dict(t) for t in tenants]


@router.post("/tenants", status_code=201)
def create_tenant(
    data: TenantCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    slug = re.sub(r'[^\w-]', '-', data.name.lower()).strip('-')[:80]
    base = slug
    i = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base}-{i}"; i += 1

    tenant = Tenant(
        name=data.name, slug=slug, country=data.country,
        plan=data.plan, search_quota=data.search_quota,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return _tenant_dict(tenant)


@router.patch("/tenants/{tenant_id}")
def update_tenant(
    tenant_id: str,
    data: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    for field in ("name", "plan", "is_active", "search_quota"):
        if field in data:
            setattr(tenant, field, data[field])
    db.commit()
    db.refresh(tenant)
    return _tenant_dict(tenant)


# ── Users ─────────────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "analyst"
    tenant_id: str


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_all_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [_user_dict(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    if db.query(User).filter(User.email == data.email.lower()).first():
        raise HTTPException(400, "Email already registered")
    tenant = db.query(Tenant).filter(Tenant.id == data.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    user = User(
        tenant_id=tenant.id,
        email=data.email.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if data.full_name:    user.full_name = data.full_name
    if data.role:         user.role = data.role
    if data.is_active is not None: user.is_active = data.is_active
    if data.password:     user.hashed_password = hash_password(data.password)
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_super),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()

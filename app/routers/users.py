from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.routers.deps import get_current_user, require_roles
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)


@router.patch("/me")
def update_me(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if data.full_name:
        current_user.full_name = data.full_name
    db.commit()
    db.refresh(current_user)
    return _user_dict(current_user)


@router.get("")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "tenant_admin")),
):
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id).all()
    return [_user_dict(u) for u in users]


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "tenant_admin")),
):
    user = db.query(User).filter_by(id=user_id, tenant_id=current_user.tenant_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if data.full_name:  user.full_name = data.full_name
    if data.role:       user.role = data.role
    if data.is_active is not None: user.is_active = data.is_active
    db.commit()
    return _user_dict(user)


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value if hasattr(u.role, "value") else u.role,
        "is_active": u.is_active,
        "two_factor_enabled": u.two_factor_enabled,
        "tenant_id": str(u.tenant_id),
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }

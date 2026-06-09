from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TokenResponse, TwoFAVerifyRequest,
    TwoFASetupResponse, TwoFAConfirmRequest, TwoFADisableRequest,
    ForgotPasswordRequest, ResetPasswordRequest, UserMeResponse,
)
from app.services import auth_service
from app.routers.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_user(db, data)
    return {"message": "Account created successfully", "user_id": str(user.id)}


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    result = auth_service.login(db, data.email, data.password)
    return result


@router.post("/2fa/verify", response_model=TokenResponse)
def verify_2fa(data: TwoFAVerifyRequest, db: Session = Depends(get_db)):
    result = auth_service.verify_2fa(db, data.temp_token, data.code)
    return result


@router.post("/2fa/setup", response_model=TwoFASetupResponse)
def setup_2fa(current_user: User = Depends(get_current_user)):
    return auth_service.setup_2fa(current_user)


@router.post("/2fa/confirm")
def confirm_2fa(
    data: TwoFAConfirmRequest,
    pending_secret: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    auth_service.confirm_2fa(db, current_user, data.code, pending_secret)
    return {"message": "2FA enabled successfully"}


@router.post("/2fa/disable")
def disable_2fa(
    data: TwoFADisableRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    auth_service.disable_2fa(db, current_user, data.code)
    return {"message": "2FA disabled"}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always return 200 to prevent email enumeration
    user = auth_service.get_user_by_email(db, data.email)
    if user:
        # TODO: send reset email
        pass
    return {"message": "If that email exists, a reset link has been sent"}


@router.get("/me", response_model=UserMeResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserMeResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        tenant_id=str(current_user.tenant_id),
        tenant_name=current_user.tenant.name,
        is_active=current_user.is_active,
        two_factor_enabled=current_user.two_factor_enabled,
        created_at=current_user.created_at.isoformat(),
        last_login=current_user.last_login.isoformat() if current_user.last_login else None,
    )

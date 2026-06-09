from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User, UserRole
from app.models.tenant import Tenant, PlanType
from app.schemas.auth import RegisterRequest
from app.utils.security import (
    hash_password, verify_password, create_access_token, create_temp_token,
    decode_token, generate_totp_secret, get_totp_uri, verify_totp, generate_secure_token,
)
import re
import io
import base64
import qrcode


def get_user_by_email(db: Session, email: str) -> "User | None":
    return db.query(User).filter(User.email == email.lower()).first()


def slugify(name: str) -> str:
    s = re.sub(r'[^\w\s-]', '', name.lower())
    s = re.sub(r'[\s_-]+', '-', s)
    return s.strip('-')[:80]


def register_user(db: Session, data: RegisterRequest) -> User:
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    base_slug = slugify(data.company_name)
    slug = base_slug
    counter = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    tenant = Tenant(
        name=data.company_name,
        slug=slug,
        country=data.country,
        plan=PlanType.trial,
        search_quota=500,
    )
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=data.email.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role=UserRole.tenant_admin,
        is_verified=True,  # skip email verification for now
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")
    user.last_login = datetime.utcnow()
    db.commit()
    return user


def login(db: Session, email: str, password: str) -> dict:
    user = authenticate_user(db, email, password)

    if user.two_factor_enabled:
        return {
            "requires_2fa": True,
            "temp_token": create_temp_token(str(user.id)),
        }

    token = create_access_token({"sub": str(user.id), "tenant": str(user.tenant_id), "role": user.role})
    return {"access_token": token, "token_type": "bearer", "requires_2fa": False}


def verify_2fa(db: Session, temp_token: str, code: str) -> dict:
    payload = decode_token(temp_token)
    if not payload or payload.get("type") != "2fa_pending":
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA not configured")

    if not verify_totp(user.two_factor_secret, code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token({"sub": str(user.id), "tenant": str(user.tenant_id), "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


def setup_2fa(user: User) -> dict:
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)

    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return {"secret": secret, "qr_uri": uri, "qr_image_base64": qr_b64, "_pending_secret": secret}


def confirm_2fa(db: Session, user: User, code: str, pending_secret: str) -> None:
    if not verify_totp(pending_secret, code):
        raise HTTPException(status_code=400, detail="Invalid code — please try again")
    user.two_factor_secret = pending_secret
    user.two_factor_enabled = True
    db.commit()


def disable_2fa(db: Session, user: User, code: str) -> None:
    if not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")
    if not verify_totp(user.two_factor_secret, code):
        raise HTTPException(status_code=400, detail="Invalid code")
    user.two_factor_secret = None
    user.two_factor_enabled = False
    db.commit()

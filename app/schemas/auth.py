from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    country: str


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    temp_token: Optional[str] = None


class TwoFAVerifyRequest(BaseModel):
    temp_token: str
    code: str


class TwoFASetupResponse(BaseModel):
    secret: str
    qr_uri: str
    qr_image_base64: str


class TwoFAConfirmRequest(BaseModel):
    code: str


class TwoFADisableRequest(BaseModel):
    code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class UserMeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    tenant_id: str
    tenant_name: str
    is_active: bool
    two_factor_enabled: bool
    created_at: str
    last_login: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

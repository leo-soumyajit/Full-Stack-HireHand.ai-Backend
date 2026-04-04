from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    company_name: str = Field(..., min_length=2, max_length=100)
    company_domain: Optional[str] = None
    company_logo: Optional[str] = None
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserInDB(BaseModel):
    name: str
    company_name: str
    company_domain: Optional[str] = None
    company_logo: Optional[str] = None
    email: EmailStr
    hashed_password: str
    is_verified: bool = False
    verification_otp: Optional[str] = None
    otp_expires_at: Optional[datetime] = None
    position: Optional[str] = None
    phone_code: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    name: str
    company_name: str
    company_domain: Optional[str] = None
    company_logo: Optional[str] = None
    email: EmailStr
    is_verified: bool = False
    position: Optional[str] = None
    phone_code: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None

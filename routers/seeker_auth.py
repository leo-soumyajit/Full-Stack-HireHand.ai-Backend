"""
Job Seeker authentication — isolated from HR /api/auth.
Mounted at /api/seeker/auth. JWTs carry typ="seeker".
Reuses the same OTP + Resend email flow as HR for consistency.
"""
from fastapi import APIRouter, HTTPException, status, Depends
import os
import random
from datetime import timedelta, datetime, timezone

from database import job_seekers_collection, user_collection
from core.security import (
    verify_password, get_password_hash, create_access_token,
    decode_access_token, ACCESS_TOKEN_EXPIRE_MINUTES,
)
from core.resend_email import send_verification_email, send_password_reset_email
from core.seeker_deps import get_current_seeker, serialize_seeker
from models.job_seeker import (
    SeekerCreate, SeekerLogin, SeekerVerifyOTP, SeekerResendOTP,
    SeekerForgotPassword, SeekerResetPassword, SeekerToken, SeekerResponse,
)

router = APIRouter()


def _make_token(email: str) -> str:
    expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return create_access_token(data={"sub": email, "typ": "seeker"}, expires_delta=expires)


def _token_payload(doc: dict) -> dict:
    return {
        "access_token": _make_token(doc["email"]),
        "token_type": "bearer",
        "seeker": serialize_seeker(doc),
    }


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def seeker_signup(body: SeekerCreate):
    # Block if the email is already an HR account (keep the two worlds separate)
    if await user_collection.find_one({"email": body.email}):
        raise HTTPException(status_code=400, detail="This email is registered as a recruiter account.")

    existing = await job_seekers_collection.find_one({"email": body.email})
    if existing:
        if existing.get("is_verified", False):
            raise HTTPException(status_code=400, detail="Email already registered")
        await job_seekers_collection.delete_one({"email": body.email})

    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    doc = {
        "name": body.name,
        "email": body.email,
        "hashed_password": get_password_hash(body.password),
        "is_verified": False,
        "verification_otp": otp,
        "otp_expires_at": expires_at,
        "skills": [],
        "education": [],
        "work_experience": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await job_seekers_collection.insert_one(doc)
    send_verification_email(body.email, otp, body.name)
    return {"need_verification": True, "email": body.email, "message": "Verification code sent."}


@router.post("/verify-otp", response_model=SeekerToken)
async def seeker_verify_otp(body: SeekerVerifyOTP):
    seeker = await job_seekers_collection.find_one({"email": body.email})
    if not seeker:
        raise HTTPException(status_code=404, detail="Account not found")
    if seeker.get("is_verified", False):
        raise HTTPException(status_code=400, detail="Account already verified")
    if seeker.get("verification_otp") != body.otp:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    exp = seeker.get("otp_expires_at")
    if exp and exp.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired")

    await job_seekers_collection.update_one(
        {"email": body.email},
        {"$set": {"is_verified": True}, "$unset": {"verification_otp": "", "otp_expires_at": ""}},
    )
    seeker = await job_seekers_collection.find_one({"email": body.email})
    return _token_payload(seeker)


@router.post("/resend-otp")
async def seeker_resend_otp(body: SeekerResendOTP):
    seeker = await job_seekers_collection.find_one({"email": body.email})
    if not seeker:
        raise HTTPException(status_code=404, detail="Account not found")
    if seeker.get("is_verified", False):
        raise HTTPException(status_code=400, detail="Account already verified")
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await job_seekers_collection.update_one(
        {"email": body.email},
        {"$set": {"verification_otp": otp, "otp_expires_at": expires_at}},
    )
    send_verification_email(seeker["email"], otp, seeker["name"])
    return {"message": "Verification code resent."}


@router.post("/login", response_model=SeekerToken)
async def seeker_login(body: SeekerLogin):
    seeker = await job_seekers_collection.find_one({"email": body.email})
    if not seeker or not verify_password(body.password, seeker["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not seeker.get("is_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email before logging in.")
    return _token_payload(seeker)


@router.post("/forgot-password")
async def seeker_forgot_password(body: SeekerForgotPassword):
    seeker = await job_seekers_collection.find_one({"email": body.email})
    if seeker:
        reset_token = create_access_token(
            data={"sub": seeker["email"], "typ": "seeker", "type": "password_reset"},
            expires_delta=timedelta(minutes=15),
        )
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip("/")
        reset_link = f"{frontend_url}/seeker/reset-password?token={reset_token}"
        send_password_reset_email(seeker["email"], seeker["name"], reset_link)
    return {"message": "If that email is registered, a reset link will be sent."}


@router.post("/reset-password")
async def seeker_reset_password(body: SeekerResetPassword):
    payload = decode_access_token(body.token)
    if not payload or payload.get("type") != "password_reset" or payload.get("typ") != "seeker":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    email = payload.get("sub")
    seeker = await job_seekers_collection.find_one({"email": email})
    if not seeker:
        raise HTTPException(status_code=404, detail="Account not found")
    await job_seekers_collection.update_one(
        {"email": email},
        {"$set": {"hashed_password": get_password_hash(body.new_password)}},
    )
    return {"message": "Password successfully reset"}


@router.get("/me", response_model=SeekerResponse)
async def seeker_me(seeker: dict = Depends(get_current_seeker)):
    return serialize_seeker(seeker)

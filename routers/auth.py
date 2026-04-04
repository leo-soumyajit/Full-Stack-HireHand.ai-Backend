from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from core.deps import get_current_user
from pydantic import BaseModel, EmailStr
from database import user_collection
from core.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from models.user import UserCreate, UserInDB, Token, UserResponse
from core.email import send_password_reset_email, send_verification_email
import os
import random
from datetime import timedelta, datetime, timezone
from typing import Optional
from bson import ObjectId
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, File

# Configure Cloudinary
cloudinary.config( 
  cloud_name = "di5i72sy9", 
  api_key = "572758113724938", 
  api_secret = "LBnZ_kEVCCCRJ5B63jN2hcZ226k",
  secure = True
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResendOTPRequest(BaseModel):
    email: EmailStr

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_logo: Optional[str] = None
    position: Optional[str] = None
    phone_code: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    existing_user = await user_collection.find_one({"email": user.email})
    if existing_user:
        if existing_user.get("is_verified", False):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        else:
            # User exists but not verified, let them sign up again (overwrite)
            await user_collection.delete_one({"email": user.email})

    hashed_password = get_password_hash(user.password)
    user_dict = user.model_dump()
    user_dict.pop("password")
    
    # Generate OTP
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    db_user = UserInDB(
        **user_dict, 
        hashed_password=hashed_password,
        is_verified=False,
        verification_otp=otp,
        otp_expires_at=expires_at
    )
    result = await user_collection.insert_one(db_user.model_dump())

    # Send Notification Email asynchronously (or synchronously depending on the implementation)
    send_verification_email(user.email, otp, user.name)

    return {"need_verification": True, "email": user.email, "message": "Verification code sent."}

@router.post("/verify-otp", response_model=Token)
async def verify_otp(body: VerifyOTPRequest):
    user = await user_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    if user.get("is_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already verified")
        
    if user.get("verification_otp") != body.otp:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        
    if user.get("otp_expires_at") and user["otp_expires_at"].replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired")
        
    # Mark as verified
    await user_collection.update_one(
        {"email": body.email},
        {"$set": {"is_verified": True}, "$unset": {"verification_otp": "", "otp_expires_at": ""}}
    )
    
    # Proceed to login
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)

    user_response = UserResponse(
        id=str(user["_id"]), 
        name=user["name"], 
        company_name=user["company_name"], 
        company_domain=user.get("company_domain"),
        company_logo=user.get("company_logo"),
        email=user["email"],
        is_verified=True,
        position=user.get("position"),
        phone_code=user.get("phone_code"),
        phone=user.get("phone"),
        bio=user.get("bio"),
        avatar_url=user.get("avatar_url"),
        cover_url=user.get("cover_url")
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}

@router.post("/resend-otp")
async def resend_otp(body: ResendOTPRequest):
    user = await user_collection.find_one({"email": body.email})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    if user.get("is_verified", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already verified")
        
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    await user_collection.update_one(
        {"email": body.email},
        {"$set": {"verification_otp": otp, "otp_expires_at": expires_at}}
    )
    
    send_verification_email(user["email"], otp, user["name"])
    
    return {"message": "Verification code resent."}

@router.put("/profile", response_model=UserResponse)
async def update_profile(body: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    user = await user_collection.find_one({"email": current_user["email"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    # Perform update in MongoDB
    await user_collection.update_one(
        {"email": current_user["email"]},
        {"$set": update_data}
    )

    # Fetch updated user
    updated_user = await user_collection.find_one({"email": current_user["email"]})
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Failed to fetch updated profile")

    return UserResponse(
        id=str(updated_user["_id"]),
        name=updated_user["name"],
        company_name=updated_user["company_name"],
        company_domain=updated_user.get("company_domain"),
        company_logo=updated_user.get("company_logo"),
        email=updated_user["email"],
        is_verified=updated_user.get("is_verified", False),
        position=updated_user.get("position"),
        phone_code=updated_user.get("phone_code"),
        phone=updated_user.get("phone"),
        bio=updated_user.get("bio"),
        avatar_url=updated_user.get("avatar_url"),
        cover_url=updated_user.get("cover_url")
    )

@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed")

    try:
        # Read the file
        contents = await file.read()
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(contents, folder="hirehand/profiles")
        secure_url = result.get("secure_url")
        
        if not secure_url:
            raise Exception("Failed to get url from Cloudinary")
            
        return {"url": secure_url}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Image upload failed: {str(e)}")

@router.post("/login", response_model=Token)
async def login(body: LoginRequest):
    """JSON-body login — used by the React frontend."""
    user = await user_collection.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    if not user.get("is_verified", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in. If you lost the code, sign up again to generate a new one.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)

    user_response = UserResponse(
        id=str(user["_id"]), 
        name=user["name"], 
        company_name=user["company_name"], 
        company_domain=user.get("company_domain"),
        company_logo=user.get("company_logo"),
        email=user["email"]
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}


@router.post("/token", response_model=Token)
async def login_oauth2(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 form-data login — kept for Swagger UI / testing."""
    user = await user_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    if not user.get("is_verified", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in. If you lost the code, sign up again to generate a new one.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)
    user_response = UserResponse(
        id=str(user["_id"]), 
        name=user["name"], 
        company_name=user["company_name"], 
        company_domain=user.get("company_domain"),
        company_logo=user.get("company_logo"),
        email=user["email"]
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}

@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    user = await user_collection.find_one({"email": body.email})
    if not user:
        # To prevent email enumeration, we still return a success message
        return {"message": "If that email is registered, a reset link will be sent."}
    
    # Create a 15-minute reset token
    expires_delta = timedelta(minutes=15)
    reset_token = create_access_token(
        data={"sub": user["email"], "type": "password_reset"}, 
        expires_delta=expires_delta
    )
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080").rstrip('/')
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"
    
    # Send email
    send_password_reset_email(user["email"], user["name"], reset_link)
    
    return {"message": "If that email is registered, a reset link will be sent."}

@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    from core.security import decode_access_token
    payload = decode_access_token(body.token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
        
    if payload.get("type") != "password_reset":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token type")
        
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")
        
    user = await user_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Hashing the new password
    new_hashed_password = get_password_hash(body.new_password)
    
    
    await user_collection.update_one(
        {"email": email},
        {"$set": {"hashed_password": new_hashed_password}}
    )
    
    return {"message": "Password successfully reset"}

@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user = await user_collection.find_one({"email": current_user["email"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    if not verify_password(body.old_password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect old password")
        
    new_hashed_password = get_password_hash(body.new_password)
    
    await user_collection.update_one(
        {"email": current_user["email"]},
        {"$set": {"hashed_password": new_hashed_password}}
    )
    
    return {"message": "Password successfully changed"}

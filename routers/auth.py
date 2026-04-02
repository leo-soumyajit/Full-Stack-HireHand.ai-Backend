from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from core.deps import get_current_user
from pydantic import BaseModel, EmailStr
from database import user_collection
from core.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from models.user import UserCreate, UserInDB, Token, UserResponse
from core.email import send_password_reset_email
import os
from datetime import timedelta
from bson import ObjectId

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    existing_user = await user_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    user_dict = user.model_dump()
    user_dict.pop("password")

    db_user = UserInDB(**user_dict, hashed_password=hashed_password)
    result = await user_collection.insert_one(db_user.model_dump())

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)

    user_response = UserResponse(id=str(result.inserted_id), name=user.name, company_name=user.company_name, email=user.email)
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}


@router.post("/login", response_model=Token)
async def login(body: LoginRequest):
    """JSON-body login — used by the React frontend."""
    user = await user_collection.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)

    user_response = UserResponse(id=str(user["_id"]), name=user["name"], company_name=user["company_name"], email=user["email"])
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}


@router.post("/token", response_model=Token)
async def login_oauth2(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 form-data login — kept for Swagger UI / testing."""
    user = await user_collection.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["email"]}, expires_delta=access_token_expires)
    user_response = UserResponse(id=str(user["_id"]), name=user["name"], company_name=user["company_name"], email=user["email"])
    user_response = UserResponse(id=str(user["_id"]), name=user["name"], company_name=user["company_name"], email=user["email"])
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

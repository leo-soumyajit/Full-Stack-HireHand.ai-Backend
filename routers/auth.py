from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from database import user_collection
from core.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from models.user import UserCreate, UserInDB, Token, UserResponse
from datetime import timedelta
from bson import ObjectId

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
    return {"access_token": access_token, "token_type": "bearer", "user": user_response}

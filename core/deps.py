from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.security import decode_access_token
from database import user_collection

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency that decodes the JWT and returns the user from MongoDB.
    Raises 401 if token is invalid or user not found.
    All protected routes depend on this for user-scoping.
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email: str = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await user_collection.find_one({"email": email}, {"hashed_password": 0})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    actual_user_id = str(user.pop("_id"))

    # RBAC: Team members need to see the organization's data, not their own empty data.
    # org_id for owner = their own _id. org_id for team members = the owner's _id.
    # By using org_id as the effective "id", ALL existing router queries that filter
    # by user_id automatically see the shared org data — zero router file changes needed.
    org_id = user.get("org_id")
    user["id"] = org_id if org_id else actual_user_id
    user["self_id"] = actual_user_id  # Actual user ID for profile/auth/team ops
    return user

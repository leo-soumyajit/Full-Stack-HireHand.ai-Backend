"""
HireHand Team Management Router
═════════════════════════════════
Fully isolated CRUD for team members.
Owner/Admin can create, list, update roles, and delete team members.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime, timezone
import secrets
import string

from database import user_collection
from core.deps import get_current_user
from core.rbac import require_role, VALID_ROLES, ROLE_HIERARCHY
from core.security import get_password_hash
from core.resend_email import send_team_invite_email

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ══════════════════════════════════════════════════════════════════════

class CreateTeamMemberRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: str = Field(..., description="One of: admin, manager, interviewer, viewer")

class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="One of: admin, manager, interviewer, viewer")

class TeamMemberResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_verified: bool
    created_at: Optional[str] = None
    avatar_url: Optional[str] = None

class RoleInfo(BaseModel):
    role: str
    level: int
    description: str
    permissions: List[str]


# ══════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════

def _generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


def _user_to_response(user: dict) -> TeamMemberResponse:
    return TeamMemberResponse(
        id=str(user["_id"]),
        name=user.get("name", ""),
        email=user.get("email", ""),
        role=user.get("role", "viewer"),
        is_verified=user.get("is_verified", False),
        created_at=user.get("created_at", None),
        avatar_url=user.get("avatar_url", None),
    )


ROLE_DESCRIPTIONS = {
    "owner": {
        "description": "Full access. Organization creator with god-mode permissions.",
        "permissions": ["All permissions", "Transfer ownership", "Delete organization"],
    },
    "admin": {
        "description": "Co-administrator. Can manage team, positions, candidates, and all reports.",
        "permissions": ["Manage team members", "Create/edit/delete positions", "Manage candidates",
                        "Screen resumes", "Generate assessments", "Conduct interviews", "View all reports"],
    },
    "manager": {
        "description": "Hiring manager. Can create positions, manage candidates, generate assessments, and view reports.",
        "permissions": ["Create/edit positions", "Manage candidates", "Screen resumes",
                        "Generate assessments", "Send assessments", "Schedule interviews",
                        "Generate reports", "View all reports"],
    },
    "interviewer": {
        "description": "Interviewer. Can conduct interviews, score psychometrics, and view reports.",
        "permissions": ["Conduct interviews", "Score psychometrics",
                        "View positions", "View candidates", "View reports", "View schedules"],
    },
    "viewer": {
        "description": "Read-only access. Can view all data but cannot create, edit, or delete anything.",
        "permissions": ["View positions", "View candidates", "View reports", "View schedules"],
    },
}


# ══════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════

@router.get("/roles", response_model=List[RoleInfo])
async def list_roles(current_user: dict = Depends(get_current_user)):
    """List all available roles with their descriptions and permissions."""
    roles = []
    for role_name in VALID_ROLES:
        info = ROLE_DESCRIPTIONS.get(role_name, {})
        roles.append(RoleInfo(
            role=role_name,
            level=ROLE_HIERARCHY.get(role_name, 0),
            description=info.get("description", ""),
            permissions=info.get("permissions", []),
        ))
    return roles


@router.get("/members", response_model=List[TeamMemberResponse])
async def list_team_members(current_user: dict = Depends(require_role("owner", "admin"))):
    """List all team members in the same organization."""
    org_id = current_user.get("org_id")
    if not org_id:
        return [_user_to_response(current_user | {"_id": ObjectId(current_user["self_id"])})]

    cursor = user_collection.find(
        {"org_id": org_id},
        {"hashed_password": 0, "verification_otp": 0, "otp_expires_at": 0}
    ).sort("role", 1)

    members = []
    async for user in cursor:
        members.append(_user_to_response(user))
    return members


@router.post("/members", response_model=TeamMemberResponse, status_code=status.HTTP_201_CREATED)
async def create_team_member(
    body: CreateTeamMemberRequest,
    current_user: dict = Depends(require_role("owner", "admin")),
):
    """Create a new team member. Sends an invite email with temporary credentials."""
    
    # Validate role
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")
    
    if body.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot create another owner. There can only be one owner per organization.")

    # Only owner can create admins
    if body.role == "admin" and current_user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can create admin accounts.")

    # Check if email already exists
    existing = await user_collection.find_one({"email": body.email})
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    # Generate temp password
    temp_password = _generate_temp_password()
    hashed_password = get_password_hash(temp_password)

    org_id = current_user.get("org_id", current_user["self_id"])

    new_member = {
        "name": body.name,
        "email": body.email,
        "hashed_password": hashed_password,
        "role": body.role,
        "org_id": org_id,
        "invited_by": current_user["self_id"],
        "company_name": current_user.get("company_name", ""),
        "company_domain": current_user.get("company_domain"),
        "company_logo": current_user.get("company_logo"),
        "is_verified": True,  # Team members are pre-verified (invited by admin)
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await user_collection.insert_one(new_member)
    new_member["_id"] = result.inserted_id

    # Send invite email with temp credentials
    try:
        send_team_invite_email(
            to_email=body.email,
            member_name=body.name,
            inviter_name=current_user.get("name", "Admin"),
            company_name=current_user.get("company_name", "HireHand"),
            role=body.role,
            temp_password=temp_password,
        )
    except Exception as e:
        print(f"⚠️ [Team] Failed to send invite email to {body.email}: {e}")
        # Don't fail the creation — user is created, email is secondary

    return _user_to_response(new_member)


@router.patch("/members/{member_id}/role", response_model=TeamMemberResponse)
async def update_member_role(
    member_id: str,
    body: UpdateRoleRequest,
    current_user: dict = Depends(require_role("owner", "admin")),
):
    """Update a team member's role."""
    
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    if body.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot assign owner role. Ownership transfer is not supported yet.")

    try:
        member_oid = ObjectId(member_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member ID format")

    member = await user_collection.find_one({"_id": member_oid})
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    # Can't change your own role
    if str(member["_id"]) == current_user["self_id"]:
        raise HTTPException(status_code=400, detail="You cannot change your own role.")

    # Can't modify the owner
    if member.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Cannot modify the owner's role.")

    # Only owner can promote to admin
    if body.role == "admin" and current_user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can promote members to admin.")

    # Verify same org
    if member.get("org_id") != current_user.get("org_id", current_user["self_id"]):
        raise HTTPException(status_code=403, detail="This member does not belong to your organization.")

    await user_collection.update_one(
        {"_id": member_oid},
        {"$set": {"role": body.role}}
    )

    updated = await user_collection.find_one({"_id": member_oid})
    return _user_to_response(updated)


@router.delete("/members/{member_id}")
async def delete_team_member(
    member_id: str,
    current_user: dict = Depends(require_role("owner", "admin")),
):
    """Remove a team member from the organization."""
    
    try:
        member_oid = ObjectId(member_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member ID format")

    member = await user_collection.find_one({"_id": member_oid})
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    # Can't delete yourself
    if str(member["_id"]) == current_user["self_id"]:
        raise HTTPException(status_code=400, detail="You cannot remove yourself from the team.")

    # Can't delete the owner
    if member.get("role") == "owner":
        raise HTTPException(status_code=403, detail="Cannot delete the organization owner.")

    # Admin can't delete another admin (only owner can)
    if member.get("role") == "admin" and current_user.get("role") != "owner":
        raise HTTPException(status_code=403, detail="Only the owner can remove admin accounts.")

    # Verify same org
    if member.get("org_id") != current_user.get("org_id", current_user["self_id"]):
        raise HTTPException(status_code=403, detail="This member does not belong to your organization.")

    await user_collection.delete_one({"_id": member_oid})

    return {"message": f"Team member '{member.get('name')}' removed successfully."}

"""
HireHand RBAC (Role-Based Access Control) Engine
═══════════════════════════════════════════════════
Fully isolated permission system. Does NOT modify any existing router logic.
Uses FastAPI middleware to enforce permissions based on route + HTTP method.
"""

from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.deps import get_current_user
from typing import List, Optional
import re

# ══════════════════════════════════════════════════════════════════════
# ROLE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════

VALID_ROLES = ["owner", "admin", "manager", "interviewer", "viewer"]

ROLE_HIERARCHY = {
    "owner": 5,
    "admin": 4,
    "manager": 3,
    "interviewer": 2,
    "viewer": 1,
}

# ══════════════════════════════════════════════════════════════════════
# PERMISSION MAP — Maps (HTTP_METHOD, route_regex) → minimum_role
# ══════════════════════════════════════════════════════════════════════
# Routes NOT listed here default to "authenticated only" (any role).
# The order matters — first match wins.

ROUTE_PERMISSIONS = [
    # ── Team Management (Owner/Admin only) ─────────────────────────
    ("POST",   r"^/api/team/members$",               "admin"),
    ("PATCH",  r"^/api/team/members/.+/role$",        "admin"),
    ("DELETE", r"^/api/team/members/.+$",             "admin"),
    ("GET",    r"^/api/team/members$",                "admin"),
    ("GET",    r"^/api/team/roles$",                  "viewer"),  # anyone can see roles list

    # ── Profile & Auth (self-service — any authenticated user) ─────
    ("PUT",    r"^/api/auth/profile$",                "viewer"),
    ("POST",   r"^/api/auth/upload-image$",           "viewer"),
    ("POST",   r"^/api/auth/change-password$",        "viewer"),

    # ── Positions ──────────────────────────────────────────────────
    ("POST",   r"^/api/positions$",                   "manager"),    # create
    ("PUT",    r"^/api/positions/[^/]+$",              "manager"),    # update
    ("DELETE", r"^/api/positions/[^/]+$",              "admin"),      # delete
    ("PATCH",  r"^/api/positions/[^/]+/status$",       "manager"),    # change status
    ("PATCH",  r"^/api/positions/[^/]+/jd$",           "manager"),    # save JD
    ("PUT",    r"^/api/positions/[^/]+/l1-questions$",  "manager"),   # save L1 questions
    ("PUT",    r"^/api/positions/[^/]+/screening-rules$", "manager"), # screening rules
    ("GET",    r"^/api/positions",                     "viewer"),     # view (any)

    # ── Candidates ─────────────────────────────────────────────────
    ("POST",   r"^/api/positions/[^/]+/candidates$",   "manager"),   # add
    ("POST",   r"^/api/positions/[^/]+/candidates/bulk-email$", "manager"), # bulk mail
    ("PATCH",  r"^/api/positions/candidates/.+$",      "manager"),   # update
    ("DELETE", r"^/api/positions/candidates/.+$",      "manager"),   # delete
    ("GET",    r"^/api/positions/.+/candidates",       "viewer"),    # view list
    ("GET",    r"^/api/positions/candidates/.+",       "viewer"),    # view single

    # ── Assessments ────────────────────────────────────────────────
    ("POST",   r"^/api/assessment/generate$",          "manager"),   # generate
    ("POST",   r"^/api/assessment/send$",              "manager"),   # send
    ("DELETE", r"^/api/assessment/position/.+$",       "manager"),   # clear
    ("PATCH",  r"^/api/assessment/position/.+$",       "manager"),   # edit question
    ("GET",    r"^/api/assessment/position/.+$",       "viewer"),    # view

    # ── Resume Screening ───────────────────────────────────────────
    ("POST",   r"^/api/positions/[^/]+/candidates/[^/]+/screen$", "manager"),
    ("GET",    r"^/api/positions/[^/]+/screened-resumes$",        "viewer"),

    # ── Psychometrics (EOS-IA) ─────────────────────────────────────
    ("POST",   r"^/api/psychometric/profile$",         "manager"),   # generate profile
    ("POST",   r"^/api/psychometric/scores$",          "interviewer"), # submit scores
    ("POST",   r"^/api/psychometric/report/.+$",       "manager"),   # generate report
    ("GET",    r"^/api/psychometric",                  "viewer"),    # view

    # ── Schedules ──────────────────────────────────────────────────
    ("POST",   r"^/api/schedules$",                    "manager"),   # create
    ("PATCH",  r"^/api/schedules/.+$",                 "manager"),   # update
    ("GET",    r"^/api/schedules",                     "viewer"),    # view

    # ── Interview Intelligence ─────────────────────────────────────
    ("POST",   r"^/api/interview-intelligence",        "interviewer"), # conduct/analyze
    ("GET",    r"^/api/interview-intelligence",        "viewer"),      # view reports

    # ── AI Tools ───────────────────────────────────────────────────
    ("POST",   r"^/api/ai",                            "manager"),

    # ── AI Interview (Autonomous) ─────────────────────────────────
    ("POST",   r"^/api/ai-interview/dispatch$",         "manager"),   # dispatch
    ("GET",    r"^/api/ai-interview/voices/list$",      "viewer"),    # list voices
    # GET /{token} and WebSocket /{token}/ws are public (candidate-facing)
    # GET /{token}/status is protected by Depends(get_current_user) in the router

    # ── Candidate-facing assessment (public — no auth needed) ──────
    # These routes use skipAuth / no Depends(get_current_user), so middleware won't block them
]


def _get_min_role_for_route(method: str, path: str) -> Optional[str]:
    """Find the minimum required role for a given HTTP method + path."""
    for perm_method, pattern, min_role in ROUTE_PERMISSIONS:
        if method.upper() == perm_method and re.match(pattern, path):
            return min_role
    return None  # No explicit rule → allow any authenticated user


def _has_sufficient_role(user_role: str, min_role: str) -> bool:
    """Check if user's role meets or exceeds the minimum required role."""
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(min_role, 99)


# ══════════════════════════════════════════════════════════════════════
# FASTAPI MIDDLEWARE — Enforces RBAC on ALL routes without touching routers
# ══════════════════════════════════════════════════════════════════════

# Routes that are completely public (no auth needed at all)
PUBLIC_ROUTE_PATTERNS = [
    r"^/$",
    r"^/docs",
    r"^/openapi",
    r"^/redoc",
    r"^/api/auth/signup$",
    r"^/api/auth/login$",
    r"^/api/auth/token$",
    r"^/api/auth/verify-otp$",
    r"^/api/auth/resend-otp$",
    r"^/api/auth/forgot-password$",
    r"^/api/auth/reset-password$",
    r"^/api/assessment/[^/]+$",          # GET assessment by token (candidate-facing)
    r"^/api/assessment/[^/]+/submit$",   # POST submit assessment (candidate-facing)
    r"^/api/deepgram",                   # Deepgram auth
    r"^/api/turn",                       # TURN/ICE servers
    r"^/api/live-transcript",            # WebSocket live transcript
    r"^/api/interview/.+",              # Interview room
    r"^/api/ai-interview/[^/]+$",        # AI Interview — candidate token validation
    r"^/api/ai-interview/[^/]+/ws$",     # AI Interview — WebSocket (candidate-facing)
]


def _is_public_route(path: str) -> bool:
    """Check if a route is public (no auth/role check needed)."""
    return any(re.match(p, path) for p in PUBLIC_ROUTE_PATTERNS)


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces role-based access control.
    
    Flow:
    1. If the route is public → pass through
    2. If no RBAC rule exists for this route → pass through (let existing auth handle it)
    3. If a rule exists → decode JWT, check role, block if insufficient
    
    This is 100% additive — it NEVER blocks routes that don't have explicit rules.
    Existing authentication (Depends(get_current_user)) still runs independently.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 1. Public routes — skip entirely
        if _is_public_route(path) or method == "OPTIONS":
            return await call_next(request)

        # 2. Find RBAC rule for this route
        min_role = _get_min_role_for_route(method, path)

        if min_role is None:
            # No explicit RBAC rule → let existing auth dependencies handle it
            return await call_next(request)

        # 3. Decode the JWT to get the user's role
        from core.security import decode_access_token
        from database import user_collection

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            # No token — let the existing Depends(get_current_user) handle the 401
            return await call_next(request)

        token = auth_header.split(" ", 1)[1]
        payload = decode_access_token(token)

        if payload is None:
            # Invalid token — let existing deps handle it
            return await call_next(request)

        email = payload.get("sub")
        if not email:
            return await call_next(request)

        # Fetch user's role from DB
        user = await user_collection.find_one({"email": email}, {"role": 1})
        if not user:
            return await call_next(request)

        user_role = user.get("role", "owner")  # Default to owner for backward compat

        # 4. Check permission
        if not _has_sufficient_role(user_role, min_role):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Access denied. Your role '{user_role}' does not have permission for this action. Required: '{min_role}' or higher."
                },
            )

        # 5. Authorized — continue to the actual endpoint
        return await call_next(request)


# ══════════════════════════════════════════════════════════════════════
# DEPENDENCY HELPERS — For use in NEW routes (like team.py) only
# ══════════════════════════════════════════════════════════════════════

def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory for NEW routes that need role checks.
    Does NOT modify any existing route — only used in new routers like team.py.
    
    Usage:
        @router.post("/members")
        async def create_member(current_user = Depends(require_role("owner", "admin"))):
    """
    async def _checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role", "owner")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}. Your role: {user_role}."
            )
        return current_user
    return _checker

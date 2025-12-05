"""
Authentication Models

Pydantic schemas for user authentication and authorization.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime


class User(BaseModel):
    """User model for authentication."""
    user_id: str = Field(..., description="Unique user identifier (username or email)")
    password_hash: str = Field(..., description="Hashed password")
    full_name: str = Field(..., description="User's full name")
    role: str = Field(default="member", description="User role: member, manager, admin")
    member_id: Optional[str] = Field(None, description="Associated member ID for dashboard access")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    is_active: bool = Field(default=True, description="Whether user account is active")
    
    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['member', 'manager', 'admin']
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of {allowed_roles}")
        return v


class LoginRequest(BaseModel):
    """Login request payload."""
    username: str = Field(..., min_length=3, description="Username or email")
    password: str = Field(..., min_length=4, description="Password")


class LoginResponse(BaseModel):
    """Login response with access token."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    role: str
    member_id: Optional[str] = None


class TokenData(BaseModel):
    """Data stored in JWT token."""
    user_id: str
    role: str
    member_id: Optional[str] = None


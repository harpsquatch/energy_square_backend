"""
System Notice domain schemas
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class SystemNoticeIn(BaseModel):
    type: str = Field(..., description="info|warning|success")
    severity: str = Field(..., description="low|medium|high")
    message: str = Field(..., description="Notice message")
    affected_users: int = Field(0, description="Affected users count")
    user_id: Optional[str] = Field(None, description="User ID for user-specific alerts. None for community-level alerts")


class SystemNoticeOut(SystemNoticeIn):
    created_at: datetime = Field(..., description="Creation timestamp")


"""
System Notice Service for managing community and user-level alerts
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.db.database import get_database
import logging

logger = logging.getLogger(__name__)


class SystemNoticeService:
    """Service for managing system notices (alerts) at community and user levels"""

    async def create_community_alert(
        self,
        type: str,
        severity: str,
        message: str,
        affected_users: int = 0
    ) -> Dict[str, Any]:
        """Create a community-level alert (visible to all users)."""
        try:
            db = await get_database()
            doc = {
                "type": type,
                "severity": severity,
                "message": message,
                "affected_users": affected_users,
                "user_id": None,  # None indicates community-level
                "created_at": datetime.now()
            }
            await db["system_notices"].insert_one(doc)
            doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"Error creating community alert: {e}")
            raise

    async def create_user_alert(
        self,
        user_id: str,
        type: str,
        severity: str,
        message: str
    ) -> Dict[str, Any]:
        """Create a user-specific alert (visible only to the specified user)."""
        try:
            db = await get_database()
            doc = {
                "type": type,
                "severity": severity,
                "message": message,
                "affected_users": 1,  # Single user
                "user_id": user_id,
                "created_at": datetime.now()
            }
            await db["system_notices"].insert_one(doc)
            doc.pop("_id", None)
            return doc
        except Exception as e:
            logger.error(f"Error creating user alert: {e}")
            raise

    async def list_community_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List community-level alerts (user_id is None or missing)."""
        try:
            db = await get_database()
            cursor = db["system_notices"].find(
                {"$or": [{"user_id": None}, {"user_id": {"$exists": False}}]},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit)

            alerts = []
            async for doc in cursor:
                alerts.append(self._format_notice(doc))
            return alerts
        except Exception as e:
            logger.error(f"Error listing community alerts: {e}")
            return []

    async def list_user_alerts(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """List alerts for a specific user (includes both community alerts and user-specific alerts)."""
        try:
            db = await get_database()
            # Get community alerts + user-specific alerts
            cursor = db["system_notices"].find(
                {"$or": [
                    {"user_id": None},
                    {"user_id": {"$exists": False}},
                    {"user_id": user_id}
                ]},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit)

            alerts = []
            async for doc in cursor:
                alerts.append(self._format_notice(doc))
            return alerts
        except Exception as e:
            logger.error(f"Error listing user alerts: {e}")
            return []

    async def list_all_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all alerts (community + user-specific). For admin/system controller use."""
        try:
            db = await get_database()
            cursor = db["system_notices"].find(
                {},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit)

            alerts = []
            async for doc in cursor:
                alerts.append(self._format_notice(doc))
            return alerts
        except Exception as e:
            logger.error(f"Error listing all alerts: {e}")
            return []

    def _format_notice(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format notice document for output (handles datetime serialization)."""
        created_at = doc.get("created_at", "")
        if hasattr(created_at, 'isoformat'):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at) if created_at else ""

        return {
            "type": doc.get("type", "info"),
            "severity": doc.get("severity", "medium"),
            "message": doc.get("message", ""),
            "affected_users": doc.get("affected_users", 0),
            "user_id": doc.get("user_id"),
            "created_at": created_at_str if created_at_str else doc.get("created_at")
        }


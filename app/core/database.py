"""
Shim module to ensure a single source of truth for MongoDB access.
Re-exports all database helpers from app.db.database.
"""

from app.db.database import (
    Database,
    db,
    get_database,
    connect_to_mongo,
    close_mongo_connection,
)

__all__ = [
    "Database",
    "db",
    "get_database",
    "connect_to_mongo",
    "close_mongo_connection",
]
